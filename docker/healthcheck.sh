#!/bin/sh
set -eu

exec curl --fail --silent --show-error \
  --proxy "http://127.0.0.1:${TORPROXY_LISTEN_PORT}" \
  --connect-timeout 5 --max-time 10 \
  https://check.torproject.org/api/ip
