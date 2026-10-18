# Security Policy

The `torproxy` project prioritizes security, privacy, and transparent failure boundaries. This document outlines the project's security policy, threat model, supported versions, and vulnerability disclosure procedures.

---

## Supported Versions

Only the latest released version and the `latest` container image receive active security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

---

## Reporting a Vulnerability

If you discover a security vulnerability or potential leak issue in `torproxy`, please report it responsibly:

1. **Private Reporting**: Please use GitHub's private vulnerability reporting feature under the **Security** tab of the repository (`https://github.com/hapheus/torproxy/security/advisories/new`).
2. **Alternative Contact**: You may email `hapheus@gmail.com` with subject `[SECURITY] torproxy vulnerability report`.
3. **Information to Include**:
   - Detailed description of the vulnerability.
   - Proof-of-concept steps or Docker command demonstrating the issue.
   - Potential impact (e.g., clearnet leak, host exposure, bypass).
   - Any proposed mitigations or patches.

### Response Timeline
- **Acknowledgement**: Within 48 hours.
- **Triage & Reproduction**: Within 5 business days.
- **Fix & Coordinated Disclosure**: As rapidly as possible depending on severity, with credit attributed in release notes.

Please **do not** report security vulnerabilities via public GitHub issues.

---

## Threat Model and Trust Boundaries

### 1. Local Container Security Boundary
- **Non-Root Execution**: The container runs under a dedicated unprivileged system user (`torproxy`), never as `root` (UID 0).
- **Control Port Authentication**: Tor's internal ControlPort (`127.0.0.1:9051`) requires authentication using an ephemeral filesystem cookie (`CookieAuthentication 1`). The cookie file permissions are restricted to the non-root container user (`0600`).
- **Loopback Internal Services**: Tor ControlPort listens strictly on loopback inside the container and is never exposed or published.

### 2. REST Management API Trust Boundary
- **Unauthenticated Design**: The REST API on port `8080` is unauthenticated by default to provide a lightweight developer and automation experience.
- **Publication Warning**: Port `8080` must **never** be exposed to untrusted networks or the public internet without an authenticating reverse proxy (e.g., Caddy, Nginx, or Traefik with HTTP Basic Auth / OAuth / mTLS).
- **Default Loopback Binding**: In `docker-compose.yml`, all published ports bind explicitly to `127.0.0.1`.

### 3. Fail-Closed Proxy Architecture
- **No Clearnet Bypass**: Privoxy forwards traffic to Tor using `forward-socks5t 127.0.0.1:9050 .`. If Tor is offline, disconnected via `/disconnect`, or unbootstrapped, Privoxy returns an HTTP 500/503 error page. It **never** falls back to direct clearnet routing.
- **SOCKS5 Failure**: When Tor is stopped or disconnected, direct connections to port `9050` are rejected or drop immediately, preventing leaks.

### 4. Remote DNS Resolution (Preventing DNS Leaks)
- **SOCKS5a / SOCKS5h**: Software routing through SOCKS5 (`127.0.0.1:9050`) must pass domain names directly to the proxy (RFC 1928 address type `0x03`) rather than resolving them locally.
  - In `curl`: Use `--socks5-hostname 127.0.0.1:9050` (or `socks5h://`), **not** `--socks5`.
  - In browsers: Ensure "Proxy DNS when using SOCKS v5" is enabled.
- **Privoxy**: Automatically resolves all DNS queries via Tor exit nodes.

### 5. Tor Network Realities
- **No 100% Anonymity Guarantee**: Tor is an overlay network designed to conceal network routing. It does not strip application-level tracking cookies, browser fingerprints, or plaintext payloads.
- **Always Use HTTPS**: Plaintext HTTP traffic exiting a Tor exit relay can be monitored by the exit node operator. Always use `https://` for sensitive data.
- **Latency & Reliability**: Tor circuits incur variable latency and occasional connection drops. Circuit rotation (`/reconnect`) requests a fresh circuit from Tor via `SIGNAL NEWNYM`, but does not guarantee a distinct exit IP address if Tor's circuit pool is constrained.

---

## Vulnerability Management and Scanning Policy

To protect users against upstream vulnerabilities and supply chain compromises:

1. **Continuous Automated Scanning**:
   - Every pull request and merge to `main` undergoes container vulnerability scanning using Trivy.
   - Images are evaluated against standard CVE databases (Debian Security Advisories, NVD).
2. **Triage Severity SLA**:
   - **Critical & High**: Addressed within 7 business days via base image update or upstream package bump.
   - **Medium & Low**: Triaged during regular monthly release cycles.
3. **False Positive & Exception Process**:
   - Any accepted risk or scanner false-positive must be documented in a `.trivyignore` file with an issue link, rationale, and expiration date.
4. **Base Image Updates**:
   - The container builds upon `debian:bookworm-slim`. Security patches for `tor`, `privoxy`, `curl`, and `ca-certificates` are pulled directly from Debian security mirrors during build.

---

## Supply Chain Security and Provenance

- **Reproducible Multi-Arch Builds**: Images are built using Docker Buildx for `linux/amd64`, `linux/arm64`, and `linux/arm/v7`.
- **Software Bill of Materials (SBOM)**: Release builds generate automated SBOM metadata (SPDX format) embedded in the image attestation.
- **Provenance Attestations**: Docker Buildx generates SLSA provenance attestations (`mode=max`) guaranteeing build integrity from GitHub Actions.
- **Minimal Dependencies**: The image intentionally contains no node runtime, pip packages, or third-party binaries. Privoxy, Tor, and standard library Python 3 constitute the entire execution stack.
