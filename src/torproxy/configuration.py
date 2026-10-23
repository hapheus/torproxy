"""Configuration parsing without environment or runtime side effects."""

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass


def validate_country_input(value: object) -> tuple[str | None, str | None, str | None]:
    if value is None:
        return None, None, None
    if isinstance(value, str):
        raw = value.strip()
        if raw.lower() in ("", "any", "all", "none", "*"):
            return "", None, None
        parts = [part.strip() for part in raw.split(",")]
    elif isinstance(value, list) and all(isinstance(part, str) for part in value):
        parts = [part.strip() for part in value]
    else:
        return None, None, "Invalid country parameter format. Expected string or array of strings."
    for part in parts:
        if not re.fullmatch(r"[a-zA-Z]{2}", part):
            return None, None, f"Invalid ISO country code: '{part}'. Must be 2-letter alpha code."
    return (
        ",".join(f"{{{p.lower()}}}" for p in parts),
        ",".join(p.upper() for p in parts) or None,
        None,
    )


def validate_strict_nodes_input(value: object) -> tuple[bool | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, bool):
        return value, None
    if isinstance(value, int):
        return (
            (bool(value), None)
            if value in (0, 1)
            else (None, "strict_nodes integer must be 0 or 1")
        )
    if isinstance(value, str):
        if value.strip().lower() in ("1", "true", "yes"):
            return True, None
        if value.strip().lower() in ("0", "false", "no"):
            return False, None
        return None, f"Invalid boolean value for strict_nodes: '{value}'"
    return None, "strict_nodes must be boolean, integer (0/1), or boolean string"


@dataclass(frozen=True)
class Settings:
    listen_address: str = "0.0.0.0"
    proxy_port: int = 8118
    api_port: int = 8080
    socks_port: int = 9050
    control_port: int = 9051
    cookie_path: str = "/var/lib/tor/control_auth_cookie"
    country: str | None = None
    strict_nodes: bool = False
    exit_nodes: str = ""
    cache_ttl: float = 30
    request_timeout: float = 3
    max_body_bytes: int = 16384
    max_workers: int = 32

    def __post_init__(self) -> None:
        try:
            ipaddress.IPv4Address(self.listen_address)
        except ipaddress.AddressValueError:
            raise ValueError("TORPROXY_LISTEN_ADDRESS must be a valid IPv4 address") from None
        for name, port in (
            ("TORPROXY_LISTEN_PORT", self.proxy_port),
            ("TORPROXY_API_PORT", self.api_port),
            ("TORPROXY_SOCKS_PORT", self.socks_port),
            ("TOR_CONTROL_PORT", self.control_port),
        ):
            if not 1 <= port <= 65535:
                raise ValueError(f"{name} must be between 1 and 65535")
        if len({self.proxy_port, self.api_port, self.socks_port, self.control_port}) != 4:
            raise ValueError(
                "Configuration error: TORPROXY_LISTEN_PORT, TORPROXY_API_PORT, TORPROXY_SOCKS_PORT "
                "and TOR_CONTROL_PORT must all be distinct ports"
            )
        nodes, country, error = validate_country_input(self.country)
        if error or country != self.country:
            raise ValueError(error or "Country must be normalized")
        if self.request_timeout <= 0 or self.cache_ttl < 0:
            raise ValueError("Timeout must be positive and cache TTL non-negative")
        if self.max_body_bytes < 1 or self.max_workers < 1:
            raise ValueError("Request limits must be positive")
        if self.exit_nodes and not re.fullmatch(r"[a-zA-Z0-9{},.$~= /:-]+", self.exit_nodes):
            raise ValueError("Invalid TORPROXY_EXIT_NODES")

    @classmethod
    def from_mapping(cls, env: Mapping[str, str]) -> "Settings":
        nodes, country, error = validate_country_input(
            env.get("TORPROXY_COUNTRY") or env.get("TORPROXY_EXIT_COUNTRY") or None
        )
        if error:
            raise ValueError(f"TORPROXY_COUNTRY: {error}")
        strict, error = validate_strict_nodes_input(env.get("TORPROXY_STRICT_NODES") or None)
        if error:
            raise ValueError(f"TORPROXY_STRICT_NODES: {error}")

        def port(name: str, default: int) -> int:
            try:
                return int(env.get(name, str(default)))
            except ValueError:
                raise ValueError(f"{name} must be an integer between 1 and 65535") from None

        return cls(
            listen_address=env.get("TORPROXY_LISTEN_ADDRESS", "0.0.0.0"),
            proxy_port=port("TORPROXY_LISTEN_PORT", 8118),
            api_port=port("TORPROXY_API_PORT", 8080),
            socks_port=port("TORPROXY_SOCKS_PORT", 9050),
            control_port=port("TOR_CONTROL_PORT", 9051),
            cookie_path=env.get("TOR_CONTROL_COOKIE_FILE", "/var/lib/tor/control_auth_cookie"),
            country=country,
            exit_nodes=nodes or env.get("TORPROXY_EXIT_NODES", ""),
            strict_nodes=strict
            if strict is not None
            else bool(nodes or env.get("TORPROXY_EXIT_NODES")),
        )


def render_torrc(settings: Settings, template: str) -> str:
    result = template.replace("__TORPROXY_SOCKS_PORT__", str(settings.socks_port))
    result = result.replace(
        "ControlPort 127.0.0.1:9051", f"ControlPort 127.0.0.1:{settings.control_port}"
    )
    if settings.exit_nodes:
        result += f"\nExitNodes {settings.exit_nodes}\n"
    if settings.exit_nodes or settings.strict_nodes:
        result += f"StrictNodes {int(settings.strict_nodes)}\n"
    return result
