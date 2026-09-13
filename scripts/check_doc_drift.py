#!/usr/bin/env python3
"""Fail the build when documentation names something that no longer exists.

DG-238 was a manual sweep of 34 stale references. The reason it was needed at
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
    Retired("--workspace", "DG-224", "--project <id>"),
    Retired("drunken-register", "S11 / 2.2.0", "drunken-init"),
    Retired("jira_mcp/config.py", "DG-224 (S3)", "core.registry + core.secrets"),
    Retired("AGY_DAEMON_SOCKET", "DG-244", "DRUNKEN_DAEMON_SOCKET"),
    Retired("agy_pids.json", "DG-244", "pids.json"),
    Retired("com.drunkenteam.agy-daemon", "DG-244", "com.drunkenteam.daemon"),
    Retired("discord_outbox.json", "DG-232 / DG-243", "$DRUNKEN_HOME/approvals.json"),
    Retired("Silent Wait Protocol", "DG-232", "request_boss_approval_async"),
    Retired("sync_skills.sh", "DG-269", "install_skills.sh"),
    Retired("sync_agents.sh", "DG-269", "install_agents.sh"),
    Retired("sync_skills.ps1", "DG-269", "install_skills.ps1"),
    Retired("sync_agents.ps1", "DG-269", "install_agents.ps1"),
    Retired(".agents/skills/", "DG-267", "skills/ and agents/, installed by script"),
    Retired("Drunken-Team", "DG-274", "Drunken Guild"),
    Retired("Drunken Team", "DG-274", "Drunken Guild"),
    Retired("drunken-ai-team", "DG-274", "drunken-guild"),
    Retired("Drunken-Team-Guide.md", "DG-274", "Drunken-Guild-Guide.md"),
    # Two template sets stood side by side, and the stale one -- a bridge
    # script, a retired board tool, three commit formats -- was the one the
    # integration guide sent new projects to.
    Retired(".guild_templates", "DG-337", "templates/"),
    Retired("migrate_env_to_registry.py", "DG-351", "scripts/set_secret.py"),
    Retired("clean_host_config.py", "DG-351", "drunken-config --kind host"),
    # The Antigravity plumbing (DG-349). `templates/AGENTS.md` is deliberately
    # not listed: the re-scope's vendor-neutral AGENTS.md template may reuse
    # the name, and a guard that fires on the replacement is a guard that gets
    # switched off.
    Retired(".agents/AGENTS.md", "DG-349", "CLAUDE.md"),
    Retired(".agents/hooks.json", "DG-349", ".claude/settings.json hooks"),
    Retired(
        "install_host_docs.sh", "DG-349", "nothing; the global file was Antigravity's"
    ),
    Retired(
        "check_worktree_isolation.py", "DG-349", "git-workflow's One Working Tree rule"
    ),
    Retired(
        "sync_customizations.py", "DG-349", "install_skills.sh / install_agents.sh"
    ),
    Retired(
        "antigravity_payload_debug", "DG-349", "nothing; the mapping it logged is gone"
    ),
    # Five skills that serve no step of the flow, and the bridge one of them
    # needed (DG-352). The fifteen general skills that moved to the extras
    # plugin are not listed: they still exist, just not in skills/.
    Retired("python-quality-gates", "DG-352", "the project's own AGENTS.md commands"),
    Retired("project-hygiene", "DG-352", "git-workflow"),
    Retired("confluence-sync", "DG-352", "nothing in the core flow"),
    Retired("confluence_bridge.py", "DG-352", "nothing in the core flow"),
    Retired("zero-defect-mindset", "DG-352", "the /build step"),
    Retired("ai-output", "DG-352", "the /build step"),
    # The local pre-push hook duplicated a server-side ruleset that cannot be
    # bypassed, with one that can -- by not being installed (DG-354).
    Retired("setup_git_hooks.py", "DG-354", "the GitHub rulesets on main and develop"),
    # The ten skills the six flow commands replace (DG-353). Only the skill
    # names are listed, not their slash commands: `/refine` and `/next` are
    # also Discord commands that still exist, and a guard that fires on a live
    # command is a guard that gets switched off. Add the slash commands when
    # the Discord lane goes.
    Retired("spec-to-backlog", "DG-353", "the `breakdown` skill (/breakdown)"),
    Retired("backlog-refinement", "DG-353", "the `breakdown` skill (/breakdown)"),
    Retired("task-estimation", "DG-353", "a task is sized to a day in /breakdown"),
    Retired("issue-intake", "DG-353", "the Bug path of the `breakdown` skill"),
    Retired("audit-to-backlog", "DG-353", "the `audit` skill (/audit)"),
    Retired("local-progress-reporter", "DG-353", "the `audit` skill (/audit)"),
    Retired("project-audit-reviewer", "DG-353", "the `audit` skill (/audit)"),
    Retired("test-report-generator", "DG-353", "the `audit` skill (/audit)"),
    Retired("core-engineering", "DG-353", "the `build` skill (/build)"),
    Retired("anti-regression", "DG-353", "the `build` skill (/build)"),
    # The Discord approval machinery, away mode, and the scripts that only the
    # daemon reached (DG-355). The slash commands go in here at last: the
    # comment above `spec-to-backlog` said to add them "when the Discord lane
    # goes", because a guard that fires on a live command is a guard that gets
    # switched off. This is that change.
    Retired("drunken-listen", "DG-355", "nothing; there is no daemon to run"),
    Retired("drunken-away", "DG-355", "nothing; the terminal prompt is the only one"),
    Retired("drunken-discord-mcp", "DG-355", "core.notify, sent from hooks and CI"),
    Retired("drunken-approval-hook", "DG-355", "drunken-hook"),
    Retired("request_boss_approval", "DG-355", "ask the Boss in the conversation"),
    Retired("check_approvals", "DG-355", "nothing; no approval is submitted now"),
    Retired("discord_listener.py", "DG-355", "nothing; the daemon is retired"),
    Retired("discord_router.py", "DG-355", "nothing; the daemon is retired"),
    Retired("approval_manager.py", "DG-355", "nothing; the daemon is retired"),
    Retired("jira_bridge.py", "DG-355", "the drunken-jira-mcp tools"),
    Retired("qa_automation.py", "DG-355", "the /audit step"),
    Retired("setup_daemon_service.py", "DG-355", "nothing; there is no daemon"),
    Retired("check_pending_approval.py", "DG-355", "nothing; no approval can be open"),
    Retired("away mode", "DG-355", "nothing; the harness prompt is the only layer"),
    Retired("Away mode", "DG-355", "nothing; the harness prompt is the only layer"),
    Retired("/refine", "DG-355", "the `breakdown` skill (/breakdown)"),
    Retired("/next", "DG-355", "the `breakdown` skill (/breakdown)"),
    Retired("/qa", "DG-355", "the `build` and `audit` steps"),
)

#: Documents whose job is to record what changed. They have to be able to name
#: a removed thing in order to say it was removed.
RECORDS = frozenset(
    {
        "SESSION_CHECKPOINT.md",
        ".local_backlog.md",
        "CHANGELOG.md",
        # The retirement index. It exists to say what was withdrawn and what
        # replaced it, so it has to be able to name the withdrawn thing. It took
        # over that job from the per-directory notes when `_not_used/` stopped
        # being committed (DG-291) -- see RECORD_DIRS below, which is now about
        # a working directory rather than a tracked one.
        "RETIRED.md",
    }
)

#: Directories where *every* document is a record. `_not_used/` is one by
#: definition: the standing rule is that a retired thing moves there with a note
#: saying what it was and what replaced it, so a note that may not name the
#: retired thing cannot do its job. Listing each RETIRED.md by name in RECORDS
#: would mean this check needs editing every time something is retired -- which
#: is the moment it would instead be switched off.
#:
#: It is no longer tracked (DG-291), so on a fresh clone this matches nothing.
#: That is not a reason to remove it: the directory still exists in a working
#: checkout, and a note read from disk must not be reported as drift.
RECORD_DIRS = ("_not_used",)

#: Put this on a line that must keep a retired name for a stated reason.
ESCAPE = "drift-ok"

#: Not documentation. `.claude/worktrees` and the Antigravity brain hold whole
#: copies of the repo at older commits — scanning them reports drift that is
#: simply the past, and they are not ours to edit in any case.
#:
#: DG-300: matched against each path *relative to REPO_ROOT*, not the
#: absolute path. Every linked worktree this harness creates lives at
#: `<repo>/.claude/worktrees/<name>`, which makes `.claude` an ancestor of
#: REPO_ROOT itself when running from inside one -- matching on the absolute
#: path meant `.claude` appeared in every file's parts there, and every
#: document in the repo was silently skipped.
SKIPPED_DIRS = frozenset(
    {".venv", ".git", "node_modules", "build", "not_use", ".claude", ".mypy_cache"}
)


def documents() -> list[Path]:
    """Markdown outside the records, plus the rulebooks we ship to others.

    `templates/` is included deliberately, suffix or not: those files are
    copied into every downstream project, so a stale instruction there
    propagates rather than just sitting still. `.cursorrules` and
    `.aider.conf.yml` carry no `.md`, and a markdown-only glob skipped them.
    """
    found = [
        path
        for path in REPO_ROOT.rglob("*.md")
        if not (SKIPPED_DIRS & set(path.relative_to(REPO_ROOT).parts))
        and path.name not in RECORDS
        and not (set(RECORD_DIRS) & set(path.relative_to(REPO_ROOT).parts))
    ]
    found += [
        path
        for path in (REPO_ROOT / "templates").glob("*")
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
