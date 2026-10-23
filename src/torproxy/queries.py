"""Read-only application queries, independent of HTTP and concrete I/O."""

from datetime import datetime, timezone
from typing import Any

from torproxy.models import Response
from torproxy.service import ProxyService


def iso_time(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProxyQueries:
    def __init__(self, service: ProxyService) -> None:
        self.service = service

    def status(self) -> Response:
        response, error = self.service.send_tor_command("GETCONF DisableNetwork")
        if error:
            return Response(500, {"error": f"Failed to query Tor: {error}"})
        if "DisableNetwork=0" not in (response or ""):
            return Response(200, {"status": "disconnected", "ip": None})
        bootstrap, error = self.service.get_tor_bootstrap_status()
        if not bootstrap or not bootstrap["bootstrapped"]:
            detail = bootstrap["summary"] if bootstrap else error or "Unknown bootstrap status"
            return Response(
                200,
                {
                    "status": "connecting",
                    "ip": None,
                    "detail": f"Tor bootstrapping: {detail}",
                },
            )
        ip, error = self.service.get_current_ip()
        if ip:
            return Response(200, {"status": "connected", "ip": ip})
        return Response(
            200,
            {
                "status": "connecting",
                "ip": None,
                "detail": f"Failed to route traffic (Tor bootstrapping?): {error}",
            },
        )

    def ip(self) -> Response:
        ip, error = self.service.get_current_ip()
        return (
            Response(200, {"ip": ip})
            if ip
            else Response(
                503,
                {
                    "error": "Could not retrieve IP. Proxy may be offline or connecting.",
                    "detail": error,
                },
            )
        )

    def health(self) -> Response:
        response, error = self.service.send_tor_command("GETCONF DisableNetwork")
        if error:
            return Response(
                503,
                {
                    "status": "unhealthy",
                    "error": f"Failed to query Tor control: {error}",
                },
            )
        snapshot = self.service.state.snapshot()
        enabled = "DisableNetwork=0" in (response or "")
        tor = {
            "network_enabled": enabled,
            "bootstrapped": False,
            "progress": 0,
            "exit_country": snapshot.country,
            "strict_nodes": snapshot.strict_nodes,
        }
        body: dict[str, Any] = {
            "status": "disconnected",
            "tor": tor,
            "proxies": {"socks5": False},
            "egress": {"verified": False, "ip": None},
        }
        if not enabled:
            return Response(200, body)
        bootstrap, error = self.service.get_tor_bootstrap_status()
        socks = self.service.check_socks5_ready()
        body["proxies"]["socks5"] = socks
        if not bootstrap or not bootstrap.get("bootstrapped"):
            body["status"] = "bootstrapping"
            tor.update(
                progress=bootstrap.get("progress", 0) if bootstrap else 0,
                summary=bootstrap.get("summary", error or "Bootstrapping")
                if bootstrap
                else error or "Unknown",
            )
            return Response(200, body)
        ip, error = self.service.get_current_ip()
        body["status"] = "healthy" if ip and socks else "degraded"
        tor.update(bootstrapped=True, progress=100, summary="Done")
        body["egress"].update(verified=bool(ip), ip=ip, error=error if not ip else None)
        return Response(200, body)

    def diagnostics(self) -> Response:
        snapshot = self.service.state.snapshot()
        bootstrap, error = self.service.get_tor_bootstrap_status()
        socks = self.service.check_socks5_ready()
        response, _ = self.service.send_tor_command("GETCONF DisableNetwork")
        enabled = "DisableNetwork=0" in (response or "")
        ip, ip_error = self.service.get_current_ip() if enabled else (None, None)
        return Response(
            200,
            {
                "uptime_seconds": round(snapshot.uptime, 2),
                "started_at": iso_time(snapshot.started_at),
                "last_reconnect_at": iso_time(snapshot.last_reconnect),
                "reconnect_count": snapshot.reconnect_count,
                "tor": {
                    "network_enabled": enabled,
                    "bootstrapped": bool(bootstrap and bootstrap.get("bootstrapped")),
                    "progress": bootstrap.get("progress", 0) if bootstrap else 0,
                    "summary": bootstrap.get("summary", error or "Unknown")
                    if bootstrap
                    else error or "Unknown",
                    "exit_country": snapshot.country,
                    "strict_nodes": snapshot.strict_nodes,
                },
                "proxies": {
                    "socks5_ready": socks,
                    "socks_port": self.service.settings.socks_port,
                    "http_port": self.service.settings.proxy_port,
                },
                "egress": {"verified": bool(ip), "ip": ip, "error": ip_error if not ip else None},
            },
        )
