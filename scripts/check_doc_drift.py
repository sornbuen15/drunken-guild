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

import re
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
    Retired("--workspace", "DG-224", "the project argument on each tool"),
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
    Retired(
        "clean_host_config.py",
        "DG-351",
        "onboard_project.py --merge-mcp-config, which prunes on every merge",
    ),
    # The Antigravity plumbing (DG-349). `templates/AGENTS.md` is deliberately
    # not listed: the re-scope's vendor-neutral AGENTS.md template may reuse
    # the name, and a guard that fires on the replacement is a guard that gets
    # switched off.
    Retired(".agents/AGENTS.md", "DG-349", "AGENTS.md"),
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
    # The ten skills the flow commands replace (DG-353). Only the skill
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
    # DG-341. Deliberately the *MCP server* spelling and not a bare
    # `--project`: the flag is alive and correct on `drunken-doctor`,
    # `drunken-init` and `drunken-usage`, so a bare entry would fire on every
    # line that documents those and get switched off within a day.
    Retired(
        "drunken-jira-mcp --project",
        "DG-341",
        "the project argument on each tool; the server takes none",
    ),
    Retired(
        '"args": ["--project"',
        "DG-341",
        "no args at all — one MCP entry serves every project",
    ),
    # DG-356. Four commands ship; these two answered questions nothing asks any
    # more. The library behind `drunken-config` survives — what is retired is
    # the command, so the name is what the guard looks for.
    Retired(
        "drunken-config",
        "DG-356",
        "install_mcp.sh for the config; drunken-doctor --requirements for the pins",
    ),
    Retired("drunken-status", "DG-356", "the /audit step"),
    # Retired with the Discord lane but missed by this list until DG-360 found
    # CLAUDE.md still explaining how to call it, five sessions later. A rule
    # about a function nobody can call is worse than no rule: it is read as
    # current.
    Retired("require_discord", "DG-355", "nothing; no Discord credential is resolved"),
    Retired("--kind install", "DG-356", "drunken-doctor --requirements"),
    Retired("--kind host", "DG-356", "onboard_project.py --merge-mcp-config"),
    # DG-427. A 211-line rulebook that predated REQ-015's one-line CLAUDE.md
    # adapter and restated coordination rules a project's own AGENTS.md now
    # owns. Moved out of templates/ to _not_used/ (uncommitted); RETIRED.md
    # carries the row. The name below is also a substring of the
    # already-retired dotted name above (DG-337's ".guild_templates/"), so a
    # line naming that one trips both -- test_doc_drift.py's own fixture for
    # DG-337 accounts for it rather than assuming an exact count of one.
    Retired(
        "templates/CLAUDE.md",
        "DG-427",
        "a project's own AGENTS.md (REQ-015), written by drunken-init",
    ),
    # DG-522. A document explaining *that* a server was retired is doing
    # RETIRED.md's job a second time outside RETIRED.md/CHANGELOG, the one
    # exemption large enough to hold the detail. Naming the retired thing to
    # say it is gone is still naming it -- the point DG-337's guard already
    # made about ".guild_templates".
    Retired(
        "drunken-board-mcp",
        "DG-265",
        "Jira via drunken-jira-mcp; the retirement detail is in RETIRED.md",
    ),
    Retired(
        "approval server",
        "DG-355",
        "ask the Boss in the conversation; the retirement detail is in RETIRED.md",
    ),
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

#: `tests/fixtures/` is not scanned as a document source (DG-430, gap 3): it
#: holds realistic-looking markdown built on purpose to prove *other*
#: checkers notice (or refuse) a stray file, never a document someone reads
#: for instructions. `documents()` used a blanket `rglob("*.md")` with no
#: exception for it, so any such fixture was silently counted here too --
#: narrower than skipping all of `tests/`, which still carries a real
#: document (`tests/test_jira_workflow.md`) that belongs in the scan.
_FIXTURES_PREFIX = ("tests", "fixtures")


