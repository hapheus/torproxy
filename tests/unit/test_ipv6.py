"""ISSUE-18b (#107): IPv6 listen addresses for the API.

Hermetic tests: settings validation plus a real loopback bind on
::1 (skipped gracefully on hosts without IPv6).
"""

import socket

import pytest

from torproxy.bootstrap import create_server
from torproxy.configuration import Settings


@pytest.mark.unit
class TestIPv6Settings:
    def test_ipv6_loopback_api_address_accepted(self):
        settings = Settings(api_listen_address="::1")
        assert settings.api_listen_address == "::1"

    def test_ipv6_any_api_address_accepted(self):
        settings = Settings(api_listen_address="::")
        assert settings.api_listen_address == "::"

    def test_ipv4_default_unchanged(self):
        assert Settings().api_listen_address == "0.0.0.0"

    def test_invalid_address_still_rejected(self):
        with pytest.raises(ValueError, match="TORPROXY_API_LISTEN_ADDRESS"):
            Settings(api_listen_address="not-an-address")

    def test_listen_address_ipv6_accepted(self):
        # Privoxy listen address validation shares the same rule.
        settings = Settings(listen_address="::1")
        assert settings.listen_address == "::1"


@pytest.mark.unit
class TestIPv6ServerBind:
    def test_server_binds_ipv6_loopback(self):
        try:
            probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            probe.bind(("::1", 0))
            probe.close()
        except OSError:
            pytest.skip("IPv6 loopback unavailable on this host")

        settings = Settings(api_listen_address="::1")
        server = create_server(settings, ("::1", 0))
        try:
            assert server.address_family == socket.AF_INET6
            host, port = server.server_address[0], server.server_address[1]
            assert host == "::1"
            assert port > 0
        finally:
            server.server_close()
