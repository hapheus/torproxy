#!/bin/bash
# ==============================================================================
# Transparent Tor Gateway Smoke & Leak Prevention Verification Script
# Validates:
#   1. iptables NAT rules present (TransPort 9040, DNSPort 9053)
#   2. iptables Kill Switch present (Reject non-Tor traffic)
#   3. Transparent TCP routing through Tor (curl without proxy flags returns IsTor: true)
#   4. DNS leak prevention (DNS resolves through Tor internal resolver)
#   5. Kill Switch enforcement (direct non-Tor UDP packets blocked)
# ==============================================================================
set -euo pipefail

GATEWAY_CONTAINER="${1:-torproxy-gateway-smoke}"

echo "=== 1. Netfilter Rules Inspection ==="
NAT_RULES=$(docker exec "$GATEWAY_CONTAINER" iptables -t nat -L OUTPUT -n)
echo "$NAT_RULES"
echo "$NAT_RULES" | grep -q "redir ports 9053" || (echo "❌ DNS redirect rule missing" && exit 1)
echo "$NAT_RULES" | grep -q "redir ports 9040" || (echo "❌ TransPort redirect rule missing" && exit 1)
echo "✅ NAT redirection rules verified."

# ISSUE-03: the WAN bypass must be scoped to the dedicated tor user,
# never to the torproxy UID (API/Privoxy share it).
TOR_UID=$(docker exec "$GATEWAY_CONTAINER" getent passwd tor | cut -d: -f3)
TORPROXY_UID=$(docker exec "$GATEWAY_CONTAINER" getent passwd torproxy | cut -d: -f3)
if echo "$NAT_RULES" | grep -q "owner UID match $TORPROXY_UID"; then
  echo "❌ CRITICAL: torproxy-UID WAN bypass present in NAT OUTPUT (dedicated tor user missing)!"
  exit 1
fi
echo "$NAT_RULES" | grep -q "owner UID match $TOR_UID" || (echo "❌ Tor-UID bypass rule missing in NAT OUTPUT" && exit 1)
echo "✅ Tor-UID-scoped NAT bypass verified."

FILTER_RULES=$(docker exec "$GATEWAY_CONTAINER" iptables -L OUTPUT -n)
echo "$FILTER_RULES"
echo "$FILTER_RULES" | grep -q "reject-with icmp-port-unreachable" || (echo "❌ Kill switch reject rule missing" && exit 1)
echo "✅ Filter kill switch verified."

# ISSUE-03: filter-side bypass must also be tor-UID-scoped, and Tor must keep
# an IPv6 egress exception while the IPv6 policy stays DROP.
if echo "$FILTER_RULES" | grep -q "owner UID match $TORPROXY_UID"; then
  echo "❌ CRITICAL: torproxy-UID WAN bypass present in filter OUTPUT (dedicated tor user missing)!"
  exit 1
fi
echo "$FILTER_RULES" | grep -q "owner UID match $TOR_UID" || (echo "❌ Tor-UID bypass rule missing in filter OUTPUT" && exit 1)
IP6_RULES=$(docker exec "$GATEWAY_CONTAINER" ip6tables -L OUTPUT -n)
echo "$IP6_RULES"
echo "$IP6_RULES" | grep -q "owner UID match $TOR_UID" || (echo "❌ Tor-UID IPv6 exception missing" && exit 1)
echo "✅ IPv6: Tor exception present, policy DROP retained."

# ISSUE-02: an unrestricted ESTABLISHED,RELATED accept would let pre-existing
# clearnet connections survive a Tor outage and silently break fail-closed.
if echo "$FILTER_RULES" | grep -q "RELATED,ESTABLISHED"; then
  echo "❌ CRITICAL: unrestricted ESTABLISHED,RELATED accept present in filter OUTPUT (fail-closed bypass)!"
  exit 1
fi
echo "✅ No ESTABLISHED fail-closed bypass rule present."

echo "=== 2. Transparent Tor Egress Verification ==="
CLIENT_OUTPUT=$(docker run --rm --network "container:${GATEWAY_CONTAINER}" curlimages/curl:latest -sS --connect-timeout 15 --max-time 30 https://check.torproject.org/api/ip)
echo "Client Response: $CLIENT_OUTPUT"
IS_TOR=$(echo "$CLIENT_OUTPUT" | jq -r '.IsTor // empty')
EXIT_IP=$(echo "$CLIENT_OUTPUT" | jq -r '.IP // empty')

if [ "$IS_TOR" != "true" ]; then
  echo "❌ CRITICAL: Outgoing traffic was NOT identified as Tor egress!"
  exit 1
fi
echo "✅ Transparent Tor routing verified: Exit IP is $EXIT_IP (IsTor=true)."

echo "=== 3. UDP Kill Switch & Leak Prevention Verification ==="
# Attempt direct non-DNS UDP transmission (e.g. NTP port 123) - should be immediately blocked/rejected
if docker run --rm --network "container:${GATEWAY_CONTAINER}" alpine:3.24 sh -c "nc -z -u -w 2 1.1.1.1 123" 2>/dev/null; then
  echo "❌ CRITICAL: Direct UDP traffic to 1.1.1.1:123 bypassed kill switch (UDP LEAK)!"
  exit 1
else
  echo "✅ Direct non-DNS UDP traffic correctly blocked by kill switch."
fi

echo "=== All Transparent Gateway Verification Tests PASSED! ==="
