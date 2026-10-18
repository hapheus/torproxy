# Compatibility Contract & Public Interface Inventory

This document defines the strict, non-negotiable backward compatibility contract for `torproxy`. Every pull request, release, and refactoring must uphold the guarantees outlined here.

## 1. Absolute Compatibility Principles

1. **No Breaking Changes:** Existing Docker configurations, Compose files, deployment scripts, and API consumers must continue working without modifications.
2. **Additive Evolution:** New features, settings, or telemetry must be introduced additively (e.g., new optional fields or optional environment variables).
3. **No New Required Secrets or Volumes:** The container must continue to operate out of the box with `docker compose up -d` or `docker run`.
4. **Dual HTTP Method Support:** Legacy `GET` mutations on `/connect`, `/disconnect`, and `/reconnect` will remain supported indefinitely alongside `POST`.
5. **Stable Defaults:** Port numbers, bind addresses, and environment variable defaults must not change.

---

## 2. Public Network Interfaces & Ports

| Service | Container Port | Default Host Port | Protocol | Auth Default | Description |
|---|---|---|---|---|---|
| **HTTP Proxy** | `8118` | `8118` (`127.0.0.1`) | HTTP (Privoxy) | Unauthenticated | Standard HTTP/HTTPS forward proxy routed via Tor SOCKS5. |
| **SOCKS5 Proxy** | `9050` | `9050` (`127.0.0.1`) | SOCKS5 (Tor) | Unauthenticated | Tor SOCKS5 proxy with remote DNS resolution (`socks5h`). |
| **Control REST API** | `8080` | `8080` (`127.0.0.1`) | HTTP/REST | Unauthenticated | JSON management and monitoring interface. |
| **Tor ControlPort** | `9051` | Not Published | Tor Control | Cookie (M1+) | Internal loopback only (`127.0.0.1:9051`), never published to host. |

### Network Guarantees vs. Implementation Details

- **Guaranteed:**
  - Default ports 8118, 9050, 8080 are preserved.
  - Compose file binds host ports to `127.0.0.1` by default.
  - Intra-container communication on shared Docker networks uses container ports directly.
- **Incidental / Internal:**
  - Tor ControlPort is internal to the container and never exposed to the host.

---

## 3. Environment Variables & Defaults

| Variable | Default Value | Format / Validation | Guaranteed Behavior |
|---|---|---|---|
| `TORPROXY_LISTEN_ADDRESS` | `0.0.0.0` | Valid IPv4 address | Bind address for Privoxy inside the container. |
| `TORPROXY_LISTEN_PORT` | `8118` | Integer `1`–`65535` | Listening port for Privoxy inside the container. |
| `TORPROXY_API_PORT` | `8080` | Integer `1`–`65535` | Listening port for the Python REST API server. |
| `TORPROXY_SOCKS_PORT` | `9050` | Integer `1`–`65535` | Listening port for Tor SOCKS5 inside the container. |
| `TORPROXY_HOST_PORT` | `8118` | Integer `1`–`65535` | Compose host port mapping for the HTTP proxy. |
| `TORPROXY_COUNTRY` | *(unset)* | Comma-separated ISO codes | Optional: Restricts Tor exit nodes by country. Default: standard unrestricted Tor routing. |
| `TORPROXY_STRICT_NODES` | `0` | Boolean (`0`, `1`, `true`, `false`) | Optional: Refuse circuits if country exit nodes are unavailable. Default: `0`. |

---

## 4. REST API Contract

Base URL: `http://127.0.0.1:8080` (or `http://torproxy:8080` internally)
Content-Type: `application/json`
CORS: `Access-Control-Allow-Origin: *`

### Endpoints and HTTP Methods

| Path | Supported Methods | Description | Status Code | Required JSON Response Keys |
|---|---|---|---|---|
| `/status` (or `/`) | `GET`, `POST` | Current daemon and egress status | `200` (OK)<br>`500` (Error) | `status` (`string`), `ip` (`string` or `null`)<br>*On error:* `error` (`string`) |
| `/ip` | `GET`, `POST` | Current public Tor exit IP | `200` (OK)<br>`503` (Unavailable) | `ip` (`string`)<br>*On error:* `error` (`string`), `detail` (`string`) |
| `/connect` | `GET`, `POST` | Enable Tor network traffic | `200` (OK)<br>`500` (Error) | `action` (`"connect"`), `status` (`"success"`)<br>*On error:* `error` (`string`) |
| `/disconnect` | `GET`, `POST` | Disable Tor network traffic | `200` (OK)<br>`500` (Error) | `action` (`"disconnect"`), `status` (`"success"`)<br>*On error:* `error` (`string`) |
| `/reconnect` | `GET`, `POST` | Request new Tor circuit (`NEWNYM`) | `200` (OK)<br>`500` (Error) | `action` (`"reconnect"`), `status` (`"success"`)<br>*On error:* `error` (`string`) |
| *`<unknown>`* | Any | Fallback for unmapped paths | `404` (Not Found) | `error` (`"Not Found"`), `supported_paths` (`array[string]`) |

### Stable Status Values for `/status`
The `status` field must strictly evaluate to one of the following canonical strings:
- `"connected"`: Tor is fully bootstrapped, proxy is routing, and egress IP was resolved.
- `"connecting"`: Tor is bootstrapping or initial circuit is not yet ready.
- `"disconnected"`: Network disabled via `/disconnect`.

Optional additive fields such as `detail` may be included, but `status` and `ip` must never be omitted or renamed.

---

## 5. Container Runtime & Health Contract

### Dockerfile & Image Standards
- **Image Names:** `hapheus/torproxy:latest`, `hapheus/torproxy:<version>`
- **User:** Non-root system user `torproxy`
- **Init Supervision:** `/usr/bin/tini -g -- /usr/local/bin/start.sh`
- **Healthcheck Parameters:**
  - Interval: `30s`
  - Timeout: `15s`
  - Start period: `180s`
  - Retries: `3`
  - Command: `/usr/local/bin/healthcheck.sh`
- **Health Condition:** The container is `healthy` if and only if:
  1. Privoxy is locally reachable via `127.0.0.1:$TORPROXY_LISTEN_PORT`.
  2. The REST API returns `status: "connected"`.

---

## 6. Safe Evolution Rules

1. **Additive Schema:** New JSON response keys can be added, but existing keys must never be removed or change data types.
2. **Method Deprecation Policy:** While `POST` is recommended for mutating endpoints (`/connect`, `/disconnect`, `/reconnect`), `GET` support is guaranteed indefinitely for backward compatibility.
3. **No Behavioral Defaults Mutation:** Do not alter default timeouts, ports, or environment variable interpretations.
4. **Mandatory Test Verification:** Any modification touching the public interface must pass the contract test suite in `tests/unit/test_contracts.py`.
