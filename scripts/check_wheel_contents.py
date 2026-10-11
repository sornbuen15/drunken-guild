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

The invariant this checks is narrow and entirely within one wheel: its own
``RECORD`` against its own ``top_level.txt``. ``top_level.txt`` is written
from the packages the project declares *now*; ``RECORD`` is the literal list
of files that ended up inside. They read alike for a clean build. They stop
agreeing the moment something undeclared is copied in anyway -- regardless of
why, so this names whatever shows up rather than two directories that happen
to be today's offenders.

**The build invocation matters as much as the check.** ``uv build`` without
flags builds an sdist first and builds the wheel from *that* -- a fresh copy
that never sees a stale, gitignored ``build/lib/`` in the working tree, so it
reports a false "clean" on exactly the tree this exists to catch.
``uv build --wheel`` skips the sdist step and builds in place, which is why
it is the invocation `verify_clean_install.sh` uses (DG-363 review).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


class WheelInspectionError(ValueError):
    """The wheel could not be inspected at all.

    Distinct from finding an undeclared module: this is a missing
    `top_level.txt`/`RECORD` or a corrupt archive, and the caller must get a
    message naming the problem rather than a traceback.
    """


def dist_info_dir(names: list[str]) -> str:
    """The `*.dist-info` directory a wheel's RECORD lives under."""
    for name in names:
        if name.endswith(".dist-info/RECORD"):
            return name.rsplit("/", 1)[0]
    raise WheelInspectionError("no *.dist-info/RECORD found in this wheel")


def top_level_name(record_path: str) -> str:
    """The name a RECORD entry would appear as in top_level.txt.

    A package contributes its directory name (`core/doctor.py` -> `core`); a
    module that sits at the wheel root contributes its own name without the
    suffix (`six.py` -> `six`).
    """
    head = record_path.split("/", 1)[0]
    return head[:-3] if head.endswith(".py") else head


def _is_metadata_entry(record_path: str, info_dir: str) -> bool:
    """Wheel-format bookkeeping that is never a declared top-level module.

    ``*.dist-info/`` is the wheel's own metadata; ``*.data/`` is the other
    reserved top-level directory the wheel spec defines (scripts, headers,
    data files installed outside the package tree) and is just as
    legitimate as `.dist-info` -- neither is ever named in `top_level.txt`,
    and flagging either would fail every wheel that uses it.
    """
    head = record_path.split("/", 1)[0]
    return record_path.startswith(f"{info_dir}/") or head.endswith(".data")


def undeclared_top_level_modules(wheel_path: Path | str) -> list[str]:
    """RECORD entries whose top-level name is not in the wheel's top_level.txt.

    Sorted and de-duplicated so one retired package with many files is named
    once. Raises `WheelInspectionError` -- never a bare `KeyError` or
    `zipfile.BadZipFile` -- when the wheel cannot be read at all.
    """
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            info_dir = dist_info_dir(archive.namelist())
            try:
                top_level_raw = archive.read(f"{info_dir}/top_level.txt")
            except KeyError as exc:
                raise WheelInspectionError(
                    f"{wheel_path} has no {info_dir}/top_level.txt to compare "
                    "RECORD against"
                ) from exc
            try:
                record_raw = archive.read(f"{info_dir}/RECORD")
            except KeyError as exc:
                raise WheelInspectionError(
                    f"{wheel_path} has no {info_dir}/RECORD to compare "
                    "top_level.txt against"
                ) from exc
    except zipfile.BadZipFile as exc:
        raise WheelInspectionError(f"{wheel_path} is not a valid zip file") from exc
    except FileNotFoundError as exc:
        raise WheelInspectionError(f"{wheel_path} does not exist") from exc

    declared = set(top_level_raw.decode("utf-8").split())
    record_lines = record_raw.decode("utf-8").splitlines()

    undeclared: dict[str, None] = {}
    for line in record_lines:
        path = line.split(",", 1)[0]
        if not path or _is_metadata_entry(path, info_dir):
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
        "was retired (DG-363). `uv build --wheel` against a tree with no "
        "build/ directory reproduces cleanly; hand the exact `rm -r build/` "
        "to the Boss to run rather than deleting it yourself."
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: check_wheel_contents.py <path-to-wheel>", file=sys.stderr)
        return 2

    wheel_path = Path(argv[0])
    try:
        undeclared = undeclared_top_level_modules(wheel_path)
    except WheelInspectionError as exc:
        print(f"cannot inspect {wheel_path}: {exc}", file=sys.stderr)
        return 2

    if undeclared:
        print(explain(wheel_path, undeclared), file=sys.stderr)
        return 1

    print(f"{wheel_path} ships only its declared top-level modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
