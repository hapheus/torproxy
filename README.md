# torproxy

A small Docker image that provides an HTTP proxy on port `8118` and sends its traffic through Tor. It also offers a small local API on port `8080` to view and control the connection.

## Why use Tor?

Tor sends requests through several independent servers before they reach their destination. As a result, the destination sees a Tor exit IP address instead of your normal public IP address. This can improve privacy when an application needs to use an HTTP proxy.

> **Note:** Tor is not a guarantee of anonymity and does not protect data sent without encryption. Use `https://` whenever possible. Because traffic takes a longer route, websites and downloads can be noticeably slower than with a normal internet connection.

## Quick start

```sh
docker compose up -d
curl -v -x http://127.0.0.1:8118 https://check.torproject.org/api/ip
```

Compose makes both ports available only on this computer (`127.0.0.1`). This is intentional: neither the proxy nor the control API has a password.

## Usage

Configure software that supports an HTTP proxy with:

| Setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `8118` |
| Scheme | `http` |

For a direct Docker run:

```sh
docker run -d --name torproxy --restart unless-stopped \
  -p 127.0.0.1:8118:8118 \
  -p 127.0.0.1:8080:8080 \
  hapheus/torproxy:latest
```

### Use from other Docker containers

Containers in the same Docker network can use `torproxy:8118` as their proxy. They can also reach the control API at `torproxy:8080`, so only connect containers you trust to that network.

```sh
curl -v -x http://torproxy:8118 https://check.torproject.org/api/ip
```

## Is it ready?

The image reports `healthy` only after Tor is connected and the proxy can be used. Starting the container is quick, but establishing a Tor connection can take a little longer.

With Compose, inspect the health state with:

```sh
docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q torproxy)"
```

For the direct `docker run` example, use:

```sh
docker inspect --format '{{.State.Health.Status}}' torproxy
```

## Status and control API

The container includes a small JSON API. With Compose, it is available on this computer at `http://127.0.0.1:8080`. Containers in the same Docker network can access it too. It has no password, so do not make it publicly available.

| Method | Endpoint                                         | Short description | Example response |
| --- |--------------------------------------------------| --- | --- |
| `GET` or `POST` | [`/status`](http://localhost:8080/status)        | Shows the connection state and current Tor IP. | `{"status":"connected","ip":"109.70.100.9"}` |
| `GET` | [`/ip`](http://localhost:8080/ip)                | Shows the current Tor IP. Returns `503` until an IP is available. | `{"ip":"109.70.100.9"}` |
| `GET` or `POST` | [`/connect`](http://localhost:8080/connect)      | Establishes or resumes the Tor connection. | `{"action":"connect","status":"success"}` |
| `GET` or `POST` | [`/disconnect`](http://localhost:8080/disconnect) | Disconnects from Tor and blocks proxy traffic. | `{"action":"disconnect","status":"success"}` |
| `GET` or `POST` | [`/reconnect`](http://localhost:8080/reconnect)  | Creates a new Tor connection and requests a new IP. | `{"action":"reconnect","status":"success"}` |

For `/status`, `connected` means the proxy is ready, `connecting` means Tor is still starting, and `disconnected` means it was stopped with `/disconnect`. The `ip` value is `null` until Tor is ready or while it is disconnected.

`/reconnect` asks Tor for a new connection and exit IP. Tor may rate-limit this request, so a different IP cannot be guaranteed every time.

Examples:

```sh
curl http://127.0.0.1:8080/status
curl -X POST http://127.0.0.1:8080/reconnect
curl -X POST http://127.0.0.1:8080/disconnect
```

The IP result is cached for up to 30 seconds. `/disconnect` and `/reconnect` clear that cache.

## Settings

The default settings work without any extra file. To change a port, create a `.env` file in the project folder, for example:

```dotenv
TORPROXY_HOST_PORT=8118
TORPROXY_LISTEN_ADDRESS=0.0.0.0
TORPROXY_LISTEN_PORT=8118
TORPROXY_API_PORT=8080
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `TORPROXY_HOST_PORT` | `8118` | Port on your computer for the proxy. |
| `TORPROXY_LISTEN_ADDRESS` | `0.0.0.0` | Address the proxy uses inside its container. Usually leave this unchanged. |
| `TORPROXY_LISTEN_PORT` | `8118` | Proxy port inside the container. Usually leave this unchanged. |
| `TORPROXY_API_PORT` | `8080` | Port for the status and control API. |

The settings are checked when the container starts. Tor's own internal ports are private to the container and are never exposed.

## Safety

This project is deliberately small: it has no user accounts, password protection, or saved state. Its local API can connect, disconnect, and renew the Tor connection.

Do not expose ports `8118` or `8080` to the internet. Anyone who can reach the proxy can use it, and anyone who can reach the API can control its connection.

The proxy is configured to send all requests through Tor. Tor's internal services stay private inside the container.

## License

Released under the [MIT License](LICENSE).

## 💝 Support the Project

If you find this project helpful, consider showing some support:

- ☕ Buy me a coffee: Send a tip via [PayPal](https://paypal.me/hapheus).
- ❤️ Charity Donation: Donate to [Österreichische Krebshilfe (Austrian Cancer Aid)](https://www.krebshilfe.net/) or any local animal welfare organization.
- 🎯 Dream Support: I would love some tickets for the World Darts Championship at Ally Pally (Alexandra Palace) – hopefully, I will make it there one day!
