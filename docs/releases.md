# Releases, Versioning, and Upgrade Guide

This document describes the release lifecycle, versioning contract, multi-architecture builds, upgrade testing, and rollback procedures for `torproxy`.

---

## 1. Versioning Contract

`torproxy` strictly adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/):

$$\text{MAJOR}.\text{MINOR}.\text{PATCH}$$

- **MAJOR**: Incompatible API or breaking behavioral changes.
  > [!IMPORTANT]
  > Under the project's absolute compatibility contract, breaking changes are strictly avoided. All core ports (8118, 9050, 8080), environment variables, REST endpoints, and legacy GET mutation routes remain backward-compatible across minor and patch releases.
- **MINOR**: Backward-compatible additive functionality, new endpoints (e.g., `/health`, `/diagnostics`, `/metrics`), new optional environment variables, or security hardening enhancements.
- **PATCH**: Backward-compatible bug fixes, dependency updates, and security patches.

---

## 2. Published Tags and Architecture Matrix

### Published Tags
Images are published to Docker Hub at [`hapheus/torproxy`](https://hub.docker.com/r/hapheus/torproxy):

| Tag | Mutability | Description |
| --- | ---------- | ----------- |
| `latest` | Mutable | Tracks the latest stable commit on the default branch (`main`). |
| `vX.Y.Z` (e.g. `v1.3.0`) | **Immutable** | Official, cryptographically tagged release pointing to an exact commit. Recommended for production deployments. |
| `vX.Y` (e.g. `v1.3`) | Mutable | Tracks the latest patch release within a minor release stream. |

### Supported CPU Architectures
Every official image build targets the following architectures using Docker Buildx:
- `linux/amd64` (Standard x86_64 servers and PCs)
- `linux/arm64` (Apple Silicon, AWS Graviton, Raspberry Pi 4/5 64-bit)
- `linux/arm/v7` (32-bit ARM devices, Raspberry Pi 2/3)

---

## 3. Supply Chain Security, SBOM, and Provenance

- **Provenance Attestations**: Published container images include SLSA provenance metadata (`mode=max`) embedded in the container manifest.
- **Software Bill of Materials (SBOM)**: Release builds include an SPDX/CycloneDX SBOM documenting all installed packages and file digests.
- **Automated Vulnerability Scanning**: Images are scanned against CVE databases (Trivy) on every PR and build before publishing.

---

## 4. Upgrade Guide

Because `torproxy` maintains an absolute compatibility contract, upgrades are 100% drop-in replacements. There are **zero configuration changes**, **zero database migrations**, and **zero secret reconfigurations** required.

### Upgrading via Docker Compose

1. Pull the new image version:
   ```bash
   docker compose pull
   ```
2. Re-create the container with zero manual intervention:
   ```bash
   docker compose up -d
   ```
3. Verify the upgraded container:
   ```bash
   # Check container status
   curl -s http://127.0.0.1:8080/status | jq .

   # Check health and diagnostics
   curl -s http://127.0.0.1:8080/health | jq .
   curl -s http://127.0.0.1:8080/diagnostics | jq .
   ```

---

## 5. Rollback Procedure

If an upgraded image exhibits unexpected behavior in your environment:

1. Pin your `docker-compose.yml` to the previously known-good version (e.g. `image: hapheus/torproxy:v1.1.1`):
   ```yaml
   services:
     torproxy:
       image: hapheus/torproxy:v1.1.1
   ```
2. Restart the service:
   ```bash
   docker compose up -d
   ```
3. Since `torproxy` is stateless and persists no internal database, the rollback is instantaneous and safe.

---

## 6. Release Notes

### 2.7.1 (MCP Registry automated publishing workflow)

- **Automated MCP Registry Publish (#134):** Added `.github/workflows/publish-mcp.yml` using GitHub Actions OIDC (`id-token: write`) to automatically publish the verified `server.json` to `registry.modelcontextprotocol.io` upon pushing release tags (`v*`).
- **Dependencies (#130):** Bumped ruff to 0.17.4.

### 2.7.0 (Model Context Protocol Registry manifest)

- **Official MCP Registry Manifest (#132):** Added standardized `server.json` manifest conforming to schema `2025-12-11` under namespace `io.github.hapheus/torproxy` for OCI container distribution via `docker.io/hapheus/torproxy:2.7.0`. Validated against `registry.modelcontextprotocol.io`.
- **Single Source of Truth Enforcement (#132):** Synchronized `server.json` version and image identifier with `pyproject.toml`, `docker/Dockerfile`, and unit contract tests.

### 2.6.2 (Live verification & test resilience hardening)

- **Live Verification Resilience (#127, #128, PR #129):** Hardened the composite action (`.github/actions/live-verification/action.yml`) against transient Tor network latency, circuit negotiation drops, and upstream probe timeouts. Added 4-attempt retry loops with backoff and fallback IP verification (`api.ipify.org`) for `torproxy_fetch` and transparent gateway egress, while preserving strict fail-closed leak checks (`FETCH_IP == RUNNER_IP`).
- **GeoIP Container Bootstrap Polling (#128, PR #129):** Recognizes Tor bootstrap completion via `/health` (`progress == 100`) in addition to `/status` (`connected`), preventing false-positive timeouts when Tor is fully ready but external egress probe ping is delayed. Dumps container logs on SLA failure.

### 2.6.1 (MCP server CLI entrypoint, Streamable HTTP & transport hardening)

- **Container CLI Entrypoint (#124, PR #125):** Installed `/usr/local/bin/torproxy` inside the Docker image and verified `torproxy --version` at build time so `docker exec -i torproxy torproxy mcp` works out of the box.
- **Streamable HTTP & SSE Hardening (#124, PR #125):** Added MCP `2025-03-26+` Streamable HTTP support (`POST /mcp`, `POST /sse`, `POST /`), authenticated SSE session continuity for `?token=...` clients, constant-time `hmac.compare_digest` token verification, IPv6 listener support (`AF_INET6`), and non-blocking session shutdown.
- **Gateway Mode & Protocol Hardening (#124, PR #125):** Exempted MCP port `2501` in transparent gateway netfilter rules (`TORPROXY_GATEWAY_MODE=true`), added `protocolVersion` negotiation and `_SafeRedirectHandler` redirect scheme validation in `torproxy_fetch`.

### 2.6.0 (Model Context Protocol server & torproxy_fetch)

- **Integrated MCP Server (ISSUE-122, PR #123):** Built-in zero-dependency Model Context Protocol (MCP) server running on port `2501` (HTTP/SSE) and via Stdio (`torproxy mcp`), enabling autonomous AI agents (Claude Desktop, Cursor, Antigravity) to orchestrate Tor circuits and inspect status.
- **Native `torproxy_fetch`:** Zero-config HTTP/HTTPS and `.onion` fetching routed strictly through Tor without host proxy configuration or clearnet leaks.
- **Canary verification:** Daily live canary suite now verifies `torproxy_fetch` against `check.torproject.org` with runner host IP leak detection.

### 2.5.0 (Feature roadmap follow-ups: TLS example, IPv6, SOCKS policy)

- **GeoIP User-Agent fix (ISSUE-20 regression, #113, PR #114):** the GeoIP downloader no longer sends the custom `torproxy-geoip/1` User-Agent — GitLab answers raw files only to known UA patterns (`curl/*`, `Python-urllib/*`) with HTTP 403 for custom UAs. The daily canary failure is fixed; fallback to the bundled database was already working.
- **Feature roadmap (ISSUE-18, #82, PR #109):** `docs/roadmap-features.md` records TLS termination, IPv6 listen addresses and SOCKS5 auth as roadmap entries with threat assessments; follow-up issues #106, #107, #108.
- **TLS reverse-proxy example (ISSUE-18a, #106, PR #110):** `examples/tls-reverse-proxy/` — Caddy terminates TLS in front of the HTTP-only API (loopback-only by default), cross-referenced from `SECURITY.md`. No container behavior change.
- **IPv6 listen addresses (ISSUE-18b, #107, PR #111):** `TORPROXY_LISTEN_ADDRESS` / `TORPROXY_API_LISTEN_ADDRESS` accept IPv4 or IPv6 (`ipaddress.ip_address()`); the API server binds `AF_INET6` for IPv6 values. Defaults (`0.0.0.0`) unchanged.
- **SOCKS source-IP access control (ISSUE-18c, #108, PR #112):** new optional `TORPROXY_SOCKS_ALLOWED_CIDRS` renders Tor `SocksPolicy` (accept listed CIDRs + loopback, reject all else; default unset = accept all). Tor's SocksPort is unauthenticated by design — client username/password is only stream isolation, never a credential check — so source-IP policy is the strongest access control Tor itself offers; documented in `docs/configuration.md` / `docs/compatibility.md`.

### 2.4.0 (Probe diagnosis & Privoxy ADR)

- **Egress probe failure taxonomy (ISSUE-12, #76, PR #104):** `TorEgressProbe` now distinguishes `local HTTP proxy unreachable` (connection refused on `127.0.0.1:8118`, e.g. Privoxy down while SOCKS5/Tor may be healthy), `Tor upstream unavailable via local HTTP proxy (HTTP 5xx)` (proxy answered 5xx, no Tor circuit ready), `egress check service returned HTTP 4xx` (check service answered, e.g. 429 rate-limit — not a Tor failure), and `egress check service unreachable`. An open circuit breaker keeps the original cause. Error strings are stable and leak-free; `status` values and JSON shapes are unchanged.
- **Privoxy ADR (`docs/adr-privoxy-http-proxy.md`):** evaluation of Privoxy vs. `HTTPTunnelPort`/`tinyproxy` — decision is to **keep Privoxy on port 8118 for now**; a replacement requires a prototype passing plain HTTP, CONNECT, remote-DNS leak, fail-closed and IPv6 tests. No new dependency for a SOCKS5-native probe (`urllib` has no SOCKS support).

### 2.3.0 (GeoIP auto-update)

- **Optional periodic GeoIP auto-update (ISSUE-20, #102):** new opt-in `TORPROXY_GEOIP_AUTO_UPDATE=1` downloads Tor's `geoip`/`geoip6` from Tor Project GitLab over HTTPS at startup and every `TORPROXY_GEOIP_UPDATE_INTERVAL` seconds (default 24h), validates the format, installs atomically into `TORPROXY_GEOIP_DIR`, and sends Tor `SIGHUP` to reload. On any failure the bundled or previously installed database keeps working. Default stays disabled (backward compatible). The Daily Live Image Verification workflow now checks daily that the GeoIP upstream URLs are reachable and that a container with auto-update downloads the database.

### 2.2.0 (P0/P1 robustness sprint)

- **Egress check decoupling (ISSUE-06, #70):** `TorEgressProbe` retries with backoff, trips a circuit breaker after repeated failures and returns distinct reasons (`egress check service unreachable` vs. `IsTor=false`). `/health` reports `degraded` with a reason when Tor/SOCKS are up but the check fails. The Docker healthcheck is loopback-only — no external domain call (`config.privoxy.org` removed).
- **ControlPort sanitization (ISSUE-08, #72):** socket failures map to the stable error `Tor control unavailable`; raw `[Errno ...]`/paths never reach API clients. ADR `docs/adr-tor-control-port.md`: one-shot client stays.
- **Parser hardening (ISSUE-09, #73):** `read_reply` checks the size limit before appending in `+` data blocks and bounds the line buffer before `recv`; `authenticate` reads exactly 32 bytes (trailing-newline cookies accepted).
- **Cache correctness & tuning (ISSUE-10, #74):** single-flight for egress probes (20 parallel `/ip` → 1 upstream call), additive `stale` field in `/health` egress, and new env vars `TORPROXY_CACHE_TTL`, `TORPROXY_REQUEST_TIMEOUT`, `TORPROXY_MAX_WORKERS`, `TORPROXY_MAX_BODY_BYTES` (defaults unchanged).
- **Worker overload visibility (ISSUE-11, #75):** saturation now returns `503` + `Retry-After` (instead of a silent TCP reset) and increments `torproxy_requests_rejected_total`.
- **Gateway operations (ISSUE-13, #77):** `check_net_admin_capability` evaluates nft/legacy backend binaries (`iptables_backend()` helper); `FORWARD DROP` + Docker embedded DNS (`127.0.0.11`) interaction documented in `examples/transparent-tor-gateway/README.md`.
- **API observability & privacy (ISSUE-14, #78):** anonymous `/health` returns a minimal `{status}` body, every response carries `X-Request-ID`, and `/metrics` gains `http_requests_total`, `http_4xx_total`, `http_5xx_total`, `http_latency_seconds_total/count` and `requests_rejected_total`. Wildcard CORS stays on successful non-mutating reads only.

### 2.1.1 (Python/toolchain alignment)

- **Python/toolchain drift fixed (ISSUE-15, #79):** the image interpreter is pinned to Python 3.14 (`ARG PYTHON_VERSION` + `apk add python3~3.14`) with a fail-fast build-time version assert; `torproxy` is installed into the `sysconfig`-derived `site-packages` instead of the Debian-specific `dist-packages` path (no `PYTHONPATH` needed); the hermetic CI matrix now covers 3.10 (declared minimum), 3.11, and 3.14; the image build logs the Python version and runs an import self-test. No application behavior changed. Original approach contributed by @Joffy-Maria (#93).

### 2.1.0 (Sprint 2: gateway security architecture)

- **Kill-switch fail-closed restored (ISSUE-02):** removed the unrestricted `ESTABLISHED,RELATED` accept from filter OUTPUT; pre-existing clearnet connections no longer survive a Tor outage.
- **Least privilege for the WAN bypass (ISSUE-03):** the container init runs as root only to drop privileges — Tor runs as the dedicated unprivileged `tor` user, Privoxy as `privoxy`, the API as `torproxy`. Gateway netfilter now scopes the WAN bypass to the `tor` UID, so the API/Privoxy cannot reach the WAN directly. Tor gets a scoped IPv6 exception (IPv6-only bootstrap fixed) while the IPv6 policy stays DROP.
- **Idempotent gateway setup (ISSUE-05):** `setup_gateway` probes each rule with `-C` before appending; container restarts in gateway mode no longer fail on duplicate rules.

### 2.0.2 (Sprint 1: security & contract fixes)

- **CSRF protection on mutations (ISSUE-01):** `/connect`, `/disconnect`, `/reconnect` presented with a foreign browser `Origin`/`Referer` are rejected with `403 Forbidden`. Requests without those headers (curl, scripts, healthchecks) are unaffected. Wildcard CORS is now sent only on successful non-mutating responses.
- **`TORPROXY_STRICT_NODES` default fix (ISSUE-04):** setting `TORPROXY_COUNTRY` no longer implicitly enables strict mode; strict requires explicit `TORPROXY_STRICT_NODES=1` (matches the documented default `0`).
- **Version single source of truth (ISSUE-07):** `torproxy.__version__` is derived from `pyproject.toml`; `torproxy --version` now reports the actual release version.
- **Repo hygiene (ISSUE-16):** `.mypy_cache/` ignored; contract test guards against tracked compiled artifacts.

---

## 7. Release Verification Checklist

Maintainers must verify the following checklist before publishing any new version:
- [ ] All hermetic unit tests pass (`uv run pytest tests/unit/ -v --cov=torproxy`).
- [ ] Static analysis passes (`ruff check .` and `shellcheck`).
- [ ] Container smoke and multi-port verification succeed (`tests/integration/verify_container.sh`).
- [ ] Backward compatibility upgrade test succeeds with unchanged Compose configuration.
- [ ] Single source of truth synchronized (`pyproject.toml`, `src/torproxy/__init__.py`, `docker/Dockerfile`, `server.json`).
- [ ] Documentation (`README.md`, `DOCKERHUB.md`, `docs/`) updated with the new version and features.
- [ ] Git tag created matching `vX.Y.Z` and pushed to GitHub.
