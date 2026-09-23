#!/usr/bin/env python3
"""Refuse a commit that names one of the operator's registered projects.

DG-317 took the operator's project ids out of this public repository and a test
guards the tree. The test cannot stop a new occurrence: it skips on CI, where
there is no registry, and it reads tracked files only. On 2026-09-23 a real
project key went back in twice that way. This runs where the mistake is made:

    pre-commit stage   the staged content of every added or modified file
    commit-msg stage   the commit message (``--message <file>``)

against the registry of the machine making the commit. No registry means nothing
to leak, and nothing is blocked. Output names the place, never the id: it lands
in terminals and logs.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

#: This repository's own key is expected everywhere and is not inventory.
OWN_KEY = "drunken-guild"

#: Shorter ids are too generic to match on, and not much of a disclosure.
MIN_ID_LENGTH = 3


def registered_ids() -> List[str]:
    try:
        from core.registry import ProjectRegistry

        ids = list(ProjectRegistry().get_projects())
    except Exception:  # noqa: BLE001 - no readable registry: nothing to compare against
        return []
    return [i for i in ids if i != OWN_KEY and len(i) >= MIN_ID_LENGTH]


def pattern(project_id: str) -> "re.Pattern[str]":
    """The id where it is not part of a longer word (DG-317's boundary rule)."""
    return re.compile(rf"(?<![A-Za-z]){re.escape(project_id)}(?![A-Za-z])", re.I)


def _staged() -> List[tuple[str, str]]:
    names = (
        subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    out = []
    for name in filter(None, names):
        blob = subprocess.run(["git", "show", f":{name}"], capture_output=True)
        try:
            out.append((name, blob.stdout.decode("utf-8")))
        except UnicodeDecodeError:
            continue  # binary: nothing to read a name out of
    return out


def offenders(sources: List[tuple[str, str]], ids: List[str]) -> List[str]:
    patterns = [pattern(i) for i in ids]
    return [
        f"{name}:{n}"
        for name, text in sources
        for n, line in enumerate(text.split("\n"), 1)
        if any(p.search(line) for p in patterns)
    ]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--message", help="commit message file (commit-msg stage)")
    args = parser.parse_args(argv)

    ids = registered_ids()
    if not ids:
        return 0

    if args.message:
        with open(args.message, encoding="utf-8", errors="replace") as handle:
            sources = [("commit message", handle.read())]
    else:
        sources = _staged()

    found = offenders(sources, ids)
    if not found:
        return 0
    print(
        "A registered project id is in what you are committing. This repository is "
        "public. Use alpha/beta, or describe the role instead of naming it:"
    )
    for place in found:
        print(f"  {place}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
