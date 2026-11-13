# Model Context Protocol (MCP) Integration

`torproxy` features a built-in, zero-dependency **Model Context Protocol (MCP)** server enabling AI coding assistants (such as Claude Desktop, Cursor, Antigravity, and custom LLM agent pipelines) to inspect Tor status, trigger circuit renewals, and perform anonymized HTTP/HTTPS or `.onion` network requests without manual script execution or external bridge daemons.

---

## 1. Quickstart Configuration Examples

### Claude Desktop (`claude_desktop_config.json`)

Connect Claude Desktop to your running `torproxy` container over Stdio without exposing any network ports:

```json
{
  "mcpServers": {
    "torproxy": {
      "command": "docker",
      "args": ["exec", "-i", "torproxy", "torproxy", "mcp"]
    }
  }
}
```

*When token authentication (`TORPROXY_API_TOKEN`) is enabled:*
```json
{
  "mcpServers": {
    "torproxy": {
      "command": "docker",
      "args": ["exec", "-i", "-e", "TORPROXY_API_TOKEN=your-token", "torproxy", "torproxy", "mcp"]
    }
  }
}
```

---

### Cursor (`.cursor/mcp.json`)

#### Option A: HTTP / SSE (Port 2501)
```json
{
  "mcpServers": {
    "torproxy": {
      "url": "http://127.0.0.1:2501/sse"
    }
  }
}
```

*With authentication (`TORPROXY_API_TOKEN`):*
```json
{
  "mcpServers": {
    "torproxy": {
      "url": "http://127.0.0.1:2501/sse?token=your-token",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    }
  }
}
```

#### Option B: Stdio Transport via Docker
```json
{
  "mcpServers": {
    "torproxy": {
      "command": "docker",
      "args": ["exec", "-i", "torproxy", "torproxy", "mcp"]
    }
  }
}
```

