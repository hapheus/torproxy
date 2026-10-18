# torproxy — Minimal, Production-Grade Tor HTTP & SOCKS5 Proxy for Docker

[![PR Quality & Smoke Gate](https://github.com/hapheus/torproxy/actions/workflows/pr-gate.yml/badge.svg)](https://github.com/hapheus/torproxy/actions/workflows/pr-gate.yml)
[![Daily Live Image Verification](https://github.com/hapheus/torproxy/actions/workflows/daily-image-verification.yml/badge.svg)](https://github.com/hapheus/torproxy/actions/workflows/daily-image-verification.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/hapheus/torproxy)](https://hub.docker.com/r/hapheus/torproxy)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A minimal, secure, and reliable Tor HTTP and SOCKS5 proxy packaged for Docker. `torproxy` routes traffic through the Tor network with fail-closed protection, non-root execution, an authenticated Tor control interface, and a lightweight JSON REST API for circuit rotation and health monitoring.

---

## Architecture

```text
Host Client / Dependent Containers
        │
        ├── HTTP Requests ────────► Privoxy (:8118)
        │                             │ (forward-socks5t)
        ├── SOCKS5 Requests ──────────┼───────────────► Tor Daemon (:9050)
        │                             │                   │
        └── REST Control API ─────► API Server (:8080)   │ (Cookie Auth)
                                      │                   │
                                      └─ ControlPort ─────┘ (:9051 loopback)
                                                          │
                                                          ▼
                                                  Tor Onion Network
                                                          ▼
                                                    Target Website
```

---

## Quick Start

```sh
# 1. Start torproxy in the background
docker compose up -d

# 2. Test HTTP proxy (port 8118)
curl -v -x http://127.0.0.1:8118 https://check.torproject.org/api/ip

# 3. Test SOCKS5 proxy with remote DNS resolution (port 9050)
curl -v --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip

# 4. Check status via the local REST API
curl http://127.0.0.1:8080/status

# 5. Optional: Route exit traffic through a specific country (e.g. DE or AT)
TORPROXY_COUNTRY=DE docker compose up -d
# or multiple countries:
TORPROXY_COUNTRY=DE,AT docker compose up -d

# 6. Dynamically switch exit country on reconnect without container restart:
curl -X POST "http://127.0.0.1:8080/reconnect?country=DE"
# or with JSON payload:
curl -X POST http://127.0.0.1:8080/reconnect \
  -H "Content-Type: application/json" \
  -d '{"country": "AT", "strict_nodes": true}'
```

> **Security Note:** In `docker-compose.yml`, all ports bind strictly to `127.0.0.1` by default. Neither the proxy listeners nor the management API require authentication; do not expose them to untrusted networks.

---

## Available Interfaces and Ports

| Interface | Default Port | Internal Service | Description |
| --------- | ------------ | ---------------- | ----------- |
| **HTTP Proxy** | `8118` | Privoxy | HTTP/HTTPS forward proxy routing traffic to Tor. Fails closed (500/503) if Tor is disconnected. |
| **SOCKS5 Proxy** | `9050` | Tor | Direct Tor SOCKS5 listener. Supports remote DNS resolution via `socks5h://`. |
| **REST API** | `8080` | Python `api.py` | JSON management and health endpoint. Circuit rotation and connection management. |

---

## REST API Reference

The lightweight API server on port `8080` manages circuits and monitors health without requiring clients to implement the Tor Control Protocol.

| Endpoint | Method | Status Code | Purpose | Example Response |
| -------- | ------ | ----------- | ------- | ---------------- |
| `/status`, `/` | `GET`, `POST` | `200` | Connection status and current exit IP. | `{"status":"connected","ip":"198.51.100.42"}` |
| `/ip` | `GET` | `200`, `503` | Current verified Tor exit IP. Returns 503 while bootstrapping. | `{"ip":"198.51.100.42"}` |
| `/health`, `/v1/health` | `GET` | `200`, `503` | Structured diagnostic health state across Tor, proxies, and egress. | `{"status":"healthy","tor":{"bootstrapped":true,"progress":100},"proxies":{"socks5":true},"egress":{"verified":true,"ip":"..."}}` |
| `/diagnostics`, `/v1/diagnostics` | `GET` | `200` | Operational telemetry (uptime, reconnect counts, bootstrap progress). | `{"uptime_seconds":120,"reconnect_total":2,"tor":{"bootstrapped":true}}` |
| `/metrics`, `/v1/metrics` | `GET` | `200` | Prometheus exposition format metrics for scrapers. | Plaintext Prometheus metrics. |
| `/reconnect` | `POST` (or `GET`) | `200`, `400` | Request new circuit (`SIGNAL NEWNYM`). Supports `?country=DE` or JSON body. Clears IP cache. | `{"action":"reconnect","status":"success","exit_country":"DE"}` |
| `/disconnect` | `POST` (or `GET`) | `200` | Pause Tor network traffic (`DisableNetwork=1`). Fails closed. | `{"action":"disconnect","status":"success"}` |
| `/connect` | `POST` (or `GET`) | `200`, `400` | Resume Tor network traffic (`DisableNetwork=0`). Supports `?country=DE` or JSON body. | `{"action":"connect","status":"success"}` |

> **HTTP Methods:** `POST` is recommended for state mutations (`/reconnect`, `/disconnect`, `/connect`). Legacy `GET` calls remain fully supported for backward compatibility.
> Detailed schema definitions are documented in [docs/api.md](docs/api.md).

---

## Container Health Checks

`torproxy` includes a ready-aware Docker health check (`docker/healthcheck.sh`). A container reports `healthy` only when:
1. Privoxy and Tor daemons are running under non-root user.
2. Tor bootstrap is 100% complete (`bootstrapped=done`).
3. SOCKS5 listener on port 9050 passes greeting handshake.
4. Egress IP is confirmed through Tor (`IsTor: true`).

In Docker Compose, dependent services can wait for genuine Tor readiness using `service_healthy`:

```yaml
services:
  app:
    image: my-scraper:latest
    depends_on:
      torproxy:
        condition: service_healthy
```

---

## Configuration

Default settings require no configuration. You can customize listening ports and bindings via environment variables in a `.env` file or Compose `environment` section:

| Variable | Default | Allowed Values | Description |
| -------- | ------- | -------------- | ----------- |
| `TORPROXY_LISTEN_ADDRESS` | `0.0.0.0` | Valid IPv4 | Bind address for Privoxy inside the container. |
| `TORPROXY_LISTEN_PORT` | `8118` | `1024`–`65535` | HTTP proxy listening port inside the container. |
| `TORPROXY_HOST_PORT` | `8118` | `1`–`65535` | Host port mapped to HTTP proxy in `docker-compose.yml`. |
| `TORPROXY_API_PORT` | `8080` | `1024`–`65535` | REST API listening port (host and container). |
| `TORPROXY_SOCKS_PORT` | `9050` | `1024`–`65535` | Tor SOCKS5 proxy port (host and container). |
| `TORPROXY_COUNTRY` | *(unset)* | ISO 3166-1 alpha-2 (e.g. `DE`, `AT`, `US`, `DE,AT`) | Route Tor exit circuits through specific countries using `tor-geoipdb`. |
| `TORPROXY_STRICT_NODES` | `0` | `0`, `1`, `true`, `false`, `yes`, `no` | When `1`/`true`, reject circuits if configured country exit nodes are unavailable. |

All variables are strictly validated at startup. Port conflicts or out-of-range values trigger an immediate diagnostic failure. See [docs/configuration.md](docs/configuration.md) for full details.

---

## Shipped Examples

Ready-to-run use cases with hardened configurations:

| Example | Purpose | Guide |
| ------- | ------- | ----- |
| **Hardened Production** | Read-only rootfs, dropped capabilities, and memory-backed tmpfs. | [View Example](examples/hardened-production/) |
| **Browserless Chromium** | Headless browser automation and scraping routed through Tor. | [View Example](examples/browserless-chromium-via-tor/) |
| **CRW Web Scraper** | High-performance webpage-to-Markdown scraper via Tor proxy. | [View Example](examples/crw-web-scraper-via-tor/) |
| **SearXNG Metasearch** | Private, self-hosted search engine routing upstream queries via Tor. | [View Example](examples/searxng-via-tor/) |

---

## Security Model and Trust Boundaries

- **Non-Root Execution**: Container processes run strictly under the unprivileged system user `torproxy`.
- **Authenticated ControlPort**: Tor's control port (`127.0.0.1:9051`) requires ephemeral filesystem cookie authentication (`CookieAuthentication 1`).
- **Fail-Closed Guarantee**: If Tor disconnects or crashes, Privoxy drops traffic and returns HTTP 503 instead of leaking to clearnet.
- **DNS Leak Prevention**: To prevent local DNS leaks, always use remote DNS resolution with SOCKS5 (`curl --socks5-hostname 127.0.0.1:9050` or `socks5h://`).
- **Threat Model**: See [SECURITY.md](SECURITY.md) for vulnerability reporting procedures, threat boundaries, and anonymity limitations.
- **Hardening Guide**: See [docs/hardening.md](docs/hardening.md) for read-only rootfs and dropped Linux capabilities.

---

## Project Documentation

- [docs/compatibility.md](docs/compatibility.md) — Absolute backward compatibility contract and frozen interfaces.
- [docs/api.md](docs/api.md) — Exhaustive REST API specification and response schemas.
- [docs/configuration.md](docs/configuration.md) — Configuration guide and startup validation rules.
- [docs/hardening.md](docs/hardening.md) — Container runtime hardening, read-only rootfs, and dropped capabilities.
- [docs/releases.md](docs/releases.md) — Semantic versioning policy, upgrade paths, and instant rollback procedures.
- [docs/quality-baseline.md](docs/quality-baseline.md) — Measurable quality and performance baselines.
- [docs/quality-gate-10-10.md](docs/quality-gate-10-10.md) — Final 10/10 quality gate audit and verification matrix.

---

## Contributing

We welcome contributions! Please review our [Contributing Guidelines](CONTRIBUTING.md) and [Code of Conduct](CONTRIBUTING.md#core-engineering-principles).
All PRs must maintain backward compatibility, include hermetic unit tests, and maintain >= 90% test coverage.

---

## License

Released under the [MIT License](LICENSE).

---

## 💝 Support the Project

If you find this project helpful, consider showing some support:

- ☕ Buy me a coffee: Send a tip via [PayPal](https://paypal.me/hapheus).
- ❤️ Charity Donation: Donate to [Österreichische Krebshilfe (Austrian Cancer Aid)](https://www.krebshilfe.net/) or any local animal welfare organization.
- 🎯 Dream Support: I would love some tickets for the World Darts Championship at Ally Pally (Alexandra Palace) – hopefully, I will make it there one day!
