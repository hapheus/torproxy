"""Prometheus serialization without network access."""

from collections.abc import Mapping

from torproxy.state import Snapshot


def render_metrics(
    snapshot: Snapshot,
    bootstrap: Mapping | None,
    socks: bool,
    gateway_mode: bool = False,
    *,
    requests_total: int = 0,
    requests_rejected_total: int = 0,
    http_4xx_total: int = 0,
    http_5xx_total: int = 0,
    latency_total_seconds: float = 0.0,
) -> str:
    values: list[tuple[str, str, str, object]] = [
        (
            "uptime_seconds",
            "Total container API uptime in seconds",
            "gauge",
            round(snapshot.uptime, 2),
        ),
        (
            "reconnect_total",
            "Total circuit reconnect requests triggered",
            "counter",
            snapshot.reconnect_count,
        ),
        (
            "tor_bootstrapped",
            "Tor bootstrap status (1=done, 0=in progress)",
            "gauge",
            int(bool(bootstrap and bootstrap.get("bootstrapped"))),
        ),
        (
            "tor_bootstrap_progress",
            "Tor bootstrap progress percentage",
            "gauge",
            bootstrap.get("progress", 0) if bootstrap else 0,
        ),
        ("socks5_ready", "SOCKS5 listener probe (1=ready, 0=down)", "gauge", int(socks)),
        (
            "gateway_mode",
            "Transparent Tor gateway mode status (1=enabled, 0=disabled)",
            "gauge",
            int(gateway_mode),
        ),
        (
            "strict_nodes",
            "Tor StrictNodes setting (1=strict, 0=flexible)",
            "gauge",
            int(snapshot.strict_nodes),
        ),
        ("exit_country_info", "Configured exit country code", "gauge", 1),
        # ISSUE-11 / ISSUE-14: overload rejections and HTTP observability.
        (
            "requests_rejected_total",
            "Requests rejected due to worker saturation (503)",
            "counter",
            requests_rejected_total,
        ),
        (
            "http_requests_total",
            "Total HTTP requests handled",
            "counter",
            requests_total,
        ),
        ("http_4xx_total", "Total HTTP 4xx responses", "counter", http_4xx_total),
        ("http_5xx_total", "Total HTTP 5xx responses", "counter", http_5xx_total),
        (
            "http_latency_seconds_total",
            "Total HTTP request latency in seconds",
            "counter",
            round(latency_total_seconds, 4),
        ),
        (
            "http_latency_seconds_count",
            "Total HTTP request latency observations",
            "counter",
            requests_total,
        ),
    ]
    country = (
        (snapshot.country or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    lines: list[str] = []
    for name, help_text, kind, value in values:
        label = f'{{country="{country}"}}' if name == "exit_country_info" else ""
        lines.extend(
            (
                f"# HELP torproxy_{name} {help_text}",
                f"# TYPE torproxy_{name} {kind}",
                f"torproxy_{name}{label} {value}",
                "",
            )
        )
    return "\n".join(lines)
