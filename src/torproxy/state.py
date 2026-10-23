"""Per-instance state and cache generations; no lock is held during egress I/O."""

from dataclasses import dataclass
from threading import Lock, RLock

from torproxy.ports import Clock


@dataclass(frozen=True)
class Snapshot:
    country: str | None
    strict_nodes: bool
    reconnect_count: int
    last_reconnect: float | None
    started_at: float
    uptime: float


class RuntimeState:
    def __init__(self, country: str | None, strict_nodes: bool, clock: Clock) -> None:
        self.lock = RLock()
        self.mutation_lock = Lock()
        self.clock = clock
        self.country = country
        self.strict_nodes = strict_nodes
        self.started_at = clock.time()
        self.started_monotonic = clock.monotonic()
        self.reconnect_count = 0
        self.last_reconnect: float | None = None
        self.cached_ip: str | None = None
        self.cached_at = 0.0
        self.generation = 0

    def invalidate(self) -> None:
        with self.lock:
            self.generation += 1
            self.cached_ip = None
            self.cached_at = 0

    def snapshot(self) -> Snapshot:
        with self.lock:
            return Snapshot(
                self.country,
                self.strict_nodes,
                self.reconnect_count,
                self.last_reconnect,
                self.started_at,
                max(0, self.clock.monotonic() - self.started_monotonic),
            )
