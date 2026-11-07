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

    def _geoip_info(self) -> dict[str, Any]:
        # ISSUE-117: additive observability so a silent fallback to
        # the bundled GeoIP DB (e.g. upstream file outgrew the size
        # limit) is visible in /status instead of only in logs.
        info: dict[str, Any] = {
            "auto_update": self.service.settings.geoip_auto_update,
            "source": "unknown",
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error": None,
        }
        snapshot = self.service.geoip_snapshot()
        if snapshot:
            for key in ("source", "last_attempt_at", "last_success_at", "last_error"):
                if key in snapshot:
                    info[key] = snapshot[key]
            for key in ("v4_bytes", "v6_bytes"):
                if isinstance(snapshot.get(key), int):
                    info[key] = snapshot[key]
        return info

    def status(self) -> Response:
        response, error = self.service.send_tor_command("GETCONF DisableNetwork")
        if error:
            return Response(500, {"error": f"Failed to query Tor: {error}"})
        if "DisableNetwork=0" not in (response or ""):
            return Response(
                200, {"status": "disconnected", "ip": None, "geoip": self._geoip_info()}
            )
        bootstrap, error = self.service.get_tor_bootstrap_status()
        if not bootstrap or not bootstrap["bootstrapped"]:
            detail = bootstrap["summary"] if bootstrap else error or "Unknown bootstrap status"
            return Response(
                200,
                {
                    "status": "connecting",
                    "ip": None,
                    "detail": f"Tor bootstrapping: {detail}",
                    "geoip": self._geoip_info(),
                },
            )
        ip, error = self.service.get_current_ip()
        if ip:
            return Response(200, {"status": "connected", "ip": ip, "geoip": self._geoip_info()})
        return Response(
            200,
            {
                "status": "connecting",
                "ip": None,
                "detail": f"Failed to route traffic (Tor bootstrapping?): {error}",
                "geoip": self._geoip_info(),
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
        # ISSUE-10: additive `stale` signal; ISSUE-06: never claim healthy
        # when the egress check itself failed — report `degraded` with a
        # reason instead of a misleading "connecting".
        stale = self.service.cache_is_stale()
        body: dict[str, Any] = {
            "status": "disconnected",
            "tor": tor,
            "proxies": {"socks5": False},
            "egress": {"verified": False, "ip": None, "stale": stale},
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
        tor.update(bootstrapped=True, progress=100, summary="Done")
        if ip and socks:
            body["status"] = "healthy"
            body["egress"].update(
                verified=True, ip=ip, error=None, stale=self.service.cache_is_stale()
            )
        else:
            # Tor is up but egress verification failed (e.g. check.torproject.org
            # unreachable): degraded, not "connecting"/"healthy".
            body["status"] = "degraded"
            body["egress"].update(
                verified=False,
                ip=ip,
                error=error or "egress verification failed",
                stale=stale,
            )
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
                "gateway": {
                    "enabled": self.service.settings.gateway_mode,
                    "trans_port": self.service.settings.trans_port,
                    "dns_port": self.service.settings.dns_port,
                },
                "egress": {"verified": bool(ip), "ip": ip, "error": ip_error if not ip else None},
            },
        )
