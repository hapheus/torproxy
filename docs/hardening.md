# Container Runtime Hardening Guide

This document describes how to deploy `torproxy` with maximum runtime security and least privilege in production environments, without altering application behavior.

---

## 1. Security Architecture & Threat Boundaries

The `torproxy` container is designed with defensive depth:
- **Dedicated Non-Root User**: The image executes as the unprivileged user `torproxy` (UID/GID assigned during build).
- **Ephemeral Cookie Authentication**: The Tor ControlPort (`127.0.0.1:9051`) requires an unguessable 32-byte filesystem cookie authenticated per session.
- **Fail-Closed Forwarding**: Privoxy routes strictly to SOCKS5. If Tor is stopped, requests immediately fail with 500/503 and cannot leak to clearnet.

---

## 2. Hardening Measures

### A. Read-Only Root Filesystem (`read_only: true`)
Prevent attackers or rogue processes from modifying system binaries or writing persistent malware by mounting the container root filesystem as read-only.

`torproxy` only requires temporary write access to four locations, which should be mounted as memory-backed `tmpfs`:
- `/tmp`: Used by startup scripts for rendering configuration templates (`privoxy.config`, `torrc`).
- `/run`: Standard Linux runtime directory.
- `/var/lib/tor`: Tor ephemeral state, circuit data, and authentication cookie.
- `/var/log/privoxy`: Privoxy runtime logging.

### B. Dropping Linux Capabilities (`cap_drop: [ALL]`)
`torproxy` does not require any Linux capabilities (such as `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, or `CAP_CHOWN`). All capabilities can be dropped safely.

### C. Preventing Privilege Escalation (`no-new-privileges:true`)
Ensures that container processes cannot gain additional privileges via setuid or setgid binaries.

---

## 3. Production Hardened Docker Compose Configuration

The recommended production configuration drops all kernel capabilities and prohibits privilege escalation (available in [`examples/hardened-production/docker-compose.yml`](../examples/hardened-production/docker-compose.yml)):

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    container_name: torproxy-hardened
    restart: unless-stopped
    
    # 1. Prevent privilege escalation
    security_opt:
      - no-new-privileges:true
      
    # 2. Drop all Linux kernel capabilities
    cap_drop:
      - ALL
      
    # 3. Bind published ports strictly to host loopback interface
    ports:
      - "127.0.0.1:8118:8118"
      - "127.0.0.1:9050:9050"
      - "127.0.0.1:8080:8080"
```

> [!NOTE]
> **Read-Only Root Filesystem (`read_only: true`)**:
> If your container runtime supports user-owned tmpfs mounts (such as Podman or Docker Compose with `tmpfs: [ /tmp, /run, /var/log/privoxy, /var/lib/tor:uid=...,gid=... ]`), you can additionally enable `read_only: true`. Tor requires `/var/lib/tor` to have mode `0700` owned by the container user (`torproxy`). For universal compatibility across standard Docker installations, `cap_drop: [ALL]` and `no-new-privileges: true` provide complete capability containment.

---

## 4. Verification

After starting the hardened container, verify that security constraints are active:

```bash
# 1. Verify read-only rootfs (should return "Read-only file system" error)
docker exec torproxy-hardened touch /etc/test.txt

# 2. Verify non-root execution (should be > 0)
docker exec torproxy-hardened id -u

# 3. Verify dropped capabilities
docker inspect --format '{{.HostConfig.CapDrop}}' torproxy-hardened
# Expected output: [ALL]

# 4. Verify no-new-privileges
docker inspect --format '{{.HostConfig.SecurityOpt}}' torproxy-hardened
# Expected output: [no-new-privileges:true]

# 5. Verify proxy functionality
curl --proxy http://127.0.0.1:8118 https://check.torproject.org/api/ip
```
