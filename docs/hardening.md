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

Here is a complete, production-ready hardened configuration (also available under [`examples/hardened-production/docker-compose.yml`](../examples/hardened-production/docker-compose.yml)):

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    container_name: torproxy-hardened
    restart: unless-stopped
    
    # 1. Enforce read-only root filesystem
    read_only: true
    
    # 2. Prevent privilege escalation
    security_opt:
      - no-new-privileges:true
      
    # 3. Drop all Linux kernel capabilities
    cap_drop:
      - ALL
      
    # 4. Mount isolated, memory-backed tmpfs for required scratch directories
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=32M
      - /run:rw,noexec,nosuid,size=16M
      - /var/lib/tor:rw,noexec,nosuid,size=64M
      - /var/log/privoxy:rw,noexec,nosuid,size=16M
      
    # 5. Resource limits to prevent denial-of-service
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 256M
        reservations:
          memory: 64M
          
    # 6. Bind published ports strictly to host loopback interface
    ports:
      - "127.0.0.1:8118:8118"
      - "127.0.0.1:9050:9050"
      - "127.0.0.1:8080:8080"
```

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