def _under_fixtures(path: Path) -> bool:
    """Case-sensitive on purpose (DG-433): `SKIPPED_DIRS` above is matched
    the same way, an exact-string set lookup against each path segment, and
    this repository's own directories are created lower-case. Folding case
    here while `SKIPPED_DIRS` stays exact would make the two exclusion
    rules disagree about what "the same name" means for no documented
    reason — if a case-insensitive filesystem ever produces a real
    `Tests/Fixtures/`, fix both together rather than one in isolation."""
    parts = path.relative_to(REPO_ROOT).parts
    return parts[: len(_FIXTURES_PREFIX)] == _FIXTURES_PREFIX


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
        and not _under_fixtures(path)
    ]
    found += [
        path
        for path in (REPO_ROOT / "templates").glob("*")
        if path.is_file() and path.suffix != ".md"
    ]
    # `.claude` is skipped above because linked worktrees live under it, holding
    # whole copies of this repository at older commits -- scanning those reports
    # drift that is simply the past. `.claude/rules/` is the opposite: it is
    # instructions, moved out of CLAUDE.md in DG-360 precisely so they load only
    # where they apply, and an instruction naming something retired is the bug
    # this check exists for. Named explicitly rather than by unskipping the
    # parent, so the worktrees stay out.
    found += sorted((REPO_ROOT / ".claude" / "rules").rglob("*.md"))
    return sorted(found)


#: DG-522. The doc set the three structural checks below run against: the
#: top-level docs that tell the install/architecture/Jira story, plus the one
#: detail page. Not the whole repository -- a skill's own `#rules` anchor and
#: a plugin's `references/` link follow no numbering convention at all, and
#: scanning them would report noise rather than the drift this ticket found
#: (the Guide's own §3.4 pointing at a §3.2 that does not say what §3.4
#: claims, and its heading numbering jumping 3.4 to 3.6).
LINKED_DOC_NAMES = (
    "README.md",
    "GETTING_STARTED.md",
    "Drunken-Guild-Guide.md",
    "Integration-Guide.md",
    "DESIGN.md",
    "CONTRIBUTING.md",
    "REPOSITORY_MAP.md",
    "AGENTS.md",
    "CONFIG_REPO.md",
)


def linked_documents() -> list[Path]:
    paths = [REPO_ROOT / name for name in LINKED_DOC_NAMES]
    paths.append(REPO_ROOT / "docs" / "REFERENCE.md")
    return [path for path in paths if path.exists()]


_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s][^)]*)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_HEADING_NUM_RE = re.compile(r"^(#{2,4})\s+(\d+)(?:\.(\d+))?\.?\s+\S")
_SECTION_REF_RE = re.compile(r"§\s*(\d+(?:\.\d+)*)")
_NON_SLUG_CHARS = re.compile(r"[^\w\s-]")
_EMPHASIS_CHARS = re.compile(r"[`*_]")
_WHITESPACE_RUN = re.compile(r"^\s+|\s+$")
_WHITESPACE_CHAR = re.compile(r"\s")


def _slugify(heading: str, seen: dict[str, int]) -> str:
    """Approximates GitHub's heading-anchor algorithm closely enough to catch
    a genuinely missing anchor, including its duplicate-heading suffixing.

    Each whitespace *character* becomes its own hyphen rather than collapsing
    a run into one — GitHub does the same, which is why a heading with an
    em-dash surrounded by spaces (two adjacent spaces once the dash itself is
    stripped as punctuation) anchors with a double hyphen, exactly what
    `docs/REFERENCE.md`'s own Contents list already links to."""
    text = _EMPHASIS_CHARS.sub("", heading.strip().lower())
    text = _NON_SLUG_CHARS.sub("", text)
    text = _WHITESPACE_RUN.sub("", text)
    slug = _WHITESPACE_CHAR.sub("-", text)
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def heading_slugs(text: str) -> set[str]:
    seen: dict[str, int] = {}
    slugs = set()
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            slugs.add(_slugify(match.group(2), seen))
    return slugs


#: `SESSION_CHECKPOINT.md` is a per-session scratch note, deliberately
#: untracked (`.gitignore`) so it never ships in a checkout -- a document is
#: allowed to link to it even though it is routinely absent on disk.
EXPECTED_ABSENT_LINK_TARGETS = frozenset({"SESSION_CHECKPOINT.md"})


