"""Values shared by the application and its adapters."""

from dataclasses import dataclass
from typing import Any

CommandResult = tuple[str | None, str | None]
BootstrapResult = tuple[dict[str, Any] | None, str | None]


@dataclass(frozen=True)
class Response:
    status: int
    body: dict[str, Any] | str
    content_type: str = "application/json"
