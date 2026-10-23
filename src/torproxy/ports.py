"""Small structural interfaces; application code does not import adapters."""

from typing import Protocol

from torproxy.models import CommandResult


class ControlPort(Protocol):
    def send(self, command: str) -> CommandResult: ...


class EgressProbe(Protocol):
    def resolve(self) -> CommandResult: ...


class SocksProbe(Protocol):
    def ready(self) -> bool: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def time(self) -> float: ...
