# torproxy

A small, non-root Docker image that exposes an HTTP proxy on port `8118` and routes all traffic through Tor.

## Quick start

```sh
docker compose up -d
curl --proxy http://127.0.0.1:8118 https://check.torproject.org/api/ip
```

The Compose file binds the proxy to `127.0.0.1` only. This is intentional: an unauthenticated proxy must not be exposed to untrusted networks. The published image is [`hapheus/torproxy`](https://hub.docker.com/r/hapheus/torproxy).

## Usage

Configure software that supports an HTTP proxy with:

| Setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `8118` |
| Scheme | `http` |

For a direct Docker run:

```sh
docker run -d --name torproxy --restart unless-stopped -p 127.0.0.1:8118:8118 hapheus/torproxy:latest
```

## Health check

The image includes a Docker health check. It becomes healthy only after Privoxy can reach the Tor Project check endpoint through Tor; process startup alone is not considered healthy. Tor bootstrapping can take up to 90 seconds.

Inspect it with:

```sh
docker inspect --format '{{.State.Health.Status}}' torproxy
```

## Configuration

Copy `.env.example` to `.env` before using Compose when the defaults do not suit your host:

```sh
cp .env.example .env
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `TORPROXY_HOST_PORT` | `8118` | Host port published by Docker Compose. |
| `TORPROXY_LISTEN_ADDRESS` | `0.0.0.0` | IPv4 address Privoxy listens on inside the container. |
| `TORPROXY_LISTEN_PORT` | `8118` | Privoxy port inside the container. |

The address and port are validated on startup. Tor's SOCKS listener is intentionally fixed to `127.0.0.1:9050` and is never published.

## Scope and security

This project deliberately has no authentication, control port, metrics endpoint, persistent state, or IP-rotation API. It is a minimal single-purpose proxy. Do not publish port `8118` on a public interface unless you add appropriate network controls outside this image.

[`docker/privoxy.config.template`](docker/privoxy.config.template) forwards all requests through Tor's internal SOCKS listener. [`docker/torrc`](docker/torrc) keeps that SOCKS listener private to the container.

## Docker Hub publishing

The GitHub Actions workflow publishes to Docker Hub when changes reach `main` and when a `v*` tag is pushed:

| Git ref | Docker tag |
| --- | --- |
| `main` | `latest` |
| `v1.2.3` | `v1.2.3` |

Create this repository secret before enabling publishing:

- `DOCKERHUB_TOKEN`: Docker Hub access token with permission to push the repository.

The workflow publishes `hapheus/torproxy` and the source repository is `hapheus/torproxy`.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and use [Conventional Commits](https://www.conventionalcommits.org/).

## License

Released under the [MIT License](LICENSE).

## 💝 Support the Project

If you find this project helpful, consider showing some support:

- ☕ Buy me a coffee: Send a tip via [PayPal](https://paypal.me/hapheus).
- ❤️ Charity Donation: Donate to [Österreichische Krebshilfe (Austrian Cancer Aid)](https://www.krebshilfe.net/) or any local animal welfare organization.
- 🎯 Dream Support: I would love some tickets for the World Darts Championship at Ally Pally (Alexandra Palace) – hopefully, I will make it there one day!
