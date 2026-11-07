"""ISSUE-18c (#108): source-IP access control for the SOCKS port.

Tor's SocksPort is unauthenticated by design (client-supplied
username/password is only stream isolation, never a credential
check), so the implementable control is Tor's SocksPolicy:
accept listed CIDRs, reject everything else. Loopback must
always stay accepted for the internal probes and Privoxy.
"""

import pytest

from torproxy.configuration import Settings, render_torrc


@pytest.mark.unit
class TestSocksPolicySettings:
    def test_default_no_policy(self):
        assert Settings().socks_allowed_cidrs == ""

    def test_cidrs_from_env(self):
        settings = Settings.from_mapping(
            {"TORPROXY_SOCKS_ALLOWED_CIDRS": "172.16.0.0/12,10.0.0.0/8"}
        )
        assert settings.socks_allowed_cidrs == "172.16.0.0/12,10.0.0.0/8"

    def test_invalid_cidr_rejected(self):
        with pytest.raises(ValueError, match="TORPROXY_SOCKS_ALLOWED_CIDRS"):
            Settings(socks_allowed_cidrs="not-a-cidr")

    def test_ipv6_cidr_accepted(self):
        settings = Settings(socks_allowed_cidrs="fd00::/8")
        assert settings.socks_allowed_cidrs == "fd00::/8"


@pytest.mark.unit
class TestSocksPolicyRender:
    def test_no_policy_line_by_default(self):
        torrc = render_torrc(Settings(), "SocksPort 0.0.0.0:9050\n")
        assert "SocksPolicy" not in torrc

    def test_policy_accepts_listed_and_loopback_rejects_rest(self):
        settings = Settings(socks_allowed_cidrs="172.16.0.0/12")
        torrc = render_torrc(settings, "SocksPort 0.0.0.0:9050\n")
        expected = "SocksPolicy accept 127.0.0.0/8, accept ::1/128, accept 172.16.0.0/12, reject *"
        assert expected in torrc
