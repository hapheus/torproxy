"""Small structural interfaces; application code does not import adapters."""

from typing import Protocol

from torproxy.models import CommandResult


class ControlPort(Protocol):
    def send(self, command: str) -> CommandResult:
        """Send a command string to the control interface."""


class EgressProbe(Protocol):
    def resolve(self) -> CommandResult:
        """Resolve current egress IP via Tor check service."""


class SocksProbe(Protocol):
    def ready(self) -> bool:
        """Probe if SOCKS listener accepts connections."""


class Clock(Protocol):
    def monotonic(self) -> float:
        """Return monotonic time in seconds."""

    def time(self) -> float:
        """Return wall-clock epoch time in seconds."""
