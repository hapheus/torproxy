"""Bounded proxy probes with explicit upstream and transport dependencies."""

import ipaddress
import json
import socket
import urllib.request

from torproxy.models import CommandResult


class TorEgressProbe:
    def __init__(self, proxy_port: int, timeout: float = 3) -> None:
        self.proxy_port = proxy_port
        self.timeout = timeout

    def resolve(self) -> CommandResult:
        proxy = f"http://127.0.0.1:{self.proxy_port}"
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        try:
            response = opener.open("https://check.torproject.org/api/ip", timeout=self.timeout)
            try:
                raw = response.read(16385)
            finally:
                response.close()
            if len(raw) > 16384:
                return None, "Tor check response too large"
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None, "Invalid Tor check response"
            confirmation = data.get("IsTor", data.get("is_tor"))
            if confirmation is False:
                return (
                    None,
                    "Tor check service reported traffic NOT routed through Tor (IsTor=false)",
                )
            if confirmation is not True:
                return None, "Tor check service response missing IsTor confirmation"
            ip = data.get("IP") or data.get("ip")
            if not ip:
                return None, "No IP key in response"
            return str(ipaddress.ip_address(ip)), None
        except (OSError, ValueError, TypeError):
            return None, "Tor egress verification failed"


class SocksReadinessProbe:
    def __init__(self, port: int, timeout: float = 1.5) -> None:
        self.port = port
        self.timeout = timeout

    def ready(self) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(("127.0.0.1", self.port))
                sock.sendall(b"\x05\x01\x00")
                reply = b""
                while len(reply) < 2:
                    chunk = sock.recv(2 - len(reply))
                    if not chunk:
                        return False
                    reply += chunk
                return reply == b"\x05\x00"
        except OSError:
            return False
