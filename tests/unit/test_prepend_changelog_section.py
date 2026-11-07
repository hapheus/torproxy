"""Tests for scripts/prepend_changelog_section.py (ISSUE-17 / PR #95)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepend_changelog_section.py"

INITIAL = """\
# Changelog

---

## [Unreleased]

## [2.0.2] — 2026-11-06

### Fixed
- Something

---

[Unreleased]: https://github.com/hapheus/torproxy/compare/v2.0.2...HEAD
[2.0.2]: https://github.com/hapheus/torproxy/compare/v2.0.1...v2.0.2
"""

SECTION = """\
## [2.1.0] — 2026-11-06

### Fixed
- New thing
"""


def _run(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    changelog = tmp_path / "CHANGELOG.md"
    section = tmp_path / "SECTION.md"
    changelog.write_text(INITIAL, encoding="utf-8")
    section.write_text(SECTION, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(changelog), str(section), "2.1.0"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_prepends_section_and_maintains_comparison_links(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    # New section inserted before the previous newest release, after Unreleased.
    assert text.index("## [Unreleased]") < text.index("## [2.1.0]") < text.index("## [2.0.2]")
    # Comparison links kept consistent so the PR-gate changelog check passes.
    assert "[2.1.0]: https://github.com/hapheus/torproxy/compare/v2.0.2...v2.1.0" in text
    assert "[Unreleased]: https://github.com/hapheus/torproxy/compare/v2.1.0...HEAD" in text
    assert "[2.0.2]:" in text


def test_prepend_is_idempotent(tmp_path: Path) -> None:
    assert _run(tmp_path).returncode == 0
    changelog = tmp_path / "CHANGELOG.md"
    section = tmp_path / "SECTION.md"
    before = changelog.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(changelog), str(section), "2.1.0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert changelog.read_text(encoding="utf-8") == before
