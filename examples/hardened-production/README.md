# Production Hardened Tor Proxy Example

This example demonstrates how to run `torproxy` in production with maximum security hardening, including a read-only root filesystem, dropped Linux capabilities, and privilege escalation prevention.

---

## Architecture

```
 Host Application / Browser
       │ (127.0.0.1:8118 / 9050)
       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ torproxy Container (Hardened Sandbox)                       │
 │                                                             │
 │  • Non-root system user: torproxy                           │
 │  • cap_drop: [ALL] (No Linux kernel privileges)             │
 │  • security_opt: [no-new-privileges:true]                   │
 │  • Strict loopback port binding (127.0.0.1)                 │
 │                                                             │
 │  Privoxy (8118) ───► Tor SOCKS5 (9050) ───► Tor Network     │
 │                           ▲                                 │
 │  REST API (8080) ─────────┘ (Cookie Authenticated)          │
 └─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/) 24.0+ and Docker Compose v2.
- `curl` and `jq` for testing endpoints.

---

## Quick start

1. Start the hardened container:
   ```bash
   docker compose up -d
   ```

2. Verify that the container is healthy and routing through Tor:
   ```bash
   curl -s http://127.0.0.1:8080/status | jq .
   curl --proxy http://127.0.0.1:8118 https://check.torproject.org/api/ip
   ```

3. Verify security constraints:
   ```bash
   # Verify non-root user execution:
   docker exec torproxy-hardened id -u

   # Verify dropped capabilities:
   docker inspect --format '{{.HostConfig.CapDrop}}' torproxy-hardened
   # Output: [ALL]

   # Verify no-new-privileges:
   docker inspect --format '{{.HostConfig.SecurityOpt}}' torproxy-hardened
   # Output: [no-new-privileges:true]
   ```

4. Clean up:
   ```bash
   docker compose down -v
   ```
