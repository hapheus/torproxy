#!/usr/bin/env bash
set -Eeuo pipefail

mcp_mode=0
if [ "${1:-}" = "mcp" ] || { [ "${1:-}" = "torproxy" ] && [ "${2:-}" = "mcp" ]; }; then
  mcp_mode=1
  # Preserve original stdout on FD 3 for JSON-RPC while routing all daemon logs to stderr.
  exec 3>&1 1>&2
fi

validate_configuration() {
  python3 -m torproxy.runtime.configure --check
}

shutdown() {
  echo "[start.sh] Shutting down child processes (Tor, Privoxy, API)..." >&2
  kill -TERM "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" "${geoip_pid:-}" 2>/dev/null || true
  wait "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" "${geoip_pid:-}" 2>/dev/null || true
}

trap shutdown SIGTERM SIGINT EXIT

validate_configuration
python3 -m torproxy.runtime.configure
python3 -m torproxy.runtime.gateway

# ISSUE-03: start.sh runs as root only to drop privileges. Every daemon
# runs as an unprivileged user so the netfilter WAN bypass (owner
# --uid-owner tor) grants least privilege.
su tor -s /bin/sh -c 'exec tor -f /tmp/torrc' &
tor_pid=$!

# Tor (running as 'tor') creates a 0600 control cookie; make it
# group-readable for the API, which runs as 'torproxy'. The fixups run
# as 'tor' (the file owner) so they also work under cap-drop hardening.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -f /var/lib/tor/control_auth_cookie ] && break
  sleep 1
done
# Tor locks its DataDirectory to 0700 at startup; restore group traverse
# so the API (group torproxy) can read the cookie file.
su tor -s /bin/sh -c 'chgrp torproxy /var/lib/tor/control_auth_cookie' 2>/dev/null || true
su tor -s /bin/sh -c 'chmod 640 /var/lib/tor/control_auth_cookie' 2>/dev/null || true
su tor -s /bin/sh -c 'chmod 0750 /var/lib/tor' 2>/dev/null || true

su privoxy -s /bin/sh -c 'exec privoxy --no-daemon /tmp/privoxy.config' &
privoxy_pid=$!

if [ "$mcp_mode" -eq 1 ]; then
  su torproxy -s /bin/sh -c 'exec torproxy mcp' >&3 3>&-
  exit $?
fi

su torproxy -s /bin/sh -c 'exec python3 -m torproxy' &
api_pid=$!

# ISSUE-20: optional periodic GeoIP refresh (opt-in, fallback-safe).
geoip_pid=""
if [ "${TORPROXY_GEOIP_AUTO_UPDATE:-0}" = "1" ] || [ "${TORPROXY_GEOIP_AUTO_UPDATE:-}" = "true" ] || [ "${TORPROXY_GEOIP_AUTO_UPDATE:-}" = "yes" ]; then
  python3 -m torproxy.runtime.geoip --loop &
  geoip_pid=$!
fi

# Exit as soon as any critical process exits. tini forwards signals and
# terminates the remaining process group during container shutdown.
wait -n "$tor_pid" "$privoxy_pid" "$api_pid"
