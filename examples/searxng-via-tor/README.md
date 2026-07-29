# SearXNG Private Metasearch Through Tor with Docker Compose

This example runs a local **SearXNG metasearch engine** whose outbound search-engine requests use **torproxy**. SearXNG provides a browser-based search interface and a JSON search API while torproxy routes the configured outbound HTTP traffic through the Tor network.

> **Request path:** local user → SearXNG → `http://torproxy:8118` → Tor network → configured search engines.

## Architecture

```text
Browser or API client
         |
         | http://127.0.0.1:8080
         v
SearXNG metasearch ── http://torproxy:8118 ──> Tor network ──> Search engines
```

Both services share a private Docker network. Docker DNS resolves the `torproxy` service name, and only the SearXNG interface is published to the local machine.

## Prerequisites

- Docker Engine with Docker Compose v2
- Internet access for Tor and the enabled SearXNG search engines
- Local TCP port `8080`, or another port selected with `SEARXNG_HOST_PORT`

## Quick start

```sh
cd examples/searxng-via-tor
docker compose up -d
docker compose ps
```

Wait until torproxy reports `healthy`, then open:

```text
http://127.0.0.1:8080
```

If you select another host port, update both the published port and SearXNG's public base URL:

```sh
SEARXNG_HOST_PORT=8180 \
SEARXNG_BASE_URL=http://localhost:8180/ \
docker compose up -d
```

## How SearXNG routes searches through Tor

The included [`settings.yml`](settings.yml) configures one proxy for all outbound schemes:

```yaml
outgoing:
  proxies:
    all://:
      - http://torproxy:8118
  using_tor_proxy: true
  extra_proxy_timeout: 10
```

`using_tor_proxy: true` tells SearXNG and its engines that the configured route is Tor. The additional timeout accounts for Tor's higher latency. The default settings are still loaded, while this file overrides only the options required by the example.

At startup, SearXNG verifies that a configuration marked as Tor is actually using Tor. The `service_healthy` dependency ensures that this verification does not run before torproxy is ready.

The configuration also enables `json` in `search.formats`, allowing the local SearXNG instance to act as a search API.

## Test the SearXNG web interface

Open `http://127.0.0.1:8080`, enter a query such as `Tor Project`, and submit it. Results from multiple engines confirm that SearXNG can reach its upstream providers through the proxy.

Some search engines block Tor exit relays or return CAPTCHAs. Partial results and individual engine errors are therefore possible even when the proxy works correctly.

## Test the SearXNG JSON search API

```sh
curl --silent --show-error --fail --get \
  --data-urlencode "q=privacy search engine" \
  --data-urlencode "format=json" \
  "http://127.0.0.1:${SEARXNG_HOST_PORT:-8080}/search"
```

A successful response contains a JSON object with fields such as `query`, `number_of_results`, and `results`. Unlike the Browserless example, this is a native API response and is not wrapped in Chromium-generated HTML.

## Verify the Tor dependency

First confirm the internal proxy status:

```sh
docker compose exec torproxy \
  curl --silent --show-error http://127.0.0.1:8080/status
```

Then disconnect Tor:

```sh
docker compose exec torproxy \
  curl --silent --show-error --request POST \
  http://127.0.0.1:8080/disconnect
```

Repeat the SearXNG query. The configured engines should fail or return no results because their only configured route is unavailable. Reconnect Tor afterwards:

```sh
docker compose exec torproxy \
  curl --silent --show-error --request POST \
  http://127.0.0.1:8080/connect
```

Wait for torproxy to report `healthy` before searching again.

## Troubleshooting

| Symptom | Cause and solution |
| --- | --- |
| SearXNG returns few or no results | Individual search engines may block Tor. Inspect `docker compose logs searxng` for engine-specific errors. |
| SearXNG reports `not using Tor` during startup | torproxy was unavailable or not fully bootstrapped when SearXNG checked the route. Confirm that torproxy is healthy, then recreate SearXNG with `docker compose up -d`. |
| JSON search returns `403 Forbidden` | Confirm the included `settings.yml` is mounted and contains `json` under `search.formats`. |
| Port `8080` is already in use | Set both `SEARXNG_HOST_PORT` and `SEARXNG_BASE_URL` as shown above. |
| Searches time out | Tor adds latency. The example already adds proxy timeout headroom; review engine errors before increasing it further. |
| SearXNG reports permission warnings | `FORCE_OWNERSHIP=false` is intentional for the read-only settings bind mount and local example. |

## Security and privacy boundaries

The example binds SearXNG to `127.0.0.1` and disables its limiter for simple local testing. Do not expose this configuration publicly. A public SearXNG instance requires a strong secret, bot protection, rate limiting, a reverse proxy with TLS, and an operational review of enabled engines.

SearXNG reduces direct data sharing with search providers, and Tor changes the outbound network route. Neither removes all tracking signals or guarantees anonymity. Search queries are still sent to the selected upstream engines.

## Clean up

```sh
docker compose down
```

No persistent volumes are created.

## Further reading

- [SearXNG outgoing proxy settings](https://docs.searxng.org/admin/settings/settings_outgoing.html)
- [SearXNG search API](https://docs.searxng.org/dev/search_api.html)
- [SearXNG source repository](https://github.com/searxng/searxng)
- [torproxy project documentation](../../README.md)
