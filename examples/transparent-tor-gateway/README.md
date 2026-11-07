# Transparent Tor Gateway for Docker

Route any Docker container's entire outbound TCP and DNS traffic transparently through Tor — with zero application configuration.

---

## Architecture

```text
Any Docker Container (network_mode: "service:torproxy")
    │
    ├── DNS Request (:53) ──────► Tor DNSPort (:9053) ─────► Tor Network (Remote DNS)
    │
    ├── TCP Request (:80/:443) ─► Tor TransPort (:9040) ───► Tor Exit Node ──► Target
    │
    └── Non-Tor UDP / Leaks ────► iptables Kill Switch ────► REJECT (Fail-Closed)
```

By attaching a container to `torproxy` via `network_mode: "service:torproxy"`, both containers share the exact same network namespace. `torproxy` intercepts all outgoing TCP traffic via `TransPort` and all DNS requests via `DNSPort`. Direct non-Tor traffic is strictly blocked by the netfilter kill switch.

---

## Prerequisites

- Docker Engine 20.10+
- Docker Compose v2+
- `CAP_NET_ADMIN` capability (required only for `torproxy` to manage iptables inside its network namespace)

---

## Quick Start

### 1. Launch the Gateway and Demo Client

```bash
docker compose up
```

### 2. Verify Output

The demo `client` container executes `curl -s https://check.torproject.org/api/ip` without any proxy flags:

```json
{"IsTor":true,"IP":"185.220.101.5"}
```

### 3. Route Your Own Containers

To route any service through the gateway, set `network_mode: "service:torproxy"` and wait for `service_healthy`:

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    pull_policy: always
    cap_add:
      - NET_ADMIN
    environment:
      TORPROXY_GATEWAY_MODE: "true"
      TORPROXY_COUNTRY: "DE" # optional country routing
    restart: unless-stopped

  my-app:
    image: my-crawler:latest
    network_mode: "service:torproxy"
    depends_on:
      torproxy:
        condition: service_healthy
```

---

## Security Guarantees & Kill Switch

1. **DNS Leak Prevention**: All DNS queries on port 53 (UDP & TCP) are automatically redirected to Tor's internal resolver. No DNS queries ever touch the Docker host or public DNS resolvers.
2. **Fail-Closed Kill Switch**: If Tor is bootstrapping, disconnected, or terminates, direct outbound traffic is blocked by `iptables` reject rules.
3. **UDP Isolation**: Because Tor does not support arbitrary UDP, unsupported outbound UDP is blocked with ICMP port-unreachable to trigger immediate fallback to TCP (e.g. for HTTP/3 / QUIC).
4. **Non-Root Execution**: The container init runs as root only to drop privileges — every daemon runs as an unprivileged user (`tor`, `privoxy`, `torproxy`). The gateway kill switch scopes the WAN bypass to the dedicated `tor` UID.
5. **iptables backend (ISSUE-13)**: `check_net_admin_capability` requires a working `iptables` plus an nft or legacy backend binary (`xtables-nft-multi` / `xtables-legacy-multi`). Alpine package renames that drop the multi-binary will fail fast at startup instead of silently leaving the gateway unprotected. `iptables_backend()` reports the active backend (`nft` / `legacy`) for diagnostics.

---

## Docker DNS interaction & `FORWARD DROP` (ISSUE-13)

The gateway installs `iptables -A FORWARD -j DROP` as part of the fail-closed
kill switch (IPv6: policy `FORWARD DROP`). This has two practical consequences
you must plan for:

* **Embedded Docker DNS (`127.0.0.11`)**: containers sharing the `torproxy`
  network namespace via `network_mode: "service:torproxy"` resolve names through
  the embedded DNS *before* traffic is forwarded. The `FORWARD DROP` rule drops
  forwarded packets, it does not break name resolution *inside* the shared
  namespace. But bridge-level forwarding to *another* Compose network or to a
  host-published port that relies on the Docker bridge `FORWARD` chain will be
  dropped — expose the gateway ports directly on the `torproxy` service
  (`ports:` on `torproxy`, not on the client container) and use
  `depends_on: condition: service_healthy`.
* **Bridge setups**: if you route traffic through a user-defined bridge and
  expect `FORWARD` to carry it to a sidecar, add an explicit `ACCEPT` for your
  subnet *after* the gateway rules are installed — or keep the setup entirely
  inside the shared namespace (recommended). The default posture is intentionally
  fail-closed; see `src/torproxy/runtime/gateway.py:generate_iptables_rules`.

Verify the documented setup with:

```bash
docker compose up -d && ./verify_gateway.sh
```

---

## Tear Down

```bash
docker compose down -v
```
