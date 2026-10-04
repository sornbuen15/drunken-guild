#!/usr/bin/env python3
"""Refuse a wheel that ships more than the project declares.

DG-363, filed because the installed drunken-guild 1.3.1 carried
``discord_mcp/`` and ``service/`` -- ten files of machinery retired in
DG-355. ``pyproject.toml`` declared ``packages = [scripts, core, route,
jira_mcp]`` and the wheel's own ``top_level.txt`` agreed with it; its
``RECORD`` did not. The cause was a stale ``build/lib/`` -- gitignored, left
over from before the retirement, and never cleaned between builds -- being
copied into the wheel on top of the packages actually declared today.

Neither existing gate can see this. ``verify_clean_install.sh`` installs from
``git archive HEAD``, which never contains an untracked ``build/`` in the
first place; ``drunken-doctor`` asks whether an installed environment is
missing a required module, never what else it is carrying.

This checks the one place the two kinds of file disagree when that happens:
a wheel's own metadata. ``top_level.txt`` is written from the packages the
project declares *now*; ``RECORD`` is the literal list of files that ended
up inside. They read alike for a clean build. They stop agreeing the moment
something undeclared is copied in anyway -- regardless of why, so this names
whatever shows up rather than two directories that happen to be today's
offenders.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def dist_info_dir(names: list[str]) -> str:
    """The `*.dist-info` directory a wheel's RECORD lives under."""
    for name in names:
        if name.endswith(".dist-info/RECORD"):
            return name.rsplit("/", 1)[0]
    raise ValueError("no *.dist-info/RECORD found in this wheel")


def top_level_name(record_path: str) -> str:
    """The name a RECORD entry would appear as in top_level.txt.

    A package contributes its directory name (`core/doctor.py` -> `core`); a
    module that sits at the wheel root contributes its own name without the
    suffix (`six.py` -> `six`).
    """
    head = record_path.split("/", 1)[0]
    return head[:-3] if head.endswith(".py") else head


def undeclared_top_level_modules(wheel_path: Path | str) -> list[str]:
    """RECORD entries whose top-level name is not in the wheel's top_level.txt.

    Sorted and de-duplicated so one retired package with many files is named
    once.
    """
    with zipfile.ZipFile(wheel_path) as archive:
        info_dir = dist_info_dir(archive.namelist())
        declared = set(
            archive.read(f"{info_dir}/top_level.txt").decode("utf-8").split()
        )
        record_lines = archive.read(f"{info_dir}/RECORD").decode("utf-8").splitlines()

    undeclared: dict[str, None] = {}
    for line in record_lines:
        path = line.split(",", 1)[0]
        if not path or path.startswith(f"{info_dir}/"):
            continue
        name = top_level_name(path)
        if name not in declared:
            undeclared.setdefault(name, None)
    return sorted(undeclared)


def explain(wheel_path: Path, undeclared: list[str]) -> str:
    named = ", ".join(undeclared)
    return (
        f"{wheel_path} ships modules the project does not declare: {named}.\n\n"
        "top_level.txt agrees with pyproject.toml; RECORD does not -- the "
        "usual cause is a stale build/lib/ left over from before a module "
        "was retired (DG-363). A `uv build` run against a tree with no "
        "build/ directory reproduces cleanly; hand the exact `rm -r build/` "
        "to the Boss to run rather than deleting it yourself."
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: check_wheel_contents.py <path-to-wheel>", file=sys.stderr)
        return 2

    wheel_path = Path(argv[0])
    undeclared = undeclared_top_level_modules(wheel_path)
    if undeclared:
        print(explain(wheel_path, undeclared), file=sys.stderr)
        return 1

    print(f"{wheel_path} ships only its declared top-level modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
