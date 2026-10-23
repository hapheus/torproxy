"""Historical import path for the Tor Control Protocol adapter."""

from torproxy.adapters.tor_control import (
    DEFAULT_CONTROL_PORT,
    DEFAULT_COOKIE_PATH,
    TorControlError,
    authenticate,
    read_reply,
    send_command,
)

__all__ = [
    "DEFAULT_CONTROL_PORT",
    "DEFAULT_COOKIE_PATH",
    "TorControlError",
    "authenticate",
    "read_reply",
    "send_command",
]
