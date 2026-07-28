#!/usr/bin/env bash
set -Eeuo pipefail

validate_configuration() {
  if [[ ! "$TORPROXY_LISTEN_ADDRESS" =~ ^[0-9.]+$ ]]; then
    echo "TORPROXY_LISTEN_ADDRESS must be an IPv4 address." >&2
    exit 1
  fi

  if [[ ! "$TORPROXY_LISTEN_PORT" =~ ^[0-9]+$ ]] \
    || (( TORPROXY_LISTEN_PORT < 1 || TORPROXY_LISTEN_PORT > 65535 )); then
    echo "TORPROXY_LISTEN_PORT must be an integer between 1 and 65535." >&2
    exit 1
  fi

  if [[ ! "$TORPROXY_API_PORT" =~ ^[0-9]+$ ]] \
    || (( TORPROXY_API_PORT < 1 || TORPROXY_API_PORT > 65535 )); then
    echo "TORPROXY_API_PORT must be an integer between 1 and 65535." >&2
    exit 1
  fi

  if [[ ! "$TORPROXY_SOCKS_PORT" =~ ^[0-9]+$ ]] \
    || (( TORPROXY_SOCKS_PORT < 1 || TORPROXY_SOCKS_PORT > 65535 )); then
    echo "TORPROXY_SOCKS_PORT must be an integer between 1 and 65535." >&2
    exit 1
  fi
}

shutdown() {
  kill -TERM "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" 2>/dev/null || true
  wait "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" 2>/dev/null || true
}

trap shutdown EXIT

validate_configuration
sed \
  -e "s|__TORPROXY_LISTEN_ADDRESS__|$TORPROXY_LISTEN_ADDRESS|" \
  -e "s|__TORPROXY_LISTEN_PORT__|$TORPROXY_LISTEN_PORT|" \
  /etc/privoxy/config.template > /tmp/privoxy.config

sed \
  -e "s|__TORPROXY_SOCKS_PORT__|$TORPROXY_SOCKS_PORT|" \
  /etc/tor/torrc > /tmp/torrc

tor -f /tmp/torrc &
tor_pid=$!

privoxy --no-daemon /tmp/privoxy.config &
privoxy_pid=$!

python3 /usr/local/bin/api.py &
api_pid=$!

# Exit as soon as any critical process exits. tini forwards signals and
# terminates the remaining process group during container shutdown.
wait -n "$tor_pid" "$privoxy_pid" "$api_pid"
