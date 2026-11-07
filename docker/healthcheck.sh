#!/bin/sh
set -eu

# ISSUE-06: the healthcheck must not depend on any external domain.
# `config.privoxy.org` was removed: an external outage/rate-limit must not
# mark a healthy Tor container unhealthy. Both probes below are loopback-only.

# 1. Verify that Privoxy accepts a TCP connection on loopback.
# Pure loopback probe: no external network traffic, no DNS resolution.
curl --silent --show-error --connect-only \
  --connect-timeout 2 --max-time 5 \
  "http://127.0.0.1:${TORPROXY_LISTEN_PORT}/" \
  >/dev/null 2>&1 || exit 1

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
