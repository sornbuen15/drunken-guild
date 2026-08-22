#!/usr/bin/env python3
"""Fail the build when documentation names something that no longer exists.

DT-238 was a manual sweep of 34 stale references. The reason it was needed at
all is that ``--workspace`` stayed advertised in ``README.md`` for two releases
after it was deleted, and it took four passes over this repo to notice. A sweep
has a shelf life; this does not.

**Deliberately dumb.** A real doc-versus-code checker is its own project. A list
of names that are gone costs nothing and catches the exact failure we actually
had. The discipline it depends on is small and enforceable: *the pull request
that removes something adds its name here.*

Two kinds of file are exempt, and the distinction matters — a document that
*records* a removal has to be able to name the thing it removed, or it cannot
say anything useful. Those are listed in :data:`RECORDS`. Everything else is
instructions, and instructions naming a dead command are the bug.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent


class Retired(NamedTuple):
    name: str
    removed_in: str
    use_instead: str


#: Every name that has been removed. Add to this in the PR that removes one.
RETIRED = (
    Retired("--workspace", "DT-224", "--project <id>"),
    Retired("drunken-register", "S11 / 2.2.0", "drunken-init"),
    Retired("jira_mcp/config.py", "DT-224 (S3)", "core.registry + core.secrets"),
    Retired("AGY_DAEMON_SOCKET", "DT-244", "DRUNKEN_DAEMON_SOCKET"),
    Retired("agy_pids.json", "DT-244", "pids.json"),
    Retired("com.drunkenteam.agy-daemon", "DT-244", "com.drunkenteam.daemon"),
    Retired("discord_outbox.json", "DT-232 / DT-243", "$DRUNKEN_HOME/approvals.json"),
    Retired("Silent Wait Protocol", "DT-232", "request_boss_approval_async"),
    Retired("sync_skills.sh", "DG-269", "install_skills.sh"),
    Retired("sync_agents.sh", "DG-269", "install_agents.sh"),
    Retired("sync_skills.ps1", "DG-269", "install_skills.ps1"),
    Retired("sync_agents.ps1", "DG-269", "install_agents.ps1"),
    Retired(".agents/skills/", "DG-267", "skills/ and agents/, installed by script"),
)

#: Documents whose job is to record what changed. They have to be able to name
#: a removed thing in order to say it was removed.
RECORDS = frozenset(
    {
        "SESSION_CHECKPOINT.md",
        ".local_backlog.md",
        "CHANGELOG.md",
    }
)

#: Directories where *every* document is a record. `_not_used/` is one by
#: definition: the standing rule is that a retired thing moves there with a note
#: saying what it was and what replaced it, so a note that may not name the
#: retired thing cannot do its job. Listing each RETIRED.md by name in RECORDS
#: would mean this check needs editing every time something is retired -- which
#: is the moment it would instead be switched off.
RECORD_DIRS = ("_not_used",)

#: Put this on a line that must keep a retired name for a stated reason.
ESCAPE = "drift-ok"

#: Not documentation. `.claude/worktrees` and the Antigravity brain hold whole
#: copies of the repo at older commits — scanning them reports drift that is
#: simply the past, and they are not ours to edit in any case.
SKIPPED_DIRS = frozenset(
    {".venv", ".git", "node_modules", "build", "not_use", ".claude", ".mypy_cache"}
)


def documents() -> list[Path]:
    """Markdown outside the records, plus the rulebooks we ship to others.

    `.guild_templates/` is included deliberately: those files are copied into
    every downstream project, so a stale instruction there propagates rather
    than just sitting still.
    """
    found = [
        path
        for path in REPO_ROOT.rglob("*.md")
        if not (SKIPPED_DIRS & set(path.parts))
        and path.name not in RECORDS
        and not (set(RECORD_DIRS) & set(path.parts))
    ]
    found += [
        path
        for path in (REPO_ROOT / ".guild_templates").glob("*")
        if path.is_file() and path.suffix != ".md"
    ]
    return sorted(found)


def scan() -> list[str]:
    problems = []
    for path in documents():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if ESCAPE in line:
                continue
            for retired in RETIRED:
                if retired.name in line:
                    relative = path.relative_to(REPO_ROOT)
                    problems.append(
                        f"{relative}:{number}: names '{retired.name}', removed "
                        f"in {retired.removed_in}. Use {retired.use_instead}."
                    )
    return problems


def main() -> int:
    problems = scan()
    if not problems:
        print(f"[check_doc_drift] {len(documents())} documents, nothing retired.")
        return 0

    print("Documentation refers to things that no longer exist:\n", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        f"\nFix the text, or add '{ESCAPE}' to the line with a reason if it has "
        "to stay.\nIf one of these is not actually gone, remove it from RETIRED "
        f"in {Path(__file__).name}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
