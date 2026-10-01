# mypy: ignore-errors
"""DG-393 follow-up. Review verdict on PR 127: the ten anchored sentences in
`test_agents_md_pointers.py` are a closed list, and DG-393's own ACCEPTANCE
line -- "a check fails a new reference to an instruction file no template or
init step produces" -- is open-ended. Proven by the reviewer planting two new
sentences naming a file nothing produces (`.claude/AGENT_RULES.md`) in a
README paragraph and in `skills/flow/ddd/SKILL.md`; the suite stayed green
both times because nothing scanned either location for an unknown filename.

This module finds the reference *structurally*, instead of listing the
sentences that currently make one: any path-ish token ending in a name that
looks like a per-agent instruction file -- `AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, a `*_RULES.md` family, or the flat-file adapters
`.cursorrules` / `.aider.conf.yml` -- found anywhere across the tracked docs
and skills DG-393's reviewer named: README, GETTING_STARTED, `templates/`,
every `skills/**/SKILL.md`, `agents/`, the jira-mcp project-id error text,
and this repo's own root AGENTS.md.

A bare token (no path separator) is valid when it names a file
`scaffold.instruction_files` actually writes at a project's root, or the
basename of a file genuinely shipped under `templates/` -- both read back
from disk rather than hand-copied here, so a rename on either producing side
fails this test too. A path-ish token is valid when that path resolves to a
real tracked file in this repository (`./AGENTS.md`, `templates/CLAUDE.md`,
`src/core/templates/AGENTS.md` all do) -- that is the "exists and is read"
half of the check, and it is why a retired or merely invented path fails
even though it still spells a real filename at the end.

What is left over after both of those -- an illustrative example path that
was never meant to resolve -- is the only thing the explicit ALLOWLIST below
carries, one entry, with its reason.
"""

from __future__ import annotations

import re
from pathlib import Path

from core import scaffold

REPO_ROOT = Path(__file__).resolve().parent.parent

#: What counts, structurally, as "a reference to an instruction file":
#: a run of path characters ending in one of these names.
_CORE = (
    r"(?:AGENTS\.md|CLAUDE\.md|GEMINI\.md|[A-Z][A-Z0-9_]*_RULES\.md"
    r"|\.cursorrules|\.aider\.conf\.yml)"
)
_TOKEN = re.compile(r"[\w./\\~-]*" + _CORE)

#: (file relative to REPO_ROOT, exact token) -> why this one is not expected
#: to resolve to a real file, even though it matches the pattern above.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("GETTING_STARTED.md", "~/Projects/my-project/CLAUDE.md"): (
        "the cp walkthrough's own illustrative target under the reader's "
        "home directory, not a path in this repository"
    ),
}


def _scan_files() -> list[Path]:
    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "GETTING_STARTED.md",
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "src" / "jira_mcp" / "server.py",
    ]
    files += sorted(p for p in (REPO_ROOT / "templates").rglob("*") if p.is_file())
    files += sorted((REPO_ROOT / "skills").rglob("SKILL.md"))
    files += sorted((REPO_ROOT / "agents").rglob("*.md"))
    return files


def _produced_filenames(tmp_path: Path) -> set[str]:
    """Every bare filename a reference to an instruction file is allowed to
    name: what `drunken-init` writes at a project's root, run for real
    against a scratch directory, plus the basename of every file actually
    shipped under `templates/` -- both read back from disk, not restated."""
    scaffold.instruction_files(tmp_path, "demo-project", None)
    produced = {entry.name for entry in tmp_path.iterdir() if entry.is_file()}
    produced |= {p.name for p in (REPO_ROOT / "templates").rglob("*") if p.is_file()}
    return produced


def _resolves(token: str, produced: set[str]) -> bool:
    if "/" not in token and "\\" not in token:
        return token in produced
    normalized = token.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("~/"):
        # Never a repository-relative path -- the reader's own home
        # directory. Only reached for a token not already in ALLOWLIST.
        return False
    if "/" not in normalized:
        return normalized in produced
    return (REPO_ROOT / normalized).is_file()


def scan(tmp_path: Path) -> list[str]:
    """Every unresolved reference found, formatted `path:line: message` --
    the shape the test below asserts is empty, and the shape each mutation
    test below asserts is exactly the planted line."""
    produced = _produced_filenames(tmp_path)
    problems: list[str] = []
    for path in _scan_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for match in _TOKEN.finditer(line):
                token = match.group(0)
                if _resolves(token, produced):
                    continue
                if (relative, token) in ALLOWLIST:
                    continue
                problems.append(
                    f"{relative}:{number}: references {token!r}, which no "
                    "template or init step produces and which is not a "
                    "real file in this repository"
                )
    return problems


