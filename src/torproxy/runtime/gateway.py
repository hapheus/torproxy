"""Transparent Tor Gateway configuration and netfilter rule application."""

import os
import shutil
import subprocess

from torproxy.configuration import Settings


def generate_iptables_rules(
    trans_port: int = 9040,
    dns_port: int = 9053,
    tor_user: str = "torproxy",
    exempt_ports: tuple[int, ...] = (8118, 8080, 9050, 9051),
) -> list[list[str]]:
    """Generate iptables and ip6tables commands for transparent Tor routing and kill switch."""
    rules: list[list[str]] = []

    # 1. NAT Table: Tor process and local daemon ports bypass redirection
    rules.append(
        [
            "iptables",
            "-t",
            "nat",
            "-A",
            "OUTPUT",
            "-m",
            "owner",
            "--uid-owner",
            tor_user,
            "-j",
            "RETURN",
        ]
    )
    for p in exempt_ports:
        rules.append(
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "OUTPUT",
                "-p",
                "tcp",
                "--dport",
                str(p),
                "-j",
                "RETURN",
            ]
        )
        rules.append(
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "PREROUTING",
                "-p",
                "tcp",
                "--dport",
                str(p),
                "-j",
                "RETURN",
            ]
        )

    # DNS redirection to Tor DNSPort (both locally generated and routed)
    rules.extend(
        [
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "OUTPUT",
                "-p",
                "udp",
                "--dport",
                "53",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(dns_port),
            ],
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "OUTPUT",
                "-p",
                "tcp",
                "--dport",
                "53",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(dns_port),
            ],
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "PREROUTING",
                "-p",
                "udp",
                "--dport",
                "53",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(dns_port),
            ],
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "PREROUTING",
                "-p",
                "tcp",
                "--dport",
                "53",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(dns_port),
            ],
            # Loopback bypass for local services
            ["iptables", "-t", "nat", "-A", "OUTPUT", "-o", "lo", "-j", "RETURN"],
            # TCP redirection to Tor TransPort
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "OUTPUT",
                "-p",
                "tcp",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(trans_port),
            ],
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "PREROUTING",
                "-p",
                "tcp",
                "-j",
                "REDIRECT",
                "--to-ports",
                str(trans_port),
            ],
        ]
    )

    # 2. Filter Table: Fail-Closed Kill Switch & Non-Tor UDP drop
    rules.extend(
        [
            [
                "iptables",
                "-A",
                "OUTPUT",
                "-m",
                "conntrack",
                "--ctstate",
                "ESTABLISHED,RELATED",
                "-j",
                "ACCEPT",
            ],
            ["iptables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"],
            # Accept redirected traffic arriving at loopback
            [
                "iptables",
                "-A",
                "OUTPUT",
                "-d",
                "127.0.0.1",
                "-p",
                "udp",
                "--dport",
                str(dns_port),
                "-j",
                "ACCEPT",
            ],
            [
                "iptables",
                "-A",
                "OUTPUT",
                "-d",
                "127.0.0.1",
                "-p",
                "tcp",
                "--dport",
                str(trans_port),
                "-j",
                "ACCEPT",
            ],
            # Tor daemon itself can output to WAN
            ["iptables", "-A", "OUTPUT", "-m", "owner", "--uid-owner", tor_user, "-j", "ACCEPT"],
            # Kill switch: reject everything else (unsupported UDP, direct TCP leaks)
            ["iptables", "-A", "OUTPUT", "-j", "REJECT", "--reject-with", "icmp-port-unreachable"],
            ["iptables", "-A", "FORWARD", "-j", "DROP"],
        ]
    )

    # Allow incoming traffic to exposed daemon ports (API, Privoxy, SOCKS)
    for p in exempt_ports:
        rules.append(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(p), "-j", "ACCEPT"])

    # 3. IPv6 Leak Prevention: Drop all non-loopback IPv6
    rules.extend(
        [
            ["ip6tables", "-P", "INPUT", "DROP"],
            ["ip6tables", "-P", "FORWARD", "DROP"],
            ["ip6tables", "-P", "OUTPUT", "DROP"],
            ["ip6tables", "-A", "INPUT", "-i", "lo", "-j", "ACCEPT"],
            ["ip6tables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"],
        ]
    )

    return rules


def check_net_admin_capability() -> bool:
    """Check if iptables can be executed in this container's network namespace."""
    iptables_bin = shutil.which("iptables")
    if not iptables_bin:
        return False
    res = subprocess.run(
        [iptables_bin, "-L", "-n"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def setup_gateway(settings: Settings) -> None:
    """Configure iptables and ip6tables rules if gateway mode is active."""
    if not settings.gateway_mode:
        return

    if not check_net_admin_capability():
        raise RuntimeError(
            "TORPROXY_GATEWAY_MODE is enabled, but CAP_NET_ADMIN capability is missing. "
            "Please add 'cap_add: [NET_ADMIN]' to your Docker compose configuration."
        )

    exempt = (settings.proxy_port, settings.api_port, settings.socks_port, settings.control_port)
    rules = generate_iptables_rules(
        trans_port=settings.trans_port,
        dns_port=settings.dns_port,
        tor_user="torproxy",
        exempt_ports=exempt,
    )

    for cmd in rules:
        subprocess.run(cmd, check=True)


def main() -> None:
    settings = Settings.from_mapping(os.environ)
    if settings.gateway_mode:
        setup_gateway(settings)


if __name__ == "__main__":
    main()