#### Option C: Zero-Config Project Auto-Discovery (`.mcp.json`)
The repository includes a root-level `.mcp.json` automatically detected by Cursor and [cursor.directory](https://cursor.directory) for on-demand execution:
```json
{
  "mcpServers": {
    "torproxy": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "hapheus/torproxy:latest", "mcp"]
    }
  }
}
```

---

### Smithery.ai Integration (`smithery.yaml`)

`torproxy` includes a root-level `smithery.yaml` configuration allowing zero-config import, automated live-healthcheck validation, and one-click installation via [Smithery.ai](https://smithery.ai):

```bash
npx -y @smithery/cli install hapheus/torproxy --client claude
```

---

### Antigravity & Gemini CLI (`settings.json`)

```json
{
  "mcpServers": {
    "torproxy": {
      "command": "docker",
      "args": ["exec", "-i", "torproxy", "torproxy", "mcp"]
    }
  }
}
```

---

### Docker Compose (`docker-compose.yml`)

Publish port `2501` for SSE network clients:

```yaml
services:
  torproxy:
    image: hapheus/torproxy:latest
    container_name: torproxy
    restart: unless-stopped
    ports:
      - "127.0.0.1:8118:8118"   # HTTP/HTTPS Proxy (Privoxy)
      - "127.0.0.1:9050:9050"   # SOCKS5 Proxy (Tor)
      - "127.0.0.1:8080:8080"   # REST API
      - "127.0.0.1:2501:2501"   # MCP Server (SSE)
    environment:
      - TORPROXY_MCP_ENABLED=true
      - TORPROXY_MCP_PORT=2501
      # Optional:
      # - TORPROXY_API_TOKEN=your-token
```

---

## 2. Architecture & Dual-Transport Support

The MCP server adheres strictly to the `torproxy` zero-dependency standard (using pure Python standard library: `http.server`, `json`, `threading`, `queue`).

It supports two distinct transport protocols:

1. **Stdio Transport (`torproxy mcp`):**
   - Designed for local processes and container execution: `docker exec -i torproxy torproxy mcp`.
   - Communicates using newline-delimited JSON-RPC 2.0 frames over `stdin` and `stdout`.
   - All internal diagnostics and operational warnings are directed to `stderr` to maintain clean protocol isolation.
   - Recommended for **Claude Desktop**.
2. **HTTP/SSE & Streamable HTTP Transport (Port 2501):**
   - Runs as a non-blocking daemon thread on port `2501` (`TORPROXY_MCP_PORT=2501`).
   - Supports both **HTTP/SSE** (`GET /sse` or `GET /mcp` for Server-Sent Events stream initialization + `POST /messages?sessionId=...` for JSON-RPC dispatch) and **Streamable HTTP** (direct JSON-RPC `POST` to `/mcp`, `/sse`, or `/`).
   - Recommended for **Cursor**, **Antigravity**, and remote container orchestrators.

---

## 3. Available Tools

| Tool | Parameters | Description |
|---|---|---|
| `torproxy_fetch` | `url` *(required)*, `method`, `headers`, `body`, `timeout`, `max_bytes` | **Zero-config fetch:** Execute an HTTP/HTTPS or `.onion` request routed strictly through Tor without shell or curl. |
| `torproxy_status` | *(none)* | Live status JSON: bootstrap progress, egress IP, and GeoIP metadata. |
| `torproxy_get_ip` | *(none)* | Current egress IP address verified through Tor. |
| `torproxy_reconnect` | `country` *(optional)*, `strict` *(optional)* | Signal Tor for a new identity/circuit (`SIGNAL NEWNYM`), optionally changing exit nodes. |
| `torproxy_connect` | `country` *(optional)*, `strict` *(optional)* | Enable the Tor network (`SETCONF DisableNetwork=0`). |
| `torproxy_disconnect` | *(none)* | Disable the Tor network (`SETCONF DisableNetwork=1`). |
| `torproxy_health` | *(none)* | Probe status of Tor, Privoxy HTTP, and SOCKS readiness. |
| `torproxy_diagnostics` | *(none)* | Comprehensive telemetry (circuits, cache age, reconnection stats, gateway mode). |

### `torproxy_fetch` Details
AI agents frequently need to fetch web pages or inspect `.onion` hidden services without having terminal or shell access on the host. `torproxy_fetch` executes requests from within the container routed through the local Privoxy proxy, guaranteeing zero clearnet leaks and remote Tor DNS resolution.

**Arguments:**
- `url` (string, required): Destination URL (`http://...`, `https://...`, or `http://...onion`).
- `method` (string, optional, default: `"GET"`): HTTP method (`GET`, `POST`, `PUT`, `DELETE`, `HEAD`).
- `headers` (object, optional): Key-value string dictionary of HTTP headers.
- `body` (string, optional): String payload for POST or PUT requests.
- `timeout` (number, optional, default: `30`): Timeout in seconds.
- `max_bytes` (integer, optional, default: `1048576`): Caps response body length to protect LLM context windows.

---

## 4. Available Resources

| URI | MIME Type | Description |
|---|---|---|
| `torproxy://status` | `application/json` | Real-time JSON status snapshot of the proxy instance. |
| `torproxy://metrics` | `text/plain` | Prometheus telemetry metrics export. |

---

## 5. Security & Authentication

When `TORPROXY_API_TOKEN` is configured:
- **Stdio:** Pass the token via environment variable (`-e TORPROXY_API_TOKEN=...`).
- **SSE:** Authenticate using one of:
  - `Authorization: Bearer <token>`
  - `X-API-Key: <token>`
  - URL query parameter: `/sse?token=<token>` (useful for browser/EventSource clients where headers cannot be modified).

---

## 6. Official MCP Registry Manifest

`torproxy` includes a standardized [`server.json`](../server.json) manifest conforming to the Model Context Protocol Registry specification (`registry.modelcontextprotocol.io`):

- **Namespace:** `io.github.hapheus/torproxy`
- **Distribution:** OCI container image (`docker.io/hapheus/torproxy:<version>`)
- **Transport:** `stdio` via `torproxy mcp`
- **Validation:** Can be validated locally using the official publisher tool:
  ```bash
  mcp-publisher validate server.json
  ```
