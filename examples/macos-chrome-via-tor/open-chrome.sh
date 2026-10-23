#!/usr/bin/env bash
# ==============================================================================
# Open Google Chrome in an isolated profile routed strictly via torproxy
# ==============================================================================
set -euo pipefail

PROXY_HOST="${TORPROXY_HOST:-127.0.0.1}"
PROXY_PORT="${TORPROXY_PORT:-8118}"
TARGET_URL="${1:-https://check.torproject.org}"
PROFILE_DIR="${TORPROXY_PROFILE_DIR:-$(mktemp -d -t torproxy-chrome-XXXXXX)}"

# Verify torproxy is reachable
if ! curl -s --connect-timeout 2 "http://${PROXY_HOST}:${PROXY_PORT}" >/dev/null 2>&1 && \
   ! curl -s --connect-timeout 2 "http://${PROXY_HOST}:8080/health" >/dev/null 2>&1; then
  echo "⚠️  Warning: torproxy does not appear to be running on ${PROXY_HOST}:${PROXY_PORT}." >&2
  echo "   Start it first in this directory with: docker compose up -d" >&2
fi

# Detect available browser application on macOS
BROWSER_APP=""
if [ -d "/Applications/Google Chrome.app" ]; then
  BROWSER_APP="Google Chrome"
elif [ -d "/Applications/Brave Browser.app" ]; then
  BROWSER_APP="Brave Browser"
elif [ -d "/Applications/Chromium.app" ]; then
  BROWSER_APP="Chromium"
fi

if [ -z "$BROWSER_APP" ]; then
  echo "❌ Error: Neither Google Chrome, Brave Browser, nor Chromium was found in /Applications." >&2
  echo "   Please install Google Chrome or specify your browser." >&2
  exit 1
fi

echo "🚀 Opening $BROWSER_APP in isolated profile routed via http://${PROXY_HOST}:${PROXY_PORT}..."
open -na "$BROWSER_APP" --args \
  --user-data-dir="$PROFILE_DIR" \
  --incognito \
  --no-first-run \
  --no-default-browser-check \
  --proxy-server="http://${PROXY_HOST}:${PROXY_PORT}" \
  "$TARGET_URL"

echo "✅ Browser launched with isolated profile ($PROFILE_DIR)"
echo "🌐 Verifying target: $TARGET_URL"
echo "💡 To request a new Tor identity, run:"
echo "   curl -s -X POST http://${PROXY_HOST}:8080/reconnect"
