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
```

### Docker Run CLI Flags
Pass environment variables directly using the `-e` flag:
```sh
docker run -d --name torproxy --restart unless-stopped \
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

1. **Validation:** Checks that `TORPROXY_LISTEN_ADDRESS` has 4 valid octets (0–255), all ports are integers (1–65535), and no port conflicts exist between Privoxy, API, and SOCKS5.
2. **Template Substitution:**
   - Replaces `__TORPROXY_LISTEN_ADDRESS__`, `__TORPROXY_LISTEN_PORT__`, and `__TORPROXY_SOCKS_PORT__` in `/etc/privoxy/config.template` and writes `/tmp/privoxy.config`.
   - Replaces `__TORPROXY_SOCKS_PORT__` in `/etc/tor/torrc` and writes `/tmp/torrc`.
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
