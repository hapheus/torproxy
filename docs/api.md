# REST API Reference

The `torproxy` container includes an internal REST API server written in Python. It provides status monitoring and operational control over the local Tor daemon without requiring external consumers to implement the Tor Control Protocol.

## 1. General Conventions

- **Default Port:** `8080` (configurable via `TORPROXY_API_PORT`)
- **Default Host Access:** `http://127.0.0.1:8080`
- **Docker Network Access:** `http://torproxy:8080`
- **Content-Type:** `application/json`
- **CORS:** `Access-Control-Allow-Origin: *` is returned on all responses. `OPTIONS` preflight requests are handled automatically (returning `204 No Content`).
- **Authentication:** None by default (guaranteeing 100% backward compatibility). When configured via `TORPROXY_API_TOKEN` (or `TORPROXY_API_KEY`), clients must authenticate using standard HTTP headers:
  - `Authorization: Bearer <token>`
  - `X-API-Key: <token>`
  Unauthenticated or invalid requests receive `401 Unauthorized` with `WWW-Authenticate: Bearer realm="torproxy"`.
  When `TORPROXY_API_ALLOW_ANONYMOUS_HEALTH=1` is enabled, `/health` (and `/v1/health`) allows unauthenticated probing for orchestrators while protecting all other endpoints.
- **Method Policy:** Both `GET` and `POST` methods are accepted by all endpoints. `POST` is recommended for state mutations (`/connect`, `/disconnect`, `/reconnect`), but `GET` is permanently preserved for backward compatibility.

---

## 2. Endpoints

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
    "error": null
  }
}
```

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
