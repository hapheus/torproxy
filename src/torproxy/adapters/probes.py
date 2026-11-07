"""Bounded proxy probes with explicit upstream and transport dependencies."""

import ipaddress
import json
import socket
import threading
import time
import urllib.error
import urllib.request

from torproxy.models import CommandResult


def _classify_transport_error(exc: BaseException) -> str:
    """Map a transport failure to a stable, leak-free reason (ISSUE-12).

    Distinct causes must not collapse into one string, otherwise a dead
    local HTTP proxy (Privoxy, 8118) looks identical to a dead check
    service although SOCKS5/Tor may be healthy:

    - connection refused to the local proxy -> local HTTP proxy
    - HTTP error answered by the local proxy (e.g. 5xx from Privoxy
      because the Tor circuit is not ready) -> Tor upstream failure
    - anything else (timeout, DNS, remote reset) -> check service

    Raw socket text is never included (cf. ISSUE-08).
    """
    # HTTPError is a subclass of URLError and must be checked first:
    # it proves some HTTP server answered. A 5xx from the local
    # proxy (Privoxy) means the Tor upstream failed; a 4xx proves
    # the check service itself answered through a healthy proxy
    # (e.g. 429 rate-limit) and must not be blamed on Tor.
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code >= 500:
            return f"Tor upstream unavailable via local HTTP proxy (HTTP {exc.code})"
        return f"egress check service returned HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ConnectionRefusedError) or isinstance(exc, ConnectionRefusedError):
        return "local HTTP proxy unreachable"
    if isinstance(reason, str) and "connection refused" in reason.lower():
        return "local HTTP proxy unreachable"
    return "egress check service unreachable"


class TorEgressProbe:
    """Egress probe with retry, backoff and circuit breaker (ISSUE-06).

    Previously a single 3 s attempt against check.torproject.org was the
    only signal: any outage/rate-limit made /status, /ip and /health report
    "connecting" although Tor was healthy. Now the probe retries with
    exponential backoff, trips a short circuit breaker after repeated
    failures and returns distinct, operator-safe reasons so callers can
    report "degraded (check service unreachable)" instead of "connecting".

    ISSUE-12 (#76) further distinguishes a dead local HTTP proxy and a
    Tor upstream failure (proxy 5xx) from an unreachable check service;
    see `_classify_transport_error`.
    """

    PRIMARY_URL = "https://check.torproject.org/api/ip"

    def __init__(
        self,
        proxy_port: int,
        timeout: float = 3,
        max_retries: int = 2,
        circuit_threshold: int = 5,
        circuit_cooldown: float = 30.0,
    ) -> None:
        self.proxy_port = proxy_port
        self.timeout = timeout
        self.max_retries = max_retries
        self.circuit_threshold = circuit_threshold
        self.circuit_cooldown = circuit_cooldown
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0
        self._last_error: str | None = None

    def _circuit_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._open_until

    def _note_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.circuit_threshold:
                self._open_until = time.monotonic() + self.circuit_cooldown

    def _note_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0

    def _attempt(self) -> tuple[str | None, str | None, bool]:
        """Single attempt. Returns (ip, error, check_reachable)."""
        proxy = f"http://127.0.0.1:{self.proxy_port}"
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        try:
            response = opener.open(self.PRIMARY_URL, timeout=self.timeout)
            try:
                raw = response.read(16385)
            finally:
                response.close()
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            return None, _classify_transport_error(exc), False
        if len(raw) > 16384:
            return None, "Tor check response too large", True
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None, "Tor egress verification failed", True
        if not isinstance(data, dict):
            return None, "Invalid Tor check response", True
        confirmation = data.get("IsTor", data.get("is_tor"))
        if confirmation is False:
            return (
                None,
                "Tor check service reported traffic NOT routed through Tor (IsTor=false)",
                True,
            )
        if confirmation is not True:
            return None, "Tor check service response missing IsTor confirmation", True
        ip = data.get("IP") or data.get("ip")
        if not ip:
            return None, "No IP key in response", True
        try:
            return str(ipaddress.ip_address(ip)), None, True
        except ValueError:
            return None, "Tor egress verification failed", True

    def resolve(self) -> CommandResult:
        if self._circuit_open():
            # Keep the original cause (ISSUE-12): an open breaker
            # after repeated local-proxy refusals must not revert
            # to blaming the check service.
            cause = self._last_error or "egress check service unreachable"
            return None, f"{cause} (circuit breaker open)"
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            ip, error, reachable = self._attempt()
            if ip:
                self._note_success()
                self._last_error = None
                return ip, None
            last_error = error
            self._last_error = error
            if reachable:
                # The service answered: no retry helps (IsTor=false etc.).
                self._note_failure()
                return None, error
            if attempt < self.max_retries:
                time.sleep(min(0.05 * (2**attempt), 0.2))
        self._note_failure()
        return None, last_error or "Tor egress verification failed"


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
