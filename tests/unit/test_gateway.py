from unittest.mock import patch

import pytest

from torproxy.configuration import Settings
from torproxy.runtime.gateway import (
    generate_iptables_rules,
    setup_gateway,
)


@pytest.mark.unit
class TestGatewayRules:
    def test_generate_rules_contains_trans_and_dns_ports(self):
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="torproxy")
        commands = [" ".join(cmd) for cmd in rules]

        # Verify DNS redirect
        assert any(
            "nat -A OUTPUT -p udp --dport 53 -j REDIRECT --to-ports 9053" in c for c in commands
        )
        assert any(
            "nat -A OUTPUT -p tcp --dport 53 -j REDIRECT --to-ports 9053" in c for c in commands
        )

        # Verify TCP TransPort redirect
        assert any("nat -A OUTPUT -p tcp -j REDIRECT --to-ports 9040" in c for c in commands)

        # Verify Tor user bypass
        assert any("nat -A OUTPUT -m owner --uid-owner torproxy -j RETURN" in c for c in commands)

        # Verify exempt ports in OUTPUT are strictly scoped to loopback 127.0.0.1
        assert any(
            "nat -A OUTPUT -d 127.0.0.1 -p tcp --dport 8080 -j RETURN" in c for c in commands
        )
        assert not any(
            c == "iptables -t nat -A OUTPUT -p tcp --dport 8080 -j RETURN" for c in commands
        )

        # Verify Kill Switch
        assert any("OUTPUT -j REJECT --reject-with icmp-port-unreachable" in c for c in commands)

        # Verify IPv6 drop
        assert any("ip6tables -P OUTPUT DROP" in c for c in commands)

    def test_custom_ports_in_rules(self):
        rules = generate_iptables_rules(trans_port=9045, dns_port=9055, tor_user="customuser")
        commands = [" ".join(cmd) for cmd in rules]

        assert any("--to-ports 9045" in c for c in commands)
        assert any("--to-ports 9055" in c for c in commands)
        assert any("--uid-owner customuser" in c for c in commands)


@pytest.mark.unit
class TestGatewayLifecycle:
    def test_gateway_noop_when_disabled(self):
        settings = Settings(gateway_mode=False)
        with patch("subprocess.run") as mock_run:
            setup_gateway(settings)
            mock_run.assert_not_called()

    def test_gateway_raises_when_cap_net_admin_missing(self):
        settings = Settings(gateway_mode=True)
        with patch("torproxy.runtime.gateway.check_net_admin_capability", return_value=False):
            with pytest.raises(RuntimeError, match="CAP_NET_ADMIN capability is missing"):
                setup_gateway(settings)

    def test_gateway_applies_rules_when_enabled(self):
        settings = Settings(gateway_mode=True, trans_port=9040, dns_port=9053)
        with (
            patch("torproxy.runtime.gateway.check_net_admin_capability", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            setup_gateway(settings)
            assert mock_run.call_count > 10
