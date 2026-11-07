"""Optional periodic GeoIP database auto-update (ISSUE-20).

Downloads Tor's geoip/geoip6 files from Tor Project GitLab over HTTPS,
validates them, and installs them atomically into ``TORPROXY_GEOIP_DIR``.
On any failure the previously installed (or bundled) database keeps
working: this module never deletes a working database and never raises
for download/validation failures (callers decide how to log).
"""

from __future__ import annotations

import os
import re
import signal
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from torproxy.configuration import Settings

Fetcher = Callable[[str, int], bytes]

_COUNTRY = re.compile(r"[A-Z]{2}\Z")
_LINE_V4 = re.compile(r"(\d{1,10}),(\d{1,10}),([A-Z]{2})\Z")
_LINE_V6 = re.compile(r"([0-9A-Fa-f:]+),([0-9A-Fa-f:]+),([A-Z]{2})\Z")


def validate_geoip_content(data: bytes, ipv6: bool) -> bool:
    """True when *data* looks like a Tor geoip/geoip6 country database."""
    if not data:
        return False
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    pattern = _LINE_V6 if ipv6 else _LINE_V4
    seen = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not pattern.fullmatch(line):
            return False
        seen += 1
    return seen > 0


def _https_fetch(url: str, max_bytes: int) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("GeoIP URL must use https://")
    request = urllib.request.Request(url, headers={"User-Agent": "torproxy-geoip/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("GeoIP database exceeds TORPROXY_GEOIP_MAX_BYTES")
    return data


def update_geoip(settings: Settings, fetcher: Fetcher | None = None) -> bool:
    """Download, validate and atomically install both GeoIP files.

    Returns True on success. On any failure returns False and leaves
    previously installed files untouched (fallback guarantee).
    """
    fetch = fetcher or _https_fetch
    try:
        v4 = fetch(settings.geoip_url, settings.geoip_max_bytes)
        v6 = fetch(settings.geoip6_url, settings.geoip_max_bytes)
    except Exception as error:  # network, TLS, size, URL errors -> keep old DB
        print(f"[geoip] download failed, keeping previous database: {error}", file=sys.stderr)
        return False
    if not validate_geoip_content(v4, ipv6=False) or not validate_geoip_content(v6, ipv6=True):
        print("[geoip] invalid GeoIP payload, keeping previous database", file=sys.stderr)
        return False

    target_dir = Path(settings.geoip_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for name, data in (("geoip", v4), ("geoip6", v6)):
            tmp = target_dir / f".{name}.tmp"
            tmp.write_bytes(data)
            os.chmod(tmp, 0o644)
            tmp.replace(target_dir / name)
    except OSError as error:
        print(f"[geoip] install failed, keeping previous database: {error}", file=sys.stderr)
        return False
    return True


def has_valid_geoip(settings: Settings) -> bool:
    """True when a previously installed (valid) GeoIP DB exists on disk."""
    target_dir = Path(settings.geoip_dir)
    for name, ipv6 in (("geoip", False), ("geoip6", True)):
        path = target_dir / name
        try:
            if not validate_geoip_content(path.read_bytes(), ipv6=ipv6):
                return False
        except OSError:
            return False
    return True


def _sighup_tor() -> None:
    pid_file = Path("/tmp/tor.pid")
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGHUP)
    except (OSError, ValueError):
        pass  # tor may not be running yet; next start picks the DB up


def run_loop(settings: Settings) -> None:
    """Periodically refresh the GeoIP DB and ask Tor to reload it (SIGHUP)."""
    while True:
        time.sleep(settings.geoip_update_interval)
        if update_geoip(settings):
            _sighup_tor()
            print("[geoip] GeoIP database updated", flush=True)


def main() -> None:
    try:
        settings = Settings.from_mapping(os.environ)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    if not settings.geoip_auto_update:
        return
    if sys.argv[1:] == ["--loop"]:
        run_loop(settings)
        return
    # --once (default): best-effort refresh, never fails startup.
    update_geoip(settings)


if __name__ == "__main__":
    main()
