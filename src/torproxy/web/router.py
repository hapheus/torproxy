"""Translate HTTP paths to application operations."""

from torproxy.metrics import render_metrics
from torproxy.models import Response
from torproxy.queries import ProxyQueries
from torproxy.service import ControlFailure, InvalidInput, ProxyService


class Router:
    def __init__(self, service: ProxyService) -> None:
        self.service = service
        queries = ProxyQueries(service)
        self.read_routes = {
            "": queries.status,
            "status": queries.status,
            "ip": queries.ip,
            "health": queries.health,
            "v1/health": queries.health,
            "diagnostics": queries.diagnostics,
            "v1/diagnostics": queries.diagnostics,
            "metrics": self.metrics,
            "v1/metrics": self.metrics,
        }

    def dispatch(self, path: str, country: object = None, strict: object = None) -> Response:
        if path in self.read_routes:
            return self.read_routes[path]()
        if path in ("connect", "disconnect", "reconnect"):
            try:
                return Response(200, self.service.mutate(path, country, strict))
            except InvalidInput as error:
                return Response(400, {"error": str(error)})
            except ControlFailure as error:
                return Response(500, {"error": str(error)})
        return Response(
            404,
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
                    "/metrics",
                ],
            },
        )

    def metrics(self) -> Response:
        bootstrap, _ = self.service.get_tor_bootstrap_status()
        s = self.service.state
        with s.lock:
            return Response(
                200,
                render_metrics(
                    self.service.state.snapshot(),
                    bootstrap,
                    self.service.check_socks5_ready(),
                    self.service.settings.gateway_mode,
                    requests_total=s.requests_total,
                    requests_rejected_total=s.requests_rejected_total,
                    http_4xx_total=s.http_4xx_total,
                    http_5xx_total=s.http_5xx_total,
                    latency_total_seconds=s.request_latency_seconds_total,
                ),
                "text/plain; version=0.0.4; charset=utf-8",
            )
