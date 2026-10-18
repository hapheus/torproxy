#!/usr/bin/env bash
set -Eeuo pipefail

validate_configuration() {
  if [[ -z "${TORPROXY_LISTEN_ADDRESS:-}" ]]; then
    echo "TORPROXY_LISTEN_ADDRESS cannot be empty." >&2
    exit 1
  fi

  local IFS='.'
  # shellcheck disable=SC2206
  local octets=($TORPROXY_LISTEN_ADDRESS)
  if [[ ${#octets[@]} -ne 4 ]]; then
    echo "TORPROXY_LISTEN_ADDRESS must be a valid IPv4 address (found '$TORPROXY_LISTEN_ADDRESS')." >&2
    exit 1
  fi
  for octet in "${octets[@]}"; do
    if [[ ! "$octet" =~ ^(0|[1-9][0-9]*)$ ]] || (( octet < 0 || octet > 255 )); then
      echo "TORPROXY_LISTEN_ADDRESS must be a valid IPv4 address with octets between 0 and 255 (found '$TORPROXY_LISTEN_ADDRESS')." >&2
      exit 1
    fi
  done

  for var_name in TORPROXY_LISTEN_PORT TORPROXY_API_PORT TORPROXY_SOCKS_PORT; do
    local port_val="${!var_name:-}"
    if [[ ! "$port_val" =~ ^[0-9]+$ ]] || (( port_val < 1 || port_val > 65535 )); then
      echo "$var_name must be an integer between 1 and 65535 (found '${port_val}')." >&2
      exit 1
    fi
  done

  if [[ "$TORPROXY_LISTEN_PORT" -eq "$TORPROXY_API_PORT" ]] || \
     [[ "$TORPROXY_LISTEN_PORT" -eq "$TORPROXY_SOCKS_PORT" ]] || \
     [[ "$TORPROXY_API_PORT" -eq "$TORPROXY_SOCKS_PORT" ]]; then
    echo "Configuration error: TORPROXY_LISTEN_PORT ($TORPROXY_LISTEN_PORT), TORPROXY_API_PORT ($TORPROXY_API_PORT), and TORPROXY_SOCKS_PORT ($TORPROXY_SOCKS_PORT) must all be distinct ports." >&2
    exit 1
  fi
}

shutdown() {
  echo "[start.sh] Shutting down child processes (Tor, Privoxy, API)..." >&2
  kill -TERM "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" 2>/dev/null || true
  wait "${tor_pid:-}" "${privoxy_pid:-}" "${api_pid:-}" 2>/dev/null || true
}

trap shutdown SIGTERM SIGINT EXIT

validate_configuration
sed \
  -e "s|__TORPROXY_LISTEN_ADDRESS__|$TORPROXY_LISTEN_ADDRESS|" \
  -e "s|__TORPROXY_LISTEN_PORT__|$TORPROXY_LISTEN_PORT|" \
  -e "s|__TORPROXY_SOCKS_PORT__|$TORPROXY_SOCKS_PORT|" \
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
