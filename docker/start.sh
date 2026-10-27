#!/usr/bin/env bash
set -Eeuo pipefail

validate_configuration() {
  python3 -m torproxy.runtime.configure --check
}

shutdown() {
  echo "[start.sh] Shutting down child processes (Tor, Privoxy, API)..." >&2
  kill -TERM "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" 2>/dev/null || true
  wait "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" 2>/dev/null || true
}

trap shutdown SIGTERM SIGINT EXIT

validate_configuration
python3 -m torproxy.runtime.configure

tor -f /tmp/torrc &
tor_pid=$!

privoxy --no-daemon /tmp/privoxy.config &
privoxy_pid=$!

python3 -m torproxy &
api_pid=$!

# Exit as soon as any critical process exits. tini forwards signals and
# terminates the remaining process group during container shutdown.
wait -n "$tor_pid" "$privoxy_pid" "$api_pid"
