# TLS Reverse Proxy Example

This example terminates TLS in front of the torproxy management
API with Caddy, so the API token and control mutations never
travel in cleartext when the API leaves loopback. The torproxy
container itself stays plain HTTP — no certificate management and
no extra dependency inside the container (ISSUE-18a, #106).

---

## Architecture

```
  Client (curl / script)
        │ https://127.0.0.1:8443 (TLS, Caddy)
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Docker network (internal only)                          │
  │                                                         │
  │  Caddy ──► torproxy:8080 (REST API, HTTP)               │
  │  torproxy: 8118 (HTTP proxy) ──► Tor SOCKS5 (9050)      │
  │            ──► Tor Network                              │
  └─────────────────────────────────────────────────────────┘
```

`torproxy` publishes **no** ports to the host; only Caddy does,
bound to `127.0.0.1` by default.

---

## Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/) 24.0+ and Docker Compose v2.
- `curl` with `--cacert` handling for the internal CA (see below), or a real domain for a trusted certificate.

---

## Quick start

1. (Optional) Set an API token — via your secret manager, never
   commit a real secret:
   ```bash
   export TORPROXY_API_TOKEN="replace-with-a-strong-secret"
   ```

2. Start the stack:
   ```bash
   docker compose up -d
   ```

3. Verify the API through the TLS endpoint. Caddy's `tls internal`
   issues a local-CA certificate, so trust it explicitly:
   ```bash
   # One-time: export Caddy's internal CA from the container
   docker exec torproxy-caddy \
     cat /data/caddy/certificates/local/root.crt > /tmp/caddy-root.crt

   curl -s --cacert /tmp/caddy-root.crt https://127.0.0.1:8443/status | jq .
   curl -s --cacert /tmp/caddy-root.crt https://127.0.0.1:8443/health | jq .
   ```

   With `TORPROXY_API_TOKEN` set, add
   `-H "Authorization: Bearer $TORPROXY_API_TOKEN"` to each call.

4. Verify the HTTP proxy still works (unchanged):
   ```bash
   docker exec torproxy-tls \
     curl -s --proxy http://127.0.0.1:8118 https://check.torproject.org/api/ip
   ```

5. Clean up:
   ```bash
   docker compose down -v
   ```

---

## Production notes

- For internet-facing use, replace `:8443` in `Caddyfile` with a
  public domain (automatic trusted certificates), add an IP
  allowlist or basic auth in Caddy, and put a firewall in front.
- Never publish ports `8080`, `8118` or `9050` directly — see
  `SECURITY.md` (Publication Warning).
- The `tls internal` certificate is only for local testing; do
  not use it for real deployments.
