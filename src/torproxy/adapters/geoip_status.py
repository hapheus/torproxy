"""Filesystem adapter for the GeoIP auto-update status file (ISSUE-117).

The GeoIP updater (``torproxy.runtime.geoip``) runs as a separate
process and records its latest outcome as JSON in the GeoIP dir.
This adapter is the only place that reads that file; core modules
receive the outcome through the ``GeoIpStatus`` port and never do I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileGeoIpStatus:
    def __init__(self, geoip_dir: str) -> None:
        self._path = Path(geoip_dir) / "geoip-status.json"

    def snapshot(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None
