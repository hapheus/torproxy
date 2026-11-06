#!/usr/bin/env python3
"""Prepend a generated changelog section into CHANGELOG.md.

Usage:
    python3 scripts/prepend_changelog_section.py CHANGELOG.md SECTION.md VERSION

The script inserts SECTION.md content immediately before the first released
version section (e.g. before '## [2.0.2]'), preserving any '## [Unreleased]'
block at the top. If no released version is found, it inserts after the header's
'---' separator.

It is idempotent: if a section for VERSION is already present in CHANGELOG.md,
the file is left unchanged and the script exits with code 0.
"""

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} CHANGELOG.md SECTION.md VERSION",
            file=sys.stderr,
        )
        return 1

    changelog_path = Path(sys.argv[1])
    section_path = Path(sys.argv[2])
    version = sys.argv[3].lstrip("v")

    changelog_text = changelog_path.read_text(encoding="utf-8")
    section_text = section_path.read_text(encoding="utf-8").strip()

    # Idempotency guard: skip if already present
    if f"## [{version}]" in changelog_text:
        print(f"Section for {version} already present — no changes made.")
        return 0

    # Locate the first released version section: ## [0-9
    match = re.search(r"\n## \[\d", changelog_text)
    if match:
        insert_at = match.start() + 1  # right before '## ['
    else:
        # Fall back to inserting after the header separator
        sep = "\n---\n"
        idx = changelog_text.find(sep)
        if idx == -1:
            print("Could not locate insertion point in CHANGELOG.md", file=sys.stderr)
            return 1
        insert_at = idx + len(sep)

    new_text = (
        changelog_text[:insert_at]
        + section_text
        + "\n\n"
        + changelog_text[insert_at:]
    )

    changelog_path.write_text(new_text, encoding="utf-8")
    print(f"Prepended section for v{version} to {changelog_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
