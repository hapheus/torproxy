"""The only composition root that selects concrete I/O adapters."""

from torproxy.adapters.clock import SystemClock
from torproxy.adapters.geoip_status import FileGeoIpStatus
from torproxy.adapters.probes import SocksReadinessProbe, TorEgressProbe
from torproxy.adapters.tor_control import TorControlClient
from torproxy.configuration import Settings
from torproxy.ports import Clock, ControlPort, EgressProbe, GeoIpStatus, SocksProbe
from torproxy.service import ProxyService
from torproxy.state import RuntimeState
from torproxy.web.router import Router
from torproxy.web.server import ProxyHTTPServer


def create_services(
    settings: Settings,
    *,
    control: ControlPort | None = None,
    egress: EgressProbe | None = None,
    socks: SocksProbe | None = None,
    clock: Clock | None = None,
    geoip: GeoIpStatus | None = None,
) -> ProxyService:
    return ProxyService(
        settings,
        control or TorControlClient(settings.control_port, settings.cookie_path),
        egress or TorEgressProbe(settings.proxy_port),
        socks or SocksReadinessProbe(settings.socks_port),
        RuntimeState(settings.country, settings.strict_nodes, clock or SystemClock()),
        geoip if geoip is not None else FileGeoIpStatus(settings.geoip_dir),
    )


def create_server(settings: Settings, address: tuple[str, int] | None = None) -> ProxyHTTPServer:
    return ProxyHTTPServer(
        address or (settings.api_listen_address, settings.api_port),
        Router(create_services(settings)),
        settings,
    )
