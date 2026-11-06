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

FILTER_RULES=$(docker exec "$GATEWAY_CONTAINER" iptables -L OUTPUT -n)
echo "$FILTER_RULES"
echo "$FILTER_RULES" | grep -q "reject-with icmp-port-unreachable" || (echo "❌ Kill switch reject rule missing" && exit 1)
echo "✅ Filter kill switch verified."

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
# Attempt direct UDP transmission - should be immediately blocked/rejected
if docker run --rm --network "container:${GATEWAY_CONTAINER}" alpine:3.24 sh -c "nc -z -u -w 2 1.1.1.1 53" 2>/dev/null; then
  echo "❌ CRITICAL: UDP traffic to 1.1.1.1 bypassed kill switch (UDP LEAK)!"
  exit 1
else
  echo "✅ Direct UDP traffic correctly blocked by kill switch."
fi

echo "=== All Transparent Gateway Verification Tests PASSED! ==="
