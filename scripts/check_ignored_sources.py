#!/usr/bin/env python3
"""Stop a commit that is quietly missing a source file.

DG-259, filed because it happened. `.gitignore` carries `*token*` as a
credential-hygiene rule; it matched ``tests/test_jira_token_economy.py``, and
``git add -A`` skipped the file without a word. The commit succeeded,
pre-commit passed, and the local suite stayed green because the file was still
on disk. A PR was opened claiming 21 new tests and contained none of them.

Nothing in the pipeline could have contradicted it. That is the gap this
closes: **nothing reported "a source file you wrote is not in the commit".**

Deliberately about the class rather than the pattern. `*credential*` has the
same property, both sit beside precise rules like `*.pem`, and a project with a
token-economy ticket and a credential resolver will keep producing filenames
that match. Narrowing the rules would trade one risk for another; reporting the
consequence costs nothing either way.
"""

from __future__ import annotations

import subprocess  # nosec B404 - git, invoked with a fixed argument list
import sys
from pathlib import Path
from typing import Iterable, List

#: Where source lives. An ignored file anywhere else -- `.env` at the root,
#: `htmlcov/` -- is ignored on purpose and is none of this check's business.
#:
#: `skills` and `agents` are here because this repository ships two products,
#: not one. They are markdown rather than Python, and nothing else in the tool
#: chain looks at them -- ruff, mypy and pytest all stop at `src`, `tests` and
#: `scripts` -- so an ignore rule that swallowed one would be caught by nothing
#: at all.
#:
#: They were previously reachable only through `.agents/skills`, which was the
#: Antigravity copy and is now retired (DG-267). The guard had therefore never
#: covered the real `skills/` tree, and `agents/` never at all.
SOURCE_DIRS = ("src", "tests", "scripts", "skills", "agents")

#: Nested source roots, checked by prefix rather than by first path component.
#: Empty now that `.agents/skills` is gone; kept because the mechanism is what
#: makes an ignored source directory nested under an ignored parent findable,
#: and the next one of those should not have to reinvent it.
SOURCE_PREFIXES: tuple[tuple[str, ...], ...] = ()

#: Deliverables that live at the repository root and have no source suffix.
ROOT_SOURCE_NAMES = frozenset({"Dockerfile", "Makefile"})

#: Root files that are ignored on purpose. Without these the guard would flag
#: scratch on its first run, and a guard that cries wolf gets switched off --
#: which is the failure it exists to prevent, one level up.
#:
#: SESSION_CHECKPOINT.md is here because it is a session scratchpad, not a
#: deliverable -- the Boss confirmed it belongs to whoever's session wrote it,
#: not to git (DG-293). Its tracked template, templates/SESSION_CHECKPOINT.md,
#: is nested and never reaches this root-only check.
#: ``.mcp.json`` is operating config, not source (DG-313): machine paths and
#: which project each MCP server serves. DG-250 puts it at the wrapper level,
#: outside git; this repo is its own wrapper, so it sits here and stays
#: untracked. ``scripts/install/install_mcp.sh`` generates it.
ROOT_ALLOWED = (
    "scratch_",
    "requirements.lock",
    "SESSION_CHECKPOINT.md",
    ".mcp.json",
)

#: What a human writes, as opposed to what a build leaves behind.
SOURCE_SUFFIXES = frozenset({".py", ".sh", ".toml", ".md", ".json", ".yaml", ".yml"})

#: Directories that legitimately hold ignored files inside a source tree. There
#: are hundreds of `__pycache__` entries in a working tree, and a guard that
#: flags those is noise on its first run and switched off by its second.
ARTIFACT_DIRS = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv"}
)


def is_source(path: Path) -> bool:
    """Whether *path* is something a person wrote and meant to commit."""
    parts = path.parts
    if not parts:
        return False
    if len(parts) == 1:
        # A root-level deliverable. Dockerfile was ignored by a rule written
        # when it was scratch, and stayed out of the commit that shipped it.
        name = parts[0]
        if any(name.startswith(prefix) for prefix in ROOT_ALLOWED):
            return False
        return name in ROOT_SOURCE_NAMES or Path(name).suffix in SOURCE_SUFFIXES

    in_root = parts[0] in SOURCE_DIRS
    in_nested = any(parts[: len(prefix)] == prefix for prefix in SOURCE_PREFIXES)
    if not (in_root or in_nested):
        return False
    if any(part in ARTIFACT_DIRS for part in parts):
        return False
    return path.suffix in SOURCE_SUFFIXES


def offenders(ignored: Iterable[str]) -> List[Path]:
    """The ignored paths that look like source, in the order given."""
    return [Path(entry) for entry in ignored if is_source(Path(entry))]


def explain(paths: List[Path]) -> str:
    """Why the commit stopped, in terms of what will otherwise go wrong.

    "Blocked" on its own gets bypassed. The message has to say that the file
    will simply be absent while every other surface reports success, because
    that is the part nobody expects.
    """
    listed = "\n".join(f"  {path}" for path in paths)
    return (
        "These source files are excluded by .gitignore and will NOT be in the "
        f"commit:\n\n{listed}\n\n"
        "Nothing else will tell you. `git add -A` skips them silently, the "
        "commit succeeds, and the suite stays green because the files are "
        "still on disk -- which is how a PR once shipped claiming 21 tests it "
        "did not contain.\n\n"
        "Rename the file so it stops matching, or add a negation to "
        ".gitignore. Prefer renaming: `git add -f` works once and leaves the "
        "next file to vanish the same way."
    )


def ignored_paths() -> List[str]:
    """Ignored-but-present files, as git itself reports them."""
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        [
            "git",
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            *SOURCE_DIRS,
            ".",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.stdout.split() if result.returncode == 0 else []


def main() -> int:
    found = offenders(ignored_paths())
    if not found:
        return 0
    print(explain(found), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
