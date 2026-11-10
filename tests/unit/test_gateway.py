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
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="tor")
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
        assert any("nat -A OUTPUT -m owner --uid-owner tor -j RETURN" in c for c in commands)

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

    def test_dedicated_tor_user_bypass_no_torproxy_bypass(self):
        # ISSUE-03: only the dedicated unprivileged tor user may bypass NAT /
        # reach the WAN; API and Privoxy (torproxy user) get no bypass.
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="tor")
        commands = [" ".join(cmd) for cmd in rules]

        assert any("nat -A OUTPUT -m owner --uid-owner tor -j RETURN" in c for c in commands)
        assert any("-A OUTPUT -m owner --uid-owner tor -j ACCEPT" in c for c in commands)
        assert not any("--uid-owner torproxy" in c for c in commands)

    def test_ip6_tor_exception_but_policy_stays_drop(self):
        # ISSUE-03: Tor itself may bootstrap over IPv6, everyone else stays blocked.
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="tor")
        commands = [" ".join(cmd) for cmd in rules]
        assert "ip6tables -P OUTPUT DROP" in commands
        assert any("ip6tables -A OUTPUT -m owner --uid-owner tor -j ACCEPT" in c for c in commands)

    def test_no_unscoped_established_accept(self):
        # ISSUE-02: an unrestricted ESTABLISHED,RELATED ACCEPT in filter OUTPUT
        # lets pre-existing clearnet connections survive a Tor outage and
        # breaks the documented fail-closed guarantee. No such rule may exist.
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="tor")
        for cmd in rules:
            joined = " ".join(cmd)
            assert "ESTABLISHED" not in joined, f"unscoped ESTABLISHED accept: {joined}"
            assert "RELATED" not in joined, f"unscoped RELATED accept: {joined}"

    def test_kill_switch_reject_is_last_output_rule(self):
        # Legitimate flows stay allowed (loopback, TransPort/DNSPort targets,
        # Tor UID owner) and everything else is rejected last.
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="tor")
        output_filter = [
            " ".join(cmd)
            for cmd in rules
            if cmd[0] == "iptables" and len(cmd) > 2 and cmd[1] == "-A" and cmd[2] == "OUTPUT"
        ]
        assert output_filter, "expected filter OUTPUT rules"
        assert "REJECT" in output_filter[-1]
        assert any("-o lo" in c and "ACCEPT" in c for c in output_filter)
        assert any("--uid-owner tor" in c and "ACCEPT" in c for c in output_filter)
        assert any("127.0.0.1" in c and "--dport 9040" in c for c in output_filter)
        assert any("127.0.0.1" in c and "--dport 9053" in c for c in output_filter)

    def test_custom_ports_in_rules(self):
        rules = generate_iptables_rules(trans_port=9045, dns_port=9055, tor_user="customuser")
        commands = [" ".join(cmd) for cmd in rules]

        assert any("--to-ports 9045" in c for c in commands)
        assert any("--to-ports 9055" in c for c in commands)
        assert any("--uid-owner customuser" in c for c in commands)

    def test_mcp_port_exempt_in_gateway_rules(self):
        rules = generate_iptables_rules(trans_port=9040, dns_port=9053, tor_user="tor")
        commands = [" ".join(cmd) for cmd in rules]
        assert any("nat -A PREROUTING -p tcp --dport 2501 -j RETURN" in c for c in commands)
        assert any("-A INPUT -p tcp --dport 2501 -j ACCEPT" in c for c in commands)


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

    def test_gateway_second_run_is_noop(self):
        # ISSUE-05: applying the rules twice (e.g. container restart with
        # rules already present) must not fail or duplicate rules.
        from unittest.mock import MagicMock

        settings = Settings(gateway_mode=True, trans_port=9040, dns_port=9053)

        def run_first(cmd, **kwargs):
            # -C probes report "not exists", -A/-P apply successfully.
            return MagicMock(returncode=1 if "-C" in cmd else 0)

        with (
            patch("torproxy.runtime.gateway.check_net_admin_capability", return_value=True),
            patch("subprocess.run", side_effect=run_first) as mock_first,
        ):
            setup_gateway(settings)
        appended = [c.args[0] for c in mock_first.call_args_list if "-A" in c.args[0]]
        assert appended, "expected appended rules on first run"

        def run_second(cmd, **kwargs):
            # -C probes report "already exists".
            return MagicMock(returncode=0)

        with (
            patch("torproxy.runtime.gateway.check_net_admin_capability", return_value=True),
            patch("subprocess.run", side_effect=run_second) as mock_second,
        ):
            setup_gateway(settings)
        reapplied = [c.args[0] for c in mock_second.call_args_list if "-A" in c.args[0]]
        assert reapplied == [], f"second run must be a no-op, reapplied: {reapplied}"
