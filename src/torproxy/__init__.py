"""Tor proxy management with explicit configuration and dependency boundaries."""

import re
from importlib import metadata
from pathlib import Path


def _resolve_version() -> str:
    """Single source of truth: derive the version, never hard-code it (ISSUE-07).

    Resolution order:
    1. Installed package metadata (``importlib.metadata``).
    2. ``pyproject.toml`` found next to/above the package (source checkout or
       the Docker image, which ships ``pyproject.toml`` alongside the package).

    Falls back to ``"0.0.0+unknown"`` only if neither source is reachable.
    """
    try:
        return metadata.version("torproxy")
    except metadata.PackageNotFoundError:
        pass

    package_dir = Path(__file__).resolve().parent
    candidates = [package_dir.parent, package_dir.parent.parent, Path.cwd()]
    for base in candidates:
        pyproject = base / "pyproject.toml"
        if pyproject.is_file():
            match = re.search(
                r'^version = "([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE
            )
            if match is not None:
                return match.group(1)
    return "0.0.0+unknown"


__version__ = _resolve_version()
