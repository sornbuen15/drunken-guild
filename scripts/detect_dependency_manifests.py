#!/usr/bin/env python3
"""Detect which dependency manifests are present, for the scheduled audit.

DG-415. The audit workflow (`templates/ci/dependency-audit.yml`, and this
repository's own `.github/workflows/dependency-audit.yml` that uses it) must
run only the audits that apply: a project with nothing but `composer.lock`
has no business failing because `npm audit` found no `package-lock.json` to
read. Detection is a small, pure question — "which manifests exist under
this root" — and it belongs in a script rather than inline shell precisely
so it can be tested against fixture directories without standing up a whole
workflow run.

Three ecosystems, three manifests:

- Python: `uv.lock`, or any `requirements*.txt` (a project without `uv` yet
  may still carry `requirements.txt` / `requirements-dev.txt`).
- PHP: `composer.lock`.
- Node: `package-lock.json`.

A manifest's *absence* is not an error — most projects use at most two of
the three ecosystems — so this prints both what it found and what it did
not, rather than staying silent about the gaps.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Ecosystem name -> the audit step that reads its manifest, for the output
#: this script prints and for the GitHub Actions step outputs it writes.
ECOSYSTEMS = ("pip", "composer", "npm")


def detect_manifests(root: Path) -> dict[str, bool]:
    """Which audits *root* has a manifest for.

    Returns one entry per ecosystem in :data:`ECOSYSTEMS`, so a caller never
    has to guess a key that was not produced.
    """
    has_pip = (root / "uv.lock").is_file() or any(root.glob("requirements*.txt"))
    has_composer = (root / "composer.lock").is_file()
    has_npm = (root / "package-lock.json").is_file()
    return {"pip": has_pip, "composer": has_composer, "npm": has_npm}


def render_report(found: dict[str, bool]) -> str:
    """What the run consulted, and what it could not — printed plainly."""
    lines = []
    for name in ECOSYSTEMS:
        if found.get(name):
            lines.append(f"consulted: {name} (manifest found)")
        else:
            lines.append(f"skipped:   {name} (no manifest)")
    return "\n".join(lines)


def write_github_output(found: dict[str, bool], output_path: Path) -> None:
    """Append `name=true`/`name=false` for each ecosystem to $GITHUB_OUTPUT."""
    with output_path.open("a", encoding="utf-8") as handle:
        for name in ECOSYSTEMS:
            value = "true" if found.get(name) else "false"
            handle.write(f"{name}={value}\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path.cwd()

    found = detect_manifests(root)
    print(render_report(found))

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        write_github_output(found, Path(github_output))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
