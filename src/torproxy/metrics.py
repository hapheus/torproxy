"""Prometheus serialization without network access."""

from collections.abc import Mapping

from torproxy.state import Snapshot


def render_metrics(snapshot: Snapshot, bootstrap: Mapping | None, socks: bool) -> str:
    values = (
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
            "strict_nodes",
            "Tor StrictNodes setting (1=strict, 0=flexible)",
            "gauge",
            int(snapshot.strict_nodes),
        ),
        ("exit_country_info", "Configured exit country code", "gauge", 1),
    )
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
