#!/bin/sh
set -eu

# 1. Verify that Privoxy accepts and processes a local proxy request.
# config.privoxy.org may return an HTTP error when its templates are not
# available beside the runtime-generated config, so only test connectivity.
# This generates zero external network traffic.
curl --silent --show-error --output /dev/null \
  --proxy "http://127.0.0.1:${TORPROXY_LISTEN_PORT}" \
  --connect-timeout 2 --max-time 5 \
  http://config.privoxy.org/

# 2. Check if the local REST API is responding with a 'connected' status.
AUTH_HEADER=""
if [ -n "${TORPROXY_API_TOKEN:-}" ]; then
  AUTH_HEADER="Authorization: Bearer ${TORPROXY_API_TOKEN}"
elif [ -n "${TORPROXY_API_KEY:-}" ]; then
  AUTH_HEADER="X-API-Key: ${TORPROXY_API_KEY}"
fi

if [ -n "$AUTH_HEADER" ]; then
  curl --fail --silent --show-error \
    --connect-timeout 2 --max-time 5 \
    -H "$AUTH_HEADER" \
    "http://127.0.0.1:${TORPROXY_API_PORT}/status" \
    | grep -Eq '"status"[[:space:]]*:[[:space:]]*"connected"'
else
  curl --fail --silent --show-error \
    --connect-timeout 2 --max-time 5 \
    "http://127.0.0.1:${TORPROXY_API_PORT}/status" \
    | grep -Eq '"status"[[:space:]]*:[[:space:]]*"connected"'
fi
