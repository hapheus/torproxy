# torproxy

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/hapheus/torproxy)](https://hub.docker.com/r/hapheus/torproxy)
[![Architectures](https://img.shields.io/badge/arch-amd64%20%7C%20arm64%20%7C%20arm%2Fv7-blue)](https://hub.docker.com/r/hapheus/torproxy)

A lightweight, secure, and production-ready Docker container combining **Tor**, **Privoxy** (HTTP/HTTPS proxy), **SOCKS5**, and a local **REST control API**.

Source repository: [https://github.com/hapheus/torproxy](https://github.com/hapheus/torproxy)

---

## Key Features

- **HTTP/HTTPS Proxy (Port 8118)**: Powered by Privoxy, automatically resolving DNS lookups through Tor exit relays to prevent DNS leaks.
- **SOCKS5 Proxy (Port 9050)**: Standard Tor SOCKS5 interface supporting remote hostname resolution (`socks5h://`).
- **REST Control API (Port 8080)**: Inspect circuit status, trigger circuit rotation (`/reconnect`), query health diagnostics, and pull Prometheus metrics.
- **Fail-Closed Security**: Privoxy strictly routes to Tor SOCKS5; if Tor circuits drop, proxy requests fail immediately (500/503) rather than leaking to clearnet.
- **Authenticated Tor Control**: Local Tor ControlPort is secured using ephemeral 32-byte filesystem cookie authentication.
- **Non-Root Execution**: Runs under a dedicated, unprivileged system user (`torproxy`), never as root.
- **Multi-Architecture**: Built natively for `linux/amd64`, `linux/arm64`, and `linux/arm/v7`.
- **Zero Breaking Changes**: Guaranteed backward compatibility across minor releases.

---

## Quick Start

### Option 1: Docker Run

```bash
docker run -d \
  --name torproxy \
  --restart unless-stopped \
  -p 127.0.0.1:8118:8118 \
  -p 127.0.0.1:9050:9050 \
  -p 127.0.0.1:8080:8080 \
  hapheus/torproxy:latest
```

### Option 2: Docker Compose

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    container_name: torproxy
    restart: unless-stopped
    ports:
      - "127.0.0.1:8118:8118"
      - "127.0.0.1:9050:9050"
      - "127.0.0.1:8080:8080"
```

---

## Verifying Tor Connectivity

Wait a few seconds for Tor to bootstrap, then test:

```bash
# 1. Check REST API status
curl -s http://127.0.0.1:8080/status | jq .

# 2. Test HTTP proxy via Privoxy
curl --proxy http://127.0.0.1:8118 https://check.torproject.org/api/ip

# 3. Test SOCKS5 proxy (using remote DNS to prevent leaks)
curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip

# 4. Request a new Tor identity / circuit
curl -X POST http://127.0.0.1:8080/reconnect
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
| `/reconnect` | `POST` (or `GET`) | Triggers `SIGNAL NEWNYM` to establish a new Tor circuit. |
| `/disconnect` | `POST` (or `GET`) | Disables Tor network traffic (`SETCONF DisableNetwork=1`). |
| `/connect` | `POST` (or `GET`) | Re-enables Tor network traffic (`SETCONF DisableNetwork=0`). |

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
