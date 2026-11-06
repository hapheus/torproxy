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
python3 -m torproxy.runtime.gateway

# ISSUE-03: start.sh runs as root only to drop privileges. Every daemon
# runs as an unprivileged user so the netfilter WAN bypass (owner
# --uid-owner tor) grants least privilege.
su tor -s /bin/sh -c 'exec tor -f /tmp/torrc' &
tor_pid=$!

# Tor (running as 'tor') creates a 0600 control cookie; make it
# group-readable for the API, which runs as 'torproxy'.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -f /var/lib/tor/control_auth_cookie ] && break
  sleep 1
done
# Tor locks its DataDirectory to 0700 at startup; restore group traverse
# so the API (group torproxy) can read the cookie file.
chmod 0750 /var/lib/tor 2>/dev/null || true
chgrp torproxy /var/lib/tor/control_auth_cookie 2>/dev/null || true
chmod 640 /var/lib/tor/control_auth_cookie 2>/dev/null || true

su privoxy -s /bin/sh -c 'exec privoxy --no-daemon /tmp/privoxy.config' &
privoxy_pid=$!

su torproxy -s /bin/sh -c 'exec python3 -m torproxy' &
api_pid=$!

# Exit as soon as any critical process exits. tini forwards signals and
# terminates the remaining process group during container shutdown.
wait -n "$tor_pid" "$privoxy_pid" "$api_pid"
