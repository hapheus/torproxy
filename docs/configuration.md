# Configuration Reference

This guide provides the complete configuration reference for `torproxy`, including environment variables, configuration files, network exposure, and process lifecycle management.

## 1. Environment Variables

All settings have sensible defaults that allow running `torproxy` with zero configuration. When running via Docker Compose or `docker run`, settings can be customized using environment variables.

| Variable | Default | Type | Description |
|---|---|---|---|
| `TORPROXY_LISTEN_ADDRESS` | `0.0.0.0` | IPv4 address | Address inside the container that Privoxy binds to. Set to `0.0.0.0` to permit container-to-container connections. |
| `TORPROXY_LISTEN_PORT` | `8118` | Integer (1–65535) | TCP port inside the container where the Privoxy HTTP proxy listens. |
| `TORPROXY_API_PORT` | `8080` | Integer (1–65535) | TCP port inside the container where the Python REST API server listens. |
| `TORPROXY_SOCKS_PORT` | `9050` | Integer (1–65535) | TCP port inside the container where Tor's SOCKS5 proxy listens. |
| `TORPROXY_HOST_PORT` | `8118` | Integer (1–65535) | Host port mapped to `TORPROXY_LISTEN_PORT` in the default `docker-compose.yml`. |
| `TORPROXY_COUNTRY` | *(unset)* | Comma-separated ISO codes | 2-letter ISO 3166-1 alpha-2 codes (e.g. `DE`, `AT`, `US`, `DE,AT`) to route exit traffic. |
| `TORPROXY_STRICT_NODES` | `0` | Boolean (`0`, `1`, `true`, `false`) | When `1`/`true`, strictly reject circuits if no exit relays in selected countries exist. |

---

## 2. Configuration Mechanisms

### Docker Compose (.env file)
Create a `.env` file in the same directory as `docker-compose.yml`:
```dotenv
TORPROXY_HOST_PORT=8118
TORPROXY_LISTEN_ADDRESS=0.0.0.0
TORPROXY_LISTEN_PORT=8118
TORPROXY_API_PORT=8080
TORPROXY_SOCKS_PORT=9050
TORPROXY_COUNTRY=DE
TORPROXY_STRICT_NODES=0
```

### Docker Run CLI Flags
Pass environment variables directly using the `-e` flag:
```sh
docker run -d --name torproxy --restart unless-stopped \
  -e TORPROXY_COUNTRY=DE \
  -e TORPROXY_LISTEN_PORT=8118 \
  -e TORPROXY_API_PORT=8080 \
  -e TORPROXY_SOCKS_PORT=9050 \
  -p 127.0.0.1:8118:8118 \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:9050:9050 \
  hapheus/torproxy:latest
```

---

## 3. Template Rendering & Startup Flow

When the container launches, `/usr/local/bin/start.sh` executes the following sequence:

1. **Validation:** Checks that `TORPROXY_LISTEN_ADDRESS` has 4 valid octets (0–255), all ports are integers (1–65535), no port conflicts exist between Privoxy, API, and SOCKS5, and `TORPROXY_COUNTRY` contains valid 2-letter ISO codes.
2. **Template Substitution:**
   - Replaces `__TORPROXY_LISTEN_ADDRESS__`, `__TORPROXY_LISTEN_PORT__`, and `__TORPROXY_SOCKS_PORT__` in `/etc/privoxy/config.template` and writes `/tmp/privoxy.config`.
   - Replaces `__TORPROXY_SOCKS_PORT__` in `/etc/tor/torrc` and appends `ExitNodes` and `StrictNodes` directives if configured, writing `/tmp/torrc`.
3. **Daemon Launch:**
   - Launches `tor -f /tmp/torrc` in the background.
   - Launches `privoxy --no-daemon /tmp/privoxy.config` in the background.
   - Launches `python3 /usr/local/bin/api.py` in the background.
4. **Supervision:** Executes `wait -n "$tor_pid" "$privoxy_pid" "$api_pid"`. If any of the three services fails, the script exits immediately, causing `tini` to terminate the container.

---

## 4. Network Exposure & Security Boundaries

- **Host Loopback Only:** By default, Docker Compose exposes ports `8118`, `8080`, and `9050` bound exclusively to `127.0.0.1`. Never expose these ports to `0.0.0.0` or public internet interfaces without an authenticating reverse proxy.
- **Docker Network Isolation:** Containers within the same Docker network can communicate with `torproxy` using the service hostname `torproxy` (e.g. `http://torproxy:8118`). Shipped examples do not publish the management API to host ports.
- **Tor Control Port (`9051`):** Bound strictly to `127.0.0.1:9051` inside the container. It is authenticated via `CookieAuthentication 1` (`/var/lib/tor/control_auth_cookie`) and is never exposed outside the container boundary.

---

## 5. Country-Specific Exit Nodes (GeoIP Routing)

`torproxy` bundles the Tor GeoIP database (`/usr/share/tor/geoip` and `/usr/share/tor/geoip6`) allowing exit node country routing.

### Static Startup Configuration
Specify `TORPROXY_COUNTRY` with comma-separated ISO 3166-1 alpha-2 codes:
- `TORPROXY_COUNTRY=DE` (Germany only)
- `TORPROXY_COUNTRY=AT,CH` (Austria or Switzerland)
- `TORPROXY_STRICT_NODES=1` (Strict mode: refuse circuits if no nodes in requested country exist)

### Dynamic Runtime Configuration via REST API
The exit country can be changed on the fly without restarting the container:
```sh
# Switch exit country to Germany on circuit rotation
curl -X POST "http://127.0.0.1:8080/reconnect?country=DE"

# Switch with strict nodes policy via JSON payload
curl -X POST http://127.0.0.1:8080/reconnect \
  -H "Content-Type: application/json" \
  -d '{"country": "AT", "strict_nodes": true}'

# Clear country restriction (return to default random routing)
curl -X POST "http://127.0.0.1:8080/reconnect?country=any"
```
Dynamic changes are applied via Tor Control Protocol (`SETCONF ExitNodes=...`) and immediately take effect for new circuits. Active configuration is surfaced in `/health`, `/diagnostics`, and `/metrics`.
