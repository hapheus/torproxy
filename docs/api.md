# REST API Reference

The `torproxy` container includes an internal REST API server written in Python. It provides status monitoring and operational control over the local Tor daemon without requiring external consumers to implement the Tor Control Protocol.

## 1. General Conventions

- **Default Port:** `8080` (configurable via `TORPROXY_API_PORT`)
- **Default Host Access:** `http://127.0.0.1:8080`
- **Docker Network Access:** `http://torproxy:8080`
- **Content-Type:** `application/json`
- **CORS:** `Access-Control-Allow-Origin: *` is returned on successful read responses (`/status`, `/ip`, `/health`, `/metrics`, …). It is intentionally **not** sent on error responses (`401`, `403`, `4xx`/`5xx`) and never on mutations (`/connect`, `/disconnect`, `/reconnect`). `OPTIONS` preflight requests are handled automatically (returning `204 No Content`); preflight for mutations omits the wildcard header so foreign origins cannot read or trigger state changes.
- **CSRF protection on mutations:** Mutations (`/connect`, `/disconnect`, `/reconnect`, via `GET` or `POST`) presented with a browser `Origin` or `Referer` header whose host differs from the request `Host` are rejected with `403 Forbidden`. Requests without these headers (curl, scripts, Docker healthchecks) are unaffected, preserving the legacy `GET`-mutation contract. `POST` is still recommended.
- **Authentication:** None by default (guaranteeing 100% backward compatibility). When configured via `TORPROXY_API_TOKEN` (or `TORPROXY_API_KEY`), clients must authenticate using standard HTTP headers:
  - `Authorization: Bearer <token>`
  - `X-API-Key: <token>`
  Unauthenticated or invalid requests receive `401 Unauthorized` with `WWW-Authenticate: Bearer realm="torproxy"`.
  When `TORPROXY_API_ALLOW_ANONYMOUS_HEALTH=1` is enabled, `/health` (and `/v1/health`) allows unauthenticated probing for orchestrators while protecting all other endpoints. Anonymous health responses are minimal (ISSUE-14): only `{"status": "..."}` — country, ports and bootstrap details require authentication.
- **Correlation:** Every response carries `X-Request-ID` (echoed if sent by the client, otherwise generated). The server log includes the same ID with all paths redacted.
- **Method Policy:** Both `GET` and `POST` methods are accepted by all endpoints. `POST` is recommended for state mutations (`/connect`, `/disconnect`, `/reconnect`), but `GET` is permanently preserved for backward compatibility. Mutations carrying a foreign browser `Origin`/`Referer` are rejected with `403 Forbidden` (CSRF protection); mutations without those headers (curl, scripts) keep working unchanged.

---

## 2. Endpoints

### Quick Reference

