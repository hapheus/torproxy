# CRW Web Scraper Through a Tor Proxy with Docker Compose

This example runs the self-hosted **CRW web scraper** from `ghcr.io/us/crw:latest` behind **torproxy**. CRW routes its scrape, crawl, and map requests through the Tor HTTP proxy and returns structured web content for applications, data pipelines, and AI agents.

Use this setup when an HTTP scraping API is a better fit than a full browser. CRW can turn a web page into Markdown or JSON without requiring every client to manage proxy settings itself.

> **Request path:** API client → CRW → `http://torproxy:8118` → Tor network → target website.

## Architecture

```text
Local API client
       |
       | http://127.0.0.1:3000/v1/...
       v
CRW web scraper ── http://torproxy:8118 ──> Tor network ──> Target website
```

Docker Compose creates a private network and resolves `torproxy` through Docker DNS. Only the CRW API is published, and it binds to the local loopback interface.

## Prerequisites

- Docker Engine with Docker Compose v2
- Internet access for Tor bootstrap and target requests
- Local TCP port `3000`, or another port selected with `CRW_HOST_PORT`

## Quick start

```sh
cd examples/crw-web-scraper-via-tor
docker compose up -d
docker compose ps
```

Wait until `torproxy` reports `healthy`. CRW is then available at `http://127.0.0.1:3000`.

## How CRW uses the Tor proxy

The Compose file configures CRW's crawler-level proxy:

```yaml
environment:
  CRW_CRAWLER__PROXY: http://torproxy:8118
```

CRW applies this proxy to its HTTP fetch path and proxy-capable JavaScript-rendering paths. A configured proxy is fail-closed: if the proxy is unavailable or a renderer cannot use it, the request fails instead of silently using the host's direct connection.

The crawler-level setting covers scrape, crawl, and map operations. A request-specific CRW proxy option can override the server setting, so do not accept arbitrary request bodies from untrusted users.

This minimal example focuses on HTTP scraping and explicitly sets `render_js: false` in its test requests. The base CRW image uses LightPanda as its default JavaScript renderer, and LightPanda cannot route through a proxy. JavaScript-heavy pages therefore require an additional proxy-capable Chrome renderer; CRW will fail closed when one is not configured.

## Test a CRW scrape through Tor

Call CRW's native `/v1/scrape` endpoint and ask it to retrieve the Tor Project IP-check API:

```sh
curl --silent --show-error --fail \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{"url":"https://check.torproject.org/api/ip","formats":["markdown"],"render_js":false}' \
  "http://127.0.0.1:${CRW_HOST_PORT:-3000}/v1/scrape"
```

The CRW response is a JSON object. Its scraped content should contain an IP-check result similar to:

```json
{"IsTor":true,"IP":"198.51.100.42"}
```

The exact outer CRW response fields can change between versions. Verify the target content contains `IsTor` set to `true`; the exit IP itself is expected to change.

For a normal webpage-to-Markdown test:

```sh
curl --silent --show-error --fail \
  --request POST \
  --header "Content-Type: application/json" \
  --data '{"url":"https://example.com","formats":["markdown","links"],"render_js":false}' \
  "http://127.0.0.1:${CRW_HOST_PORT:-3000}/v1/scrape"
```

## Verify fail-closed behaviour

Disconnect Tor through the internal torproxy API:

```sh
docker compose exec torproxy \
  curl --silent --show-error --request POST \
  http://127.0.0.1:8080/disconnect
```

Repeat the scrape request. It should fail rather than fetch through the machine's normal public IP. Re-enable Tor afterwards:

```sh
docker compose exec torproxy \
  curl --silent --show-error --request POST \
  http://127.0.0.1:8080/connect
```

Wait for torproxy to become healthy before running another scrape.

## Scrape, crawl, or map?

| CRW operation | Use case |
| --- | --- |
| `/v1/scrape` | Extract one webpage as Markdown, links, or structured content. |
| `/v1/crawl` | Follow links across an authorised website with explicit page and depth limits. |
| `/v1/map` | Discover URLs before deciding which pages should be scraped. |

Start with one-page scrapes. Add conservative concurrency, depth, and page limits before crawling a site through Tor.

## Troubleshooting

| Symptom | Cause and solution |
| --- | --- |
| CRW cannot reach the target | Confirm that torproxy is `healthy` and inspect `docker compose logs torproxy`. |
| Port `3000` is already in use | Start with `CRW_HOST_PORT=3100 docker compose up -d` and call port `3100`. |
| The response reports a proxy or renderer error | CRW is preventing a direct-connection fallback. Check `docker compose logs crw` instead of removing the proxy setting. |
| CRW reports that LightPanda cannot use the proxy | Use `render_js: false` for HTTP scraping. Add a proxy-capable Chrome renderer if the authorised target genuinely requires JavaScript. |
| A website blocks or rate-limits the request | Tor exit relays are frequently restricted. Respect the response and the site's policies; do not attempt to bypass access controls. |

## Security and responsible scraping

The CRW API has powerful network-fetching capabilities. This local example binds it to `127.0.0.1`; do not expose it publicly without authentication, request validation, rate limiting, and network-level access controls.

Only scrape content you are authorised to access. Respect `robots.txt`, terms of service, copyright, privacy requirements, and reasonable request rates. Tor changes the network route but does not grant permission to collect data.

## Clean up

```sh
docker compose down
```

No persistent volumes are created.

## Further reading

- [CRW proxy and rotation documentation](https://docs.fastcrw.com/proxies/)
- [CRW source repository](https://github.com/us/crw)
- [torproxy project documentation](../../README.md)
