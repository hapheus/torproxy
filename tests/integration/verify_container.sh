#!/bin/bash
# ==============================================================================
# Container Smoke & Integration Verification Script
# Validates:
#   1. Non-root user execution
#   2. Process supervision (tor, privoxy, api)
#   3. Multi-port reachability (8118, 9050, 8080)
#   4. REST API contract & backward compatibility
#   5. Fail-closed behavior & leak prevention on disconnect
# ==============================================================================
set -euo pipefail

CONTAINER_NAME="${1:-torproxy-smoke}"
API_PORT="${2:-8080}"
HTTP_PORT="${3:-8118}"
SOCKS_PORT="${4:-9050}"

echo "=== 1. Non-Root Execution Verification ==="
# ISSUE-03: the init runs as root only to drop privileges; every daemon
# must run as an unprivileged user (tor, privoxy, torproxy).
PIDS=$(docker exec "$CONTAINER_NAME" sh -c 'for p in /proc/[0-9]*; do c=$(cat "$p/comm" 2>/dev/null); u=$(stat -c %u "$p" 2>/dev/null); [ -n "$u" ] && echo "$c $u"; done')
echo "$PIDS"
echo "$PIDS" | grep -E "^(tor|privoxy) [1-9][0-9]*$" > /dev/null || (echo "❌ tor/privoxy not running unprivileged" && exit 1)
echo "$PIDS" | grep -E "^python3 [1-9][0-9]*$" > /dev/null || (echo "❌ API not running unprivileged" && exit 1)
if echo "$PIDS" | grep -E "^(tor|privoxy|python3) 0$" > /dev/null; then
  echo "❌ CRITICAL SECURITY ERROR: a daemon is running as root (UID 0)!"
  exit 1
fi
echo "✅ All daemons run as unprivileged users."

echo "=== 2. Daemon Process Verification ==="
PROCS=$(docker top "$CONTAINER_NAME")
echo "$PROCS"
echo "$PROCS" | grep -q "tor" || (echo "❌ tor daemon is not running" && exit 1)
echo "$PROCS" | grep -q "privoxy" || (echo "❌ privoxy is not running" && exit 1)
echo "$PROCS" | grep -q "python3" || (echo "❌ API process is not running" && exit 1)
echo "✅ Daemons verified (tor, privoxy, api)."

echo "=== 3. REST API Contract Verification ==="
# Test /status
STATUS_RESP=$(curl -fsS "http://localhost:${API_PORT}/status")
echo "/status response: $STATUS_RESP"
echo "$STATUS_RESP" | jq -e '.status' >/dev/null
echo "$STATUS_RESP" | jq -e 'if .status == "connected" then .ip else .detail end' >/dev/null

# Test /health
HEALTH_RESP=$(curl -fsS "http://localhost:${API_PORT}/health")
echo "/health response: $HEALTH_RESP"
echo "$HEALTH_RESP" | jq -e '.status' >/dev/null
echo "$HEALTH_RESP" | jq -e '.tor.network_enabled' >/dev/null
echo "$HEALTH_RESP" | jq -e '.proxies' >/dev/null

# Test /reconnect (POST)
RECONN_RESP=$(curl -fsS -X POST "http://localhost:${API_PORT}/reconnect")
echo "/reconnect response: $RECONN_RESP"
echo "$RECONN_RESP" | jq -e '.action == "reconnect" and .status == "success"' >/dev/null

# Test /diagnostics
DIAG_RESP=$(curl -fsS "http://localhost:${API_PORT}/diagnostics")
echo "$DIAG_RESP" | jq -e '.uptime_seconds >= 0' >/dev/null
echo "$DIAG_RESP" | jq -e '.tor.network_enabled' >/dev/null

# Test /metrics
METRICS_RESP=$(curl -fsS "http://localhost:${API_PORT}/metrics")
echo "$METRICS_RESP" | grep -q "torproxy_uptime_seconds"
echo "$METRICS_RESP" | grep -q "torproxy_reconnect_total"

# Test legacy GET mutation compatibility
LEGACY_RESP=$(curl -fsS "http://localhost:${API_PORT}/reconnect")
echo "legacy GET /reconnect response: $LEGACY_RESP"
echo "$LEGACY_RESP" | jq -e '.action == "reconnect" and .status == "success"' >/dev/null
echo "✅ REST API contracts verified."

