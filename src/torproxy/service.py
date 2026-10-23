"""Application operations; mutations are serialized and do not depend on HTTP."""

import re
from typing import Any

from torproxy.configuration import Settings, validate_country_input, validate_strict_nodes_input
from torproxy.models import BootstrapResult, CommandResult
from torproxy.ports import ControlPort, EgressProbe, SocksProbe
from torproxy.state import RuntimeState


class ControlFailure(Exception):
    """A control operation failed; the message is safe for operator responses."""


class InvalidInput(ValueError):
    """An operation was rejected before any external mutation."""


class ProxyService:
    def __init__(
        self,
        settings: Settings,
        control: ControlPort,
        egress: EgressProbe,
        socks: SocksProbe,
        state: RuntimeState,
    ) -> None:
        self.settings = settings
        self.control = control
        self.egress = egress
        self.socks = socks
        self.state = state

    def send_tor_command(self, command: str) -> CommandResult:
        return self.control.send(command)

    def get_current_ip(self) -> CommandResult:
        with self.state.lock:
            generation = self.state.generation
            age = self.state.clock.monotonic() - self.state.cached_at
            if self.state.cached_ip and age < self.settings.cache_ttl:
                return self.state.cached_ip, None
        ip, error = self.egress.resolve()
        with self.state.lock:
            if generation != self.state.generation:
                return None, "Proxy state changed during egress verification"
            if ip:
                self.state.cached_ip = ip
                self.state.cached_at = self.state.clock.monotonic()
        return ip, error

    def get_tor_bootstrap_status(self) -> BootstrapResult:
        response, error = self.send_tor_command("GETINFO status/bootstrap-phase")
        if error:
            return None, f"Failed to query Tor control: {error}"
        match = re.search(r'PROGRESS=(\d+)\s+TAG=(\S+)\s+SUMMARY="([^"]+)"', response or "")
        if not match or not 0 <= int(match[1]) <= 100:
            return None, "Failed to parse bootstrap status"
        return {
            "progress": int(match[1]),
            "tag": match[2],
            "summary": match[3],
            "bootstrapped": int(match[1]) == 100,
        }, None

    def check_socks5_ready(self) -> bool:
        return self.socks.ready()

    def _command(self, command: str, message: str) -> None:
        _, error = self.send_tor_command(command)
        if error:
            raise ControlFailure(f"{message}: {error}")

    def mutate(self, action: str, country: object = None, strict: object = None) -> dict:
        nodes, normalized, error = validate_country_input(country)
        if error:
            raise InvalidInput(error)
        strict_value, error = validate_strict_nodes_input(strict)
        if error:
            raise InvalidInput(error)
        if action not in ("connect", "disconnect", "reconnect"):
            raise InvalidInput("Unknown proxy action")
        with self.state.mutation_lock:
            # Invalidate before and after I/O so an in-flight probe cannot repopulate stale data.
            self.state.invalidate()
            try:
                if action != "disconnect":
                    options = []
                    if country is not None:
                        options.append(f'ExitNodes="{nodes}"')
                    if strict_value is not None:
                        options.append(f"StrictNodes={int(strict_value)}")
                    if options:
                        # One SETCONF applies the related options together in Tor.
                        self._command(
                            "SETCONF " + " ".join(options),
                            "Failed to configure ExitNodes/StrictNodes in Tor",
                        )
                        with self.state.lock:
                            if country is not None:
                                self.state.country = normalized
                            if strict_value is not None:
                                self.state.strict_nodes = strict_value
                command, message = {
                    "connect": ("SETCONF DisableNetwork=0", "Failed to enable Tor network"),
                    "disconnect": ("SETCONF DisableNetwork=1", "Failed to disable Tor network"),
                    "reconnect": ("SIGNAL NEWNYM", "Failed to trigger reconnect"),
                }[action]
                self._command(command, message)
                with self.state.lock:
                    if action == "reconnect":
                        self.state.reconnect_count += 1
                        self.state.last_reconnect = self.state.clock.time()
                result: dict[str, Any] = {"action": action, "status": "success"}
                snapshot = self.state.snapshot()
                if action != "disconnect" and snapshot.country:
                    result.update(exit_country=snapshot.country, strict_nodes=snapshot.strict_nodes)
                return result
            finally:
                self.state.invalidate()
