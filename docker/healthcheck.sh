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
curl --fail --silent --show-error \
  --connect-timeout 2 --max-time 5 \
  "http://127.0.0.1:${TORPROXY_API_PORT}/status" \
  | grep -Eq '"status"[[:space:]]*:[[:space:]]*"connected"'