echo "=== 3b. MCP Server Verification ==="
# Test MCP Stdio ping & tools/list
MCP_STDIO_RESP=$(echo '{"jsonrpc":"2.0","id":1,"method":"ping"}' | docker exec -i "$CONTAINER_NAME" python3 -m torproxy mcp 2>/dev/null)
echo "MCP stdio ping response: $MCP_STDIO_RESP"
echo "$MCP_STDIO_RESP" | jq -e '.result == {}' >/dev/null

MCP_TOOLS_RESP=$(echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | docker exec -i "$CONTAINER_NAME" python3 -m torproxy mcp 2>/dev/null)
echo "$MCP_TOOLS_RESP" | jq -e '.result.tools | map(.name) | contains(["torproxy_fetch", "torproxy_status", "torproxy_reconnect"])' >/dev/null

# Test MCP SSE endpoint on internal port 2501
SSE_ENDPOINT_RESP=$(docker exec "$CONTAINER_NAME" curl -fsS --max-time 3 http://127.0.0.1:2501/sse 2>/dev/null | head -n 2 || true)
echo "MCP SSE endpoint response: $SSE_ENDPOINT_RESP"
echo "$SSE_ENDPOINT_RESP" | grep -q "event: endpoint"
echo "✅ MCP Server (stdio & SSE port 2501) verified."

echo "=== 4. SOCKS5 Handshake Verification ==="
# Send RFC1928 greeting: \x05\x01\x00 (Version 5, 1 auth method, NO AUTH)
# Response must be \x05\x00
if command -v xxd >/dev/null 2>&1 && command -v nc >/dev/null 2>&1; then
  SOCKS_GREETING=$(printf '\x05\x01\x00' | nc -w 3 127.0.0.1 "$SOCKS_PORT" | xxd -p | tr -d '\n' || true)
else
  SOCKS_GREETING=$(python3 -c "import socket; s = socket.socket(); s.connect(('127.0.0.1', $SOCKS_PORT)); s.sendall(b'\x05\x01\x00'); print(s.recv(2).hex())" 2>/dev/null || true)
fi
echo "SOCKS5 raw greeting response hex: $SOCKS_GREETING"
if [ "$SOCKS_GREETING" != "0500" ]; then
  echo "❌ SOCKS5 handshake failed: expected 0500, got '$SOCKS_GREETING'"
  exit 1
fi
echo "✅ SOCKS5 greeting handshake verified on port $SOCKS_PORT."

echo "=== 5. Fail-Closed & Leak Prevention Verification ==="
# Disconnect Tor network
curl -fsS -X POST "http://localhost:${API_PORT}/disconnect" >/dev/null
DISC_HEALTH=$(curl -fsS "http://localhost:${API_PORT}/health")
echo "$DISC_HEALTH" | jq -e '.status == "disconnected" and .tor.network_enabled == false' >/dev/null

# Check Privoxy: must fail-closed, NEVER bypass to clearnet
PRIVOXY_LEAK=false
if curl -sS --max-time 3 --proxy "http://127.0.0.1:${HTTP_PORT}" http://example.com >/dev/null 2>&1; then
  # If curl succeeds, check if it returned a Privoxy error page or actually connected
  PAGE_OUTPUT=$(curl -sS --max-time 3 --proxy "http://127.0.0.1:${HTTP_PORT}" http://example.com 2>&1 || true)
  if echo "$PAGE_OUTPUT" | grep -qi "Privoxy\|500\|503"; then
    echo "✅ Privoxy returned expected error page when Tor disconnected."
  else
    echo "❌ CRITICAL: Privoxy forwarded traffic while Tor was disconnected (LEAK)!"
    PRIVOXY_LEAK=true
  fi
else
  echo "✅ Privoxy refused connection/failed closed when Tor disconnected."
fi

if [ "$PRIVOXY_LEAK" = "true" ]; then
  exit 1
fi

# Restore network
curl -fsS -X POST "http://localhost:${API_PORT}/connect" >/dev/null
RESTORE_HEALTH=$(curl -fsS "http://localhost:${API_PORT}/health")
echo "$RESTORE_HEALTH" | jq -e '.tor.network_enabled == true' >/dev/null
echo "✅ Fail-closed and network restore verified."

echo "=== All Container Smoke & Integration Tests PASSED! ==="
