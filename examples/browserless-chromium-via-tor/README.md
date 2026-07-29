# Browserless Chromium Through a Tor Proxy with Docker Compose

This Docker Compose example connects **Browserless Chromium** to **torproxy**. Every Chromium session started by Browserless receives the default launch argument `--proxy-server=http://torproxy:8118`, routing HTTP and HTTPS requests through the Tor HTTP proxy. It is useful for authorised browser automation, browser regression tests, and verifiable Tor egress testing.

> **In short:** a local test client calls Browserless; Browserless uses `torproxy:8118`; torproxy routes traffic through Tor.

## Architecture: Browserless, Chromium, and Tor in Docker

```text
Test client on the host
        |
        | http://127.0.0.1:3000
        v
Browserless Chromium ── http://torproxy:8118 ──> Tor network ──> Target website
                                      |
                                      v
                         Tor status API (internal:8080)
```

Both containers use the private network Docker Compose creates automatically. Docker DNS resolves the `torproxy` name on that network, so no static IP address is needed and the Compose setup remains reproducible after restarts.

## Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose version`)
- A free local TCP port `3000`, or a different setting through `BROWSERLESS_PORT`
- Internet access so Tor can bootstrap and Chromium can open the test page

## Quick start: Run Chromium through the Tor HTTP proxy

Change to this example directory and start both services:

```sh
cd examples/browserless-chromium-via-tor
docker compose up -d
```

The first start can take a moment because torproxy must establish a Tor connection. Wait until `torproxy` reports `healthy`:

```sh
docker compose ps
```

Browserless is then available only locally at `http://127.0.0.1:3000`. For a local test, this example defaults to the `local-demo-token` token.

## Configuration: DEFAULT_LAUNCH_ARGS with a Tor proxy

The relevant Browserless section in [`docker-compose.yml`](docker-compose.yml) is:

```yaml
environment:
  - DEFAULT_LAUNCH_ARGS=["--proxy-server=http://torproxy:8118"]
```

`DEFAULT_LAUNCH_ARGS` passes the proxy argument to Chromium when every browser session starts. `http://torproxy:8118` points to the HTTP proxy on the same Docker network. In an environment with another reachable proxy, use an `http://IP:PORT` value instead, for example:

```yaml
- DEFAULT_LAUNCH_ARGS=["--proxy-server=http://192.0.2.10:8118"]
```

In the included use case, the service name is safer and easier to maintain than a container IP because Docker resolves it automatically.

The example also sets:

- `HOST=0.0.0.0`, making Browserless reachable inside the container through the Compose network and local port mapping.
- `TOKEN`, preventing the local Browserless API from being unprotected. Set a unique random token before using the stack beyond your own machine.
- `CONCURRENT=1` and `QUEUED=1`, keeping the example's resource use limited and easy to understand.
- `shm_size: 2gb`, giving Chromium sufficient Docker shared memory for stable operation.

## Test: Verify that Browserless loads through Tor

The test calls Browserless's `content` endpoint. Chromium opens the Tor Project IP-check endpoint through the configured proxy, and Browserless returns the page content rendered by Chromium.

```sh
curl --silent --show-error --fail --get \
  --data-urlencode "url=https://check.torproject.org/api/ip" \
  "http://127.0.0.1:${BROWSERLESS_PORT:-3000}/chromium/content?token=${BROWSERLESS_TOKEN:-local-demo-token}"
```

A successful response resembles:

```html
<html>
  <head>
    <meta name="color-scheme" content="light dark">
    <meta charset="utf-8">
  </head>
  <body>
    <pre>{"IsTor":true,"IP":"198.51.100.42"}</pre>
    <div class="json-formatter-container"></div>
  </body>
</html>
```

The exact markup can vary between Chromium versions. `IsTor: true` inside the `<pre>` element is the key confirmation. The displayed IP is an example and changes with the Tor exit relay.

### Why does a JSON API response become HTML?

The HTML wrapper comes from Chromium. When Chromium navigates to a URL that returns JSON, its built-in JSON viewer represents the response as a document containing elements such as `<html>`, `<body>`, and `<pre>`. The Browserless `content` endpoint then serialises that rendered DOM instead of returning the original HTTP response body byte for byte.

For example, an API response such as:

```json
{"ip":"109.70.100.14"}
```

can therefore be returned by Browserless as:

```html
<html>
  <head>...</head>
  <body>
    <pre>{"ip":"109.70.100.14"}</pre>
    <div class="json-formatter-container"></div>
  </body>
</html>
```

This is expected Browserless and Chromium behaviour; torproxy does not add or transform the HTML.

## Scraping APIs: Use an HTTP client instead of Chromium

Browserless is designed for browser use cases: rendering web pages, executing JavaScript, taking screenshots, creating PDFs, and running browser automation. A headless browser is usually the wrong tool for a JSON or REST API because it adds browser startup cost and turns the raw response into a rendered document.

For API requests, use an HTTP client such as `curl`, an application HTTP library, or a dedicated API client and configure it to use the torproxy HTTP proxy directly:

```text
http://torproxy:8118
```

From this example stack, the following command performs a direct API request through Tor and preserves the raw JSON response:

```sh
docker compose exec torproxy \
  curl --silent --show-error --fail \
  --proxy http://127.0.0.1:8118 \
  https://check.torproject.org/api/ip
```

Expected output:

```json
{"IsTor":true,"IP":"198.51.100.42"}
```

If an API genuinely has to be accessed within an existing browser session—for example, because it depends on browser cookies or authentication state—read the text content of the `<pre>` element and parse that text as JSON. Do not parse the complete HTML response as JSON.

### Cross-check with the torproxy status API

Because the status API is not published to the host, run the cross-check in the Tor container:

```sh
docker compose exec torproxy curl --silent --show-error http://127.0.0.1:8080/status
```

Expect a result similar to:

```json
{"status":"connected","ip":"198.51.100.42"}
```

The IP can vary between the two requests because of Tor circuits. What matters is a `connected` status and `IsTor: true` in the Browserless test.

## Troubleshooting Browserless and Tor

| Symptom | Cause and solution |
| --- | --- |
| `torproxy` is not yet `healthy` | Tor is still bootstrapping. Wait briefly and check `docker compose logs torproxy`. |
| Browserless returns `401` or `403` | The request token does not match `BROWSERLESS_TOKEN`. Restart after changing it: `docker compose up -d`. |
| The test does not return `IsTor: true` | First check the Browserless logs (`docker compose logs browserless`), then confirm that the proxy is connected through the status API. |
| Port `3000` is in use | Start with `BROWSERLESS_PORT=3100 docker compose up -d` and use the same port in the test. |
| Chromium is unstable or exits | Ensure Docker has enough memory available; the example already sets `shm_size: 2gb`. |

## Operations and security

The port mapping deliberately binds to `127.0.0.1`. Do not expose Browserless, the Tor HTTP proxy, or the Tor control API to the internet without protection. For non-local deployments, use at least a strong token, access controls, and TLS through an appropriate reverse proxy.

Tor does not automatically remove every identifying signal from browser automation and is not a guarantee of anonymity. Use HTTPS and perform only lawful, authorised requests with appropriate rate limits.

## Clean up

To stop and remove the example containers:

```sh
docker compose down
```

No persistent volumes are created.
