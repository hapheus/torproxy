"""Transparent Tor Gateway configuration and netfilter rule application."""

import os
import shutil
import subprocess

from torproxy.configuration import Settings


def generate_iptables_rules(
    trans_port: int = 9040,
    dns_port: int = 9053,
    tor_user: str = "tor",
    exempt_ports: tuple[int, ...] = (8118, 8080, 9050, 9051, 2501),
) -> list[list[str]]:
    """Generate iptables and ip6tables commands for transparent Tor routing and kill switch.

    ISSUE-03: the WAN bypass (NAT RETURN + filter ACCEPT) applies to the
    dedicated unprivileged ``tor`` user only. The API, Privoxy, and attached
    app containers run as other users and get no bypass — netfilter least
    privilege (see docker/start.sh privilege dropping).
    """
    owner_match = ["--uid-owner", tor_user]
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
            *owner_match,
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
                "-d",
                "127.0.0.1",
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
    # NOTE (ISSUE-02): there is intentionally no ESTABLISHED,RELATED accept.
    # An unrestricted conntrack accept would let pre-existing clearnet
    # connections (established before Tor bootstrapped or after a Tor outage)
    # survive and silently bypass fail-closed. Legitimate flows are covered
    # by the loopback, TransPort/DNSPort, and Tor-UID-owner rules below.
    rules.extend(
        [
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
            # Tor daemon itself can output to WAN (dedicated tor user only, ISSUE-03)
            ["iptables", "-A", "OUTPUT", "-m", "owner", *owner_match, "-j", "ACCEPT"],
            # Kill switch: reject everything else (unsupported UDP, direct TCP leaks)
            ["iptables", "-A", "OUTPUT", "-j", "REJECT", "--reject-with", "icmp-port-unreachable"],
            ["iptables", "-A", "FORWARD", "-j", "DROP"],
        ]
    )

    # Allow incoming traffic to exposed daemon ports (API, Privoxy, SOCKS)
    for p in exempt_ports:
        rules.append(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(p), "-j", "ACCEPT"])

    # 3. IPv6 Leak Prevention: Drop all non-loopback IPv6 except Tor itself,
    # so Tor can still bootstrap in IPv6-only/preferred environments while
    # every other process stays blocked (ISSUE-03).
    rules.extend(
        [
            ["ip6tables", "-P", "INPUT", "DROP"],
            ["ip6tables", "-P", "FORWARD", "DROP"],
            ["ip6tables", "-P", "OUTPUT", "DROP"],
            ["ip6tables", "-A", "INPUT", "-i", "lo", "-j", "ACCEPT"],
            ["ip6tables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"],
            ["ip6tables", "-A", "OUTPUT", "-m", "owner", *owner_match, "-j", "ACCEPT"],
        ]
    )

    return rules


def iptables_backend() -> str | None:
    """Return the active iptables backend ("nft"/"legacy") or None (ISSUE-13)."""
    if shutil.which("xtables-nft-multi"):
        return "nft"
    if shutil.which("xtables-legacy-multi"):
        return "legacy"
    return None


def check_net_admin_capability() -> bool:
    """Check if iptables can be executed in this container's network namespace.

    ISSUE-13: Alpine may ship the nft backend (xtables-nft-multi) or the
    legacy backend (xtables-legacy-multi). A package rename or a backend
    switch must not silently break gateway mode, so the check is extended
    to require a usable backend binary in addition to ``iptables``.
    """
    iptables_bin = shutil.which("iptables")
    if not iptables_bin:
        return False
    res = subprocess.run(
        [iptables_bin, "-L", "-n"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if res.returncode != 0:
        return False
    # Backend binaries (either is acceptable; both may exist).
    if shutil.which("xtables-nft-multi") or shutil.which("xtables-legacy-multi"):
        return True
    # If no multi-binary is on PATH, `iptables` itself is still usable
    # (legacy single-binary builds); the iptables probe above is decisive.
    return True


def _rule_exists(cmd: list[str]) -> bool:
    """Probe whether an append rule is already present (ISSUE-05 idempotency)."""
    if "-A" not in cmd:
        return False
    probe = list(cmd)
    probe[probe.index("-A")] = "-C"
    res = subprocess.run(
        probe,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def setup_gateway(settings: Settings) -> None:
    """Configure iptables and ip6tables rules if gateway mode is active.

    Idempotent (ISSUE-05): a second run — e.g. a container restart with
    rules already present — probes each append rule with ``-C`` and skips
    existing ones instead of failing on duplicates.
    """
    if not settings.gateway_mode:
        return

    if not check_net_admin_capability():
        raise RuntimeError(
            "TORPROXY_GATEWAY_MODE is enabled, but CAP_NET_ADMIN capability is missing. "
            "Please add 'cap_add: [NET_ADMIN]' to your Docker compose configuration."
        )

    exempt: tuple[int, ...] = (
        settings.proxy_port,
        settings.api_port,
        settings.socks_port,
        settings.control_port,
        *((settings.mcp_port,) if settings.mcp_enabled else ()),
    )
    rules = generate_iptables_rules(
        trans_port=settings.trans_port,
        dns_port=settings.dns_port,
        tor_user="tor",
        exempt_ports=exempt,
    )

    for cmd in rules:
        if _rule_exists(cmd):
            continue
        subprocess.run(cmd, check=True)


def main() -> None:
    settings = Settings.from_mapping(os.environ)
    if settings.gateway_mode:
        setup_gateway(settings)


if __name__ == "__main__":
    main()