def test_every_instruction_file_reference_resolves(tmp_path: Path) -> None:
    problems = scan(tmp_path)
    assert problems == [], "\n".join(problems)


def test_scan_covers_more_than_a_handful_of_files() -> None:
    """A scope this narrow could pass by accident; pin a floor so a future
    refactor that empties `_scan_files()` is caught here too."""
    assert len(_scan_files()) >= 15


# --- Proof the scan actually fires, on the reviewer's own two mutations plus
# the three from the first round of this ticket. Each is applied to a scratch
# copy of the real file's text (never written back to the tracked file), run
# through the same `scan()` used above, and shown to report exactly the
# planted line -- then nothing on disk is touched, so there is nothing to
# revert.


def _scan_text(tmp_path: Path, relative: str, text: str) -> list[str]:
    """Same resolution rules as `scan()`, for one in-memory file -- lets a
    mutation be proven without ever writing a broken sentence to a tracked
    file, which the project's own guards (and good sense) rule out."""
    produced = _produced_filenames(tmp_path)
    problems: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in _TOKEN.finditer(line):
            token = match.group(0)
            if _resolves(token, produced):
                continue
            if (relative, token) in ALLOWLIST:
                continue
            problems.append(f"{relative}:{number}: references {token!r}")
    return problems


def test_catches_the_reviewers_readme_paragraph(tmp_path: Path) -> None:
    """DG-393 PR 127 review: a new README paragraph naming
    `.claude/AGENT_RULES.md`, a file no template or init step produces."""
    mutated = (
        "## A new paragraph\n\n"
        "If your project needs extra rules, add them to "
        "`.claude/AGENT_RULES.md` and every agent reads them automatically.\n"
    )
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [
        "README.md:3: references '.claude/AGENT_RULES.md'",
    ]


def test_catches_the_reviewers_ddd_skill_sentence(tmp_path: Path) -> None:
    """Same planted filename, as a new sentence in a SKILL.md."""
    mutated = (
        "Record the decision in `.claude/AGENT_RULES.md` so the next session "
        "picks it up.\n"
    )
    problems = _scan_text(tmp_path, "skills/flow/ddd/SKILL.md", mutated)
    assert problems == [
        "skills/flow/ddd/SKILL.md:1: references '.claude/AGENT_RULES.md'",
    ]


def test_catches_a_retired_directory_prefix(tmp_path: Path) -> None:
    """Round one, mutation 1: a real filename, a retired directory in front
    of it -- the file that name used to live at is gone (DG-349), so the
    path does not resolve even though the trailing filename is spelled
    correctly."""
    mutated = "the project's root `.agents/AGENTS.md` is the map, and the defaults\n"
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [
        "README.md:1: references '.agents/AGENTS.md'",
    ]


def test_does_not_catch_a_reworded_sentence_that_keeps_the_real_filename(
    tmp_path: Path,
) -> None:
    """Round one, mutation 2 (the negated sentence) on its own terms: the
    structural scan only ever looks at the filename token, so a sentence
    that keeps `AGENTS.md` but reverses its meaning is invisible to it by
    design -- that is exactly why `test_agents_md_pointers.py`'s anchored
    sentences stay in the suite rather than being replaced by this scan."""
    mutated = (
        "project's `AGENTS.md` already says exactly where, ask the project "
        "owner and record their answer there\n"
    )
    assert _scan_text(tmp_path, "skills/flow/build/SKILL.md", mutated) == []


def test_catches_the_producing_side_renaming_the_file(tmp_path: Path) -> None:
    """Round one, mutation 3: if `drunken-init` stopped writing `AGENTS.md`
    (renamed here to a file `scaffold.instruction_files` never produces,
    without touching `scaffold.py` itself), every bare mention anywhere in
    scope stops resolving."""
    produced = {"CLAUDE.md"} | {
        p.name for p in (REPO_ROOT / "templates").rglob("*") if p.is_file()
    }
    assert not _resolves("AGENTS.md", produced)


def test_does_not_false_positive_on_the_current_tree(tmp_path: Path) -> None:
    """The real files, scanned for real -- separate from
    `test_every_instruction_file_reference_resolves` only so a failure here
    reads as "the scan itself is wrong", not "a document drifted"."""
    assert scan(tmp_path) == []
