# torproxy

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/hapheus/torproxy)](https://hub.docker.com/r/hapheus/torproxy)
[![Architectures](https://img.shields.io/badge/arch-amd64%20%7C%20arm64%20%7C%20arm%2Fv7-blue)](https://hub.docker.com/r/hapheus/torproxy)
[![Non-Root: Enforced](https://img.shields.io/badge/Security-Non--Root-brightgreen)](https://github.com/hapheus/torproxy)
[![Fail-Closed](https://img.shields.io/badge/Protection-Fail--Closed-success)](https://github.com/hapheus/torproxy)
[![OpenSSF Best Practices](https://img.shields.io/cii/percentage/15828?logo=linuxfoundation&label=OpenSSF%20Best%20Practices)](https://www.bestpractices.dev/projects/15828)

**Production-grade, leak-proof Tor HTTP and SOCKS5 proxy packaged for Docker.**
Route entire container networks with zero application changes, connect AI coding assistants (Claude Desktop, Cursor) via built-in MCP, and rotate circuits dynamically via REST.

Source repository: [https://github.com/hapheus/torproxy](https://github.com/hapheus/torproxy)

---

## ⚡ Core Value & Features

- **🛡️ Zero Clearnet Leaks:** True fail-closed protection. If Tor disconnects, Privoxy and the netfilter kill-switch immediately drop traffic (HTTP 503) — your real IP is never exposed.
- **🚀 Transparent Tor Gateway:** Attach any container via `network_mode: "service:torproxy"` to tunnel all outbound TCP & DNS through Tor automatically — zero app proxy flags or code changes.
- **🤖 Native AI Agent MCP Server:** Built-in Model Context Protocol server on port `2501` (SSE) and via Stdio (`torproxy mcp`) for seamless Claude Desktop, Cursor, and Antigravity integration.
- **🔄 Dynamic Circuit Rotation:** Rotate Tor identities (`SIGNAL NEWNYM`) or switch exit countries on the fly without container restarts via the REST API (`:8080`).
- **🔒 Hardened Non-Root Security:** Daemons run strictly under an unprivileged user (`torproxy`), with authenticated loopback Tor ControlPort.
- **🌍 Country-Specific Routing:** Select Tor exit relays by country (e.g. `TORPROXY_COUNTRY=DE` or `DE,AT`) backed by built-in `tor-geoipdb`.
- **📦 Multi-Architecture:** Built natively for `linux/amd64`, `linux/arm64`, and `linux/arm/v7`.

---

## 🚀 Quick Start

### Recommended: Docker Compose

Create a `docker-compose.yml`:

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    container_name: torproxy
    restart: unless-stopped
    ports:
      - "127.0.0.1:8118:8118"   # HTTP/HTTPS proxy (Privoxy)
      - "127.0.0.1:9050:9050"   # SOCKS5 proxy (Tor)
      - "127.0.0.1:8080:8080"   # REST API & Health status
```

Launch the proxy:
```bash
docker compose up -d
```

### Alternative: Docker Run (Single Command)

```bash
docker run -d \
  --name torproxy \
  --restart unless-stopped \
  -p 127.0.0.1:8118:8118 \
  -p 127.0.0.1:9050:9050 \
  -p 127.0.0.1:8080:8080 \
  hapheus/torproxy:latest
```

---

## 🧪 Verifying Tor Connectivity

Wait a few seconds for Tor to finish bootstrapping, then test:

```bash
# 1. Test HTTP proxy via Privoxy (port 8118)
curl --proxy http://127.0.0.1:8118 https://check.torproject.org/api/ip

# 2. Test SOCKS5 proxy with remote DNS resolution (port 9050)
curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip

# 3. Check live connection status via REST API (port 8080)
curl -s http://127.0.0.1:8080/status | jq .

# 4. Request a new Tor identity / circuit on demand
curl -X POST http://127.0.0.1:8080/reconnect

# 5. Dynamically switch exit country without restarting
curl -X POST "http://127.0.0.1:8080/reconnect?country=DE"
```

> [!IMPORTANT]
> **Leak-Proof Guarantee (Fail-Closed):** If Tor fails or disconnects, `torproxy` fails closed immediately. It will **never** fall back to direct clearnet routing.

---

## 🌟 Popular Modes & Use Cases

### 1. Transparent Gateway (Zero-Config Routing for Any Container)

Route another container's entire network traffic (TCP + DNS) through Tor without setting proxy flags:

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    pull_policy: always
    cap_add:
      - NET_ADMIN
    environment:
      TORPROXY_GATEWAY_MODE: "true"
    restart: unless-stopped

  # Any container attached to torproxy's network stack is automatically anonymized:
  scraper:
    image: curlimages/curl:latest
    network_mode: "service:torproxy"
    depends_on:
      torproxy:
        condition: service_healthy
    command: ["-s", "https://check.torproject.org/api/ip"]
```

### 2. AI Coding Assistants (Model Context Protocol / MCP)

Connect **Claude Desktop** directly via Docker Stdio without exposing host ports:

```json
{
  "mcpServers": {
    "torproxy": {
      "command": "docker",
      "args": ["exec", "-i", "torproxy", "torproxy", "mcp"]
    }
  }
}
```

Or connect **Cursor** / **Antigravity** via HTTP/SSE (`http://127.0.0.1:2501/sse`).

### 3. Country-Specific Exit Proxy

Route traffic exclusively through specific countries:

```bash
docker run -d \
  --name torproxy \
  --restart unless-stopped \
  -e TORPROXY_COUNTRY=DE,AT \
  -p 127.0.0.1:8118:8118 \
  -p 127.0.0.1:9050:9050 \
  -p 127.0.0.1:8080:8080 \
  hapheus/torproxy:latest
```

---

## REST API Reference

The management API listens on port `8080` (HTTP):

| Endpoint | Methods | Description |
| -------- | ------- | ----------- |
| `/status` | `GET` | Tor bootstrap and current verified egress IP address. |
| `/ip` | `GET` | Current verified Tor egress IP address. |
| `/health` | `GET` | Multi-subsystem health check (`tor`, `proxies`, `egress`). Returns HTTP 200 when healthy, 503 during bootstrap/errors. |
| `/diagnostics` | `GET` | Uptime, reconnect counters, bootstrap details, and cache status. |
| `/metrics` | `GET` | Prometheus exposition format metrics. |
| `/reconnect` | `POST` (or `GET`) | Triggers `SIGNAL NEWNYM` to establish a new circuit. Supports `?country=DE` query or JSON body. |
| `/disconnect` | `POST` (or `GET`) | Disables Tor network traffic (`SETCONF DisableNetwork=1`). |
| `/connect` | `POST` (or `GET`) | Re-enables Tor network traffic (`SETCONF DisableNetwork=0`). Supports `?country=DE` query or JSON body. |

> [!WARNING]
> The management API is unauthenticated by default. Bind it strictly to `127.0.0.1` or place it behind an authenticating reverse proxy if exposed across networks.

---

## Configuration & Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `TORPROXY_LISTEN_ADDRESS` | `0.0.0.0` | Bind address for Privoxy and Tor inside the container. |
| `TORPROXY_LISTEN_PORT` | `8118` | Privoxy HTTP proxy port. |
| `TORPROXY_SOCKS_PORT` | `9050` | Tor SOCKS5 proxy port. |
| `TORPROXY_API_PORT` | `8080` | REST API port. |
| `TORPROXY_COUNTRY` | *(unset)* | Comma-separated ISO 3166-1 alpha-2 codes (e.g. `DE`, `AT`, `US`, `DE,AT`) to restrict exit nodes. |
| `TORPROXY_STRICT_NODES` | `0` | If `1`/`true`, refuse circuits if nodes in the requested country/countries are unavailable. |

---

## Production Hardening

For maximum security in production, run with a read-only root filesystem and drop all Linux capabilities:

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    restart: unless-stopped
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=32M
      - /run:rw,noexec,nosuid,size=16M
      - /var/lib/tor:rw,noexec,nosuid,size=64M
      - /var/log/privoxy:rw,noexec,nosuid,size=16M
    ports:
      - "127.0.0.1:8118:8118"
      - "127.0.0.1:9050:9050"
      - "127.0.0.1:8080:8080"
```

---

## License

This project is licensed under the [MIT License](https://github.com/hapheus/torproxy/blob/main/LICENSE).