| Endpoint | Methods | Status Codes | Description |
|---|---|---|---|
| [`/status`, `/`](#get--post-status-or-) | `GET`, `POST` | `200`, `500` | Connection status and current verified exit IP. |
| [`/ip`](#get--post-ip) | `GET`, `POST` | `200`, `503` | Current Tor egress IP (returns 503 while bootstrapping). |
| [`/health`](#get--post-health-or-v1health) | `GET`, `POST` | `200`, `503` | Diagnostic health state across Tor, proxies, and egress. |
| [`/reconnect`](#post--get-reconnect) | `POST`, `GET` | `200`, `400` | Request new circuit (`SIGNAL NEWNYM`); optional country change. |
| [`/disconnect`](#post--get-disconnect) | `POST`, `GET` | `200` | Pause Tor network traffic (`DisableNetwork=1`). |
| [`/connect`](#post--get-connect) | `POST`, `GET` | `200`, `400` | Resume Tor network traffic (`DisableNetwork=0`). |
| [`/diagnostics`](#get--post-diagnostics-or-v1diagnostics) | `GET`, `POST` | `200` | Telemetry (uptime, reconnect counts, bootstrap progress). |
| [`/metrics`](#get--post-metrics-or-v1metrics) | `GET`, `POST` | `200` | Prometheus exposition format metrics for scrapers. |

---

### GET | POST `/status` (or `/`)
Returns the current connection state and verified egress IP.

#### Response (Connected - 200 OK)
```json
{
  "status": "connected",
  "ip": "185.220.101.5"
}
```

#### Response (Connecting - 200 OK)
```json
{
  "status": "connecting",
  "ip": null,
  "detail": "Tor bootstrapping: Handshake"
}
```

#### Response (Disconnected - 200 OK)
```json
{
  "status": "disconnected",
  "ip": null
}
```

#### Response (Control Error - 500 Internal Server Error)
```json
{
  "error": "Failed to query Tor: <message>"
}
```

---

### GET | POST `/ip`
Returns the current public Tor egress IP address, or `503 Service Unavailable` if the proxy is not ready.

#### Response (Success - 200 OK)
```json
{
  "ip": "185.220.101.5"
}
```

#### Response (Unavailable - 503 Service Unavailable)
```json
{
  "error": "Could not retrieve IP. Proxy may be offline or connecting.",
  "detail": "<error details>"
}
```

---

### GET | POST `/connect`
Enables the Tor network connection (`SETCONF DisableNetwork=0`).

#### Parameters (Optional)
Parameters can be passed via query string (e.g. `?country=DE`) or JSON body for POST:
- `country` (`string` or `array[string]`): Comma-separated or array of 2-letter ISO 3166-1 alpha-2 country codes (e.g. `"DE"`, `"DE,AT"`, `["DE", "AT"]`). Pass `""` or `"any"` to remove country restriction.
- `strict_nodes` (`boolean` or `integer`): `1`/`true` or `0`/`false`. If true, circuits are refused if no exit nodes in the requested country are available.

#### Response (Success - 200 OK)
```json
{
  "action": "connect",
  "status": "success",
  "exit_country": "DE",
  "strict_nodes": true
}
```

#### Response (Error - 400 Bad Request)
```json
{
  "error": "Invalid ISO country code: 'XYZ'. Must be 2-letter alpha code."
}
```

#### Response (Error - 500 Internal Server Error)
```json
{
  "error": "Failed to enable Tor network: <message>"
}
```

---

### GET | POST `/disconnect`
Disables the Tor network connection (`SETCONF DisableNetwork=1`) and clears the cached egress IP.

#### Response (Success - 200 OK)
```json
{
  "action": "disconnect",
  "status": "success"
}
```

#### Response (Error - 500 Internal Server Error)
```json
{
  "error": "Failed to disable Tor network: <message>"
}
```

---

### GET | POST `/reconnect`
Requests a new Tor circuit (`SIGNAL NEWNYM`) and invalidates the cached egress IP.

#### Parameters (Optional)
Parameters can be passed via query string (e.g. `?country=DE`) or JSON body for POST:
- `country` (`string` or `array[string]`): Comma-separated or array of 2-letter ISO 3166-1 alpha-2 country codes (e.g. `"DE"`, `"DE,AT"`, `["DE", "AT"]`). Pass `""` or `"any"` to remove country restriction.
- `strict_nodes` (`boolean` or `integer`): `1`/`true` or `0`/`false`.

#### Response (Success - 200 OK)
```json
{
  "action": "reconnect",
  "status": "success",
  "exit_country": "DE",
  "strict_nodes": true
}
```

#### Response (Error - 400 Bad Request)
```json
{
  "error": "Invalid ISO country code: 'XYZ'. Must be 2-letter alpha code."
}
```

#### Response (Error - 500 Internal Server Error)
```json
{
  "error": "Failed to trigger reconnect: <message>"
}
```

---

### GET `/health` (or `/v1/health`)
Additive diagnostic endpoint providing detailed readiness and component states without modifying existing `/status` consumers.

#### Response (Healthy - 200 OK)
```json
{
  "status": "healthy",
  "tor": {
    "network_enabled": true,
    "bootstrapped": true,
    "progress": 100,
    "summary": "Done",
    "exit_country": "DE",
    "strict_nodes": true
  },
  "proxies": {
    "socks5": true
  },
  "egress": {
    "verified": true,
    "ip": "185.220.101.5",
    "error": null,
    "stale": false
  }
}
```

### IP Caching Semantics

- **Time-to-Live (TTL):** 30 seconds by default, tunable via `TORPROXY_CACHE_TTL`.
- **Single-flight (ISSUE-10):** concurrent `/ip`/`/status` calls share one upstream probe instead of stampeding the check service.
- **Stale signal:** `/health` includes `egress.stale`; when Tor is bootstrapped but egress verification fails, `/health` reports `degraded` with the reason.

---

### GET `/diagnostics` (or `/v1/diagnostics`)
Returns structured runtime diagnostics, process uptime, Tor circuit rebuild state, proxy readiness, and egress verification. Strictly omits any sensitive user data, client IPs, or Tor secrets.

#### Response (200 OK)
```json
{
  "uptime_seconds": 142.5,
  "started_at": "2026-10-18T15:00:00Z",
  "last_reconnect_at": "2026-10-18T15:05:00Z",
  "reconnect_count": 1,
  "tor": {
    "network_enabled": true,
    "bootstrapped": true,
    "progress": 100,
    "summary": "Done",
    "exit_country": "DE",
    "strict_nodes": true
  },
  "proxies": {
    "socks5_ready": true,
    "socks_port": 9050,
    "http_port": 8118
  },
  "egress": {
    "verified": true,
    "ip": "185.220.101.5",
    "error": null
  }
}
```

---

### GET `/metrics` (or `/v1/metrics`)
Returns lightweight Prometheus exposition text metrics (`text/plain; version=0.0.4`).

#### Response (200 OK)
```text
# HELP torproxy_uptime_seconds Total container API uptime in seconds
# TYPE torproxy_uptime_seconds gauge
torproxy_uptime_seconds 142.5

# HELP torproxy_reconnect_total Total circuit reconnect requests triggered
# TYPE torproxy_reconnect_total counter
torproxy_reconnect_total 1

# HELP torproxy_tor_bootstrapped Tor bootstrap status (1=done, 0=in progress)
# TYPE torproxy_tor_bootstrapped gauge
torproxy_tor_bootstrapped 1

# HELP torproxy_tor_bootstrap_progress Tor bootstrap progress percentage
# TYPE torproxy_tor_bootstrap_progress gauge
torproxy_tor_bootstrap_progress 100

# HELP torproxy_socks5_ready SOCKS5 listener probe (1=ready, 0=down)
# TYPE torproxy_socks5_ready gauge
torproxy_socks5_ready 1
```

---

### Unhandled Paths (404 Not Found)
Any request to an unsupported path returns `404 Not Found`.

#### Response (404 Not Found)
```json
{
  "error": "Not Found",
  "supported_paths": [
    "/status",
    "/ip",
    "/connect",
    "/disconnect",
    "/reconnect",
    "/health",
    "/diagnostics",
    "/metrics"
  ]
}
```

---

## 3. IP Caching Semantics

- **Time-to-Live (TTL):** 30 seconds.
- **Thread Safety:** Protected via an internal `threading.Lock` across concurrent handler threads.
- **Cache Eviction:** Automatically invalidated whenever `/connect`, `/disconnect`, or `/reconnect` is executed.
- **Verification Source:** Evaluated against `https://check.torproject.org/api/ip` through the local Privoxy proxy (`127.0.0.1:8118`).
- **Egress Guarantee:** Egress verification strictly requires `IsTor: true` from the check service. Responses with `IsTor: false` or missing verification fields are rejected and never cached or reported as connected.
- **Egress Failure Taxonomy (ISSUE-12, #76):** Transport failures of the probe surface as stable, operator-safe strings in the `error`/`detail` fields of `/ip`, `/health` and `/diagnostics` (the `status` values and JSON shapes are unchanged):
  - `local HTTP proxy unreachable` — connection refused to the local HTTP proxy on `127.0.0.1:8118` (e.g. Privoxy down; SOCKS5/Tor may still be healthy).
  - `Tor upstream unavailable via local HTTP proxy (HTTP <code>)` — the local proxy answered with a 5xx (e.g. because no Tor circuit is ready), so Tor/upstream is the problem, not the check service.
  - `egress check service returned HTTP <code>` — the check service itself answered with a 4xx through a healthy proxy (e.g. 429 rate-limit); this is not a Tor upstream failure. An open circuit breaker keeps the last cause and appends `(circuit breaker open)`.
  - `egress check service unreachable` — timeout or other transport failure after the local proxy, i.e. the check service itself could not be reached.
  - `Tor check service reported traffic NOT routed through Tor (IsTor=false)` and the other validation errors (missing `IsTor`, oversized/invalid response) — the check service answered definitively and is not retried.
