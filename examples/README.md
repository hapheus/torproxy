# Docker Tor Proxy Examples: Practical Use Cases

This collection shows how Docker applications can route outbound HTTP traffic through **torproxy** and the Tor network. Each example is a self-contained Docker Compose use case with a runnable `docker-compose.yml`, detailed documentation, and verifiable test steps.

## Choose the right Docker Tor proxy example

| Use case | What it demonstrates | Start here |
| --- | --- | --- |
| Browser automation through Tor | Browserless Chromium loads web pages through the Tor HTTP proxy. Useful for authorised browser testing, privacy-conscious automation, and reproducible egress-IP checks. | [Browserless Chromium through Tor](browserless-chromium-via-tor/README.md) |

## Shared principles for Docker and Tor examples

- Published ports bind to `127.0.0.1`, so they are reachable only from the local machine.
- Every use case is a separate Docker Compose project that can be started and stopped from its own directory.
- Tor can add latency; requesting a new Tor connection does not guarantee a different exit IP address.
- Use these examples only for lawful, authorised access. Respect terms of service, `robots.txt`, rate limits, and applicable law.

New examples should follow the same pattern: a clearly named use case, an isolated runnable Compose file, and concrete verification steps.