def _check_one_link(path: Path, number: int, link: str, text: str) -> str | None:
    """One problem string, or `None` if *link* resolves cleanly."""
    if link.startswith("#"):
        # A bare `#anchor` targets this same document.
        if link[1:] and link[1:] not in heading_slugs(text):
            return (
                f"{path.relative_to(REPO_ROOT)}:{number}: anchor '{link}' has "
                "no matching heading in this document."
            )
        return None

    target_part, _, anchor = link.partition("#")
    if Path(target_part).name in EXPECTED_ABSENT_LINK_TARGETS:
        return None
    target_path = (path.parent / target_part).resolve()
    if not target_path.exists():
        return (
            f"{path.relative_to(REPO_ROOT)}:{number}: link target "
            f"'{target_part}' does not exist."
        )
    if not anchor or target_path.suffix.lower() != ".md":
        return None
    try:
        target_text = target_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if anchor not in heading_slugs(target_text):
        return (
            f"{path.relative_to(REPO_ROOT)}:{number}: anchor '#{anchor}' has "
            f"no matching heading in '{target_part}'."
        )
    return None


def check_links(paths: list[Path]) -> list[str]:
    """A relative link or an in-page anchor that resolves nowhere."""
    problems = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if ESCAPE in line:
                continue
            for link in _LINK_RE.findall(line):
                if link.startswith(("http://", "https://", "mailto:")):
                    continue
                problem = _check_one_link(path, number, link, text)
                if problem:
                    problems.append(problem)
    return problems


def check_section_references(paths: list[Path]) -> list[str]:
    """A `§N` or `§N.M` pointing at a section number this same
    document's own numbered headings never declare."""
    problems = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        declared: set[str] = set()
        for line in lines:
            match = _HEADING_NUM_RE.match(line)
            if match:
                number = match.group(2) + (
                    f".{match.group(3)}" if match.group(3) else ""
                )
                declared.add(number)
        for number, line in enumerate(lines, 1):
            if ESCAPE in line:
                continue
            for ref in _SECTION_REF_RE.findall(line):
                if ref not in declared:
                    problems.append(
                        f"{path.relative_to(REPO_ROOT)}:{number}: §{ref} "
                        "refers to a section number this document does not "
                        "declare in a heading."
                    )
    return problems


def check_heading_gaps(paths: list[Path]) -> list[str]:
    """A numbered heading sequence that skips a number -- `3.4` to `3.6` with
    no `3.5` -- the exact shape DG-522 found in the old Guide."""
    problems = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        top_numbers: list[int] = []
        children: dict[int, list[int]] = {}
        for line in text.splitlines():
            match = _HEADING_NUM_RE.match(line)
            if not match:
                continue
            level = len(match.group(1))
            parent = int(match.group(2))
            child = match.group(3)
            if child is None:
                if level == 2:
                    top_numbers.append(parent)
            else:
                children.setdefault(parent, []).append(int(child))

        relative = path.relative_to(REPO_ROOT)
        expected = list(range(1, len(top_numbers) + 1))
        if top_numbers and top_numbers != expected:
            problems.append(
                f"{relative}: top-level heading numbers {top_numbers} are not "
                f"a contiguous run starting at 1 (expected {expected})."
            )
        for parent, numbers in children.items():
            expected_children = list(range(1, len(numbers) + 1))
            if numbers != expected_children:
                problems.append(
                    f"{relative}: heading numbers under section {parent} are "
                    f"{numbers}, not a contiguous run starting at 1 (expected "
                    f"{expected_children})."
                )
    return problems


#: DG-522 lead review. A document claiming the registry (or its secret file)
#: may be committed is not drift against something *removed* -- it is wrong
#: against a standing rule (REQ-023: no registered id, Jira URL or email
#: reaches a repository) that this exact phrase stated the opposite of in the
#: old Guide, carried forward unexamined into its rewrite. A short forbidden-
#: phrase list, the same shape as RETIRED, catches it going forward.
FORBIDDEN_CLAIMS = (
    (
        "can be committed and shared",
        "the registry and its secret file are not for a public repo (REQ-023)",
    ),
    (
        "committed, reviewed and shared",
        "the registry and its secret file are not for a public repo (REQ-023)",
    ),
    (
        "so it can be committed",
        "the registry and its secret file are not for a public repo (REQ-023)",
    ),
)


def check_forbidden_claims(paths: list[Path]) -> list[str]:
    """A line claiming the registry or its secret file may be committed."""
    problems = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if ESCAPE in line:
                continue
            for phrase, reason in FORBIDDEN_CLAIMS:
                if phrase in line:
                    problems.append(
                        f"{path.relative_to(REPO_ROOT)}:{number}: claims "
                        f"'{phrase}' -- {reason}."
                    )
    return problems


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

    problems += check_forbidden_claims(documents())

    linked = linked_documents()
    problems += check_links(linked)
    problems += check_section_references(linked)
    problems += check_heading_gaps(linked)
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
