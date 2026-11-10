"""Translate HTTP paths to application operations."""

from torproxy.models import Response
from torproxy.queries import ProxyQueries
from torproxy.service import ControlFailure, InvalidInput, ProxyService


class Router:
    def __init__(self, service: ProxyService) -> None:
        self.service = service
        self.queries = ProxyQueries(service)
        self.read_routes = {
            "": self.queries.status,
            "status": self.queries.status,
            "ip": self.queries.ip,
            "health": self.queries.health,
            "v1/health": self.queries.health,
            "diagnostics": self.queries.diagnostics,
            "v1/diagnostics": self.queries.diagnostics,
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
        return self.queries.metrics()
