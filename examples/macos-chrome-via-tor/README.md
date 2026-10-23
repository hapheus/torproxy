# macOS Chrome Incognito via Tor Proxy

This example demonstrates how to launch Google Chrome (or Chromium / Brave) on macOS in a completely isolated, anonymous Incognito window routed through `torproxy`.

It requires **zero Python scripts, virtual environments, or browser-automation libraries** on the host—just standard macOS terminal commands and Docker Compose.

---

## Architecture

```
 ┌──────────────────────────────────────────────────────────────┐
 │ macOS Host Desktop                                           │
 │                                                              │
 │  Terminal: ./open-chrome.sh                                  │
 │       │                                                      │
 │       ▼ (open -na "Google Chrome" --incognito)               │
 │  Google Chrome Incognito Window                              │
 │       │                                                      │
 │       │ HTTP Proxy: http://127.0.0.1:8118                    │
 └───────┼──────────────────────────────────────────────────────┘
         ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ torproxy Container (Docker Compose)                          │
 │                                                              │
 │  Privoxy (8118) ───► Tor SOCKS5 (9050) ───► Tor Network      │
 │                           ▲                                  │
 │  REST API (8080) ─────────┘ (Identity rotation & Health)     │
 └──────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- macOS 12+ (Apple Silicon or Intel).
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with Docker Compose v2.
- [Google Chrome](https://www.google.com/chrome/), [Brave](https://brave.com/), or Chromium installed in `/Applications`.

---

## Quick start

1. Start `torproxy` in this directory:
   ```bash
   docker compose up -d
   ```

2. Wait a few seconds for Tor circuit bootstrapping to finish:
   ```bash
   curl -s http://127.0.0.1:8080/status
   ```
   Once connected, it returns:
   ```json
   {"status": "connected", "ip": "185.220.101.5"}
   ```

3. Launch Chrome in an isolated Incognito window via the helper script:
   ```bash
   ./open-chrome.sh
   ```

   Or run the macOS one-liner directly from your terminal:
   ```bash
   open -na "Google Chrome" --args \
     --incognito \
     --proxy-server="http://127.0.0.1:8118" \
     "https://check.torproject.org"
   ```

4. The browser opens directly on `https://check.torproject.org`, displaying:
   > **"Congratulations. This browser is configured to use Tor."**

---

## Dynamic Circuit Rotation (New Identity)

To rotate to a new Tor exit node without restarting the browser or container:

```bash
# Request a new Tor identity via the REST control API
curl -s -X POST http://127.0.0.1:8080/reconnect

# Optionally request an exit node in a specific country (e.g. Germany)
curl -s -X POST "http://127.0.0.1:8080/reconnect?country=DE"
```

Reload the tab in your browser to verify that the exit IP address changed.

---

## Cleanup

When finished, shut down `torproxy`:

```bash
docker compose down
```
