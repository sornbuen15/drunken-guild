# mypy: ignore-errors
"""DG-393 follow-up. Review verdict on PR 127: the ten anchored sentences in
`test_agents_md_pointers.py` are a closed list, and DG-393's own ACCEPTANCE
line -- "a check fails a new reference to an instruction file no template or
init step produces" -- is open-ended. Proven by the reviewer planting two new
sentences naming a file nothing produces (`.claude/AGENT_RULES.md`) in a
README paragraph and in `skills/flow/ddd/SKILL.md`; the suite stayed green
both times because nothing scanned either location for an unknown filename.

Round 2 narrowed the scan further, on the same proof-by-planting pattern:

- `.claude/rules/`, `examples/` and `scripts/` were not scanned at all, so a
  bogus pointer planted in `.claude/rules/python.md`,
  `examples/00-setup/PROJECT_BRIEF.md` or `scripts/check_doc_drift.py`
  passed silently. All three are in `_scan_files()` now.
- The path-ish branch of the old `_resolves()` accepted "a file exists
  anywhere in the repository" as proof, which a stray
  `tests/fixtures/stray/CLAUDE.md` plus a README link to it exploited --
  nothing produces a project's instruction file there, but the file was
  real, so it resolved. Only the project root, `templates/`,
  `src/core/templates/` and this repository's own root are accepted now;
  everywhere else fails even when the path is real.
- Matching was case-sensitive, so `agents.md` or `Agent_Rules.md` were
  invisible to the scan -- not flagged as unresolved, not recognised as
  references at all. The token pattern and every comparison are
  case-insensitive now.
- A stray space before the extension (`AGENTS .md`) is tolerated on the
  single-word names and the `_RULES` family -- checked against the real
  tree to confirm it does not introduce a false positive (it does not: see
  `test_does_not_false_positive_on_the_current_tree`).
- `COPILOT.md`, `.windsurfrules`, `.github/copilot-instructions.md` and
  `INSTRUCTIONS.md` are recognised names now, alongside AGENTS/CLAUDE/GEMINI
  -- none of them is produced by anything, so any reference to one fails
  unless a future template or init step starts producing it.

Round 3 found the location check itself could be walked around: it tested
`_ALLOWED_PREFIXES` with a plain string `startswith` *before* `..` was ever
resolved, then let `Path.is_file()` walk straight out through it -- a token
like `templates/../tests/fixtures/stray/CLAUDE.md` starts with `templates/`
textually, so it passed the prefix check, and then resolved against a real
file sitting outside every accepted location. `_resolves()` now collapses
`.`/`..` with `posixpath.normpath` before any prefix is trusted, rejects
whatever still climbs out of the repository after that, rejects an absolute
path outright, and -- belt and braces -- checks the fully resolved
`Path` is still inside an allowed directory before ever calling
`is_file()`.

This module finds the reference *structurally*, instead of listing the
sentences that currently make one: any path-ish token ending in a name that
looks like a per-agent instruction file, found anywhere across the tracked
docs and skills: README, GETTING_STARTED, `templates/`, every
`skills/**/SKILL.md`, `agents/`, `.claude/rules/`, `examples/`, `scripts/`,
the jira-mcp project-id error text, and this repo's own root AGENTS.md.

A bare token (no path separator) is valid when it names a file
`scaffold.instruction_files` actually writes at a project's root, or the
basename of a file genuinely shipped under `templates/` -- both read back
from disk rather than hand-copied here, so a rename on either producing side
fails this test too. A path-ish token is valid only when it both resolves to
a real tracked file *and* sits under one of the four accepted locations --
that is the "exists and is read" half of the check, and it is why a stray
file placed anywhere else fails even though the file itself is real.

What is left over after both of those -- an illustrative example path, or a
comment naming a path precisely because it does *not* exist -- is what the
explicit ALLOWLIST below carries, each entry with its reason.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from core import scaffold

REPO_ROOT = Path(__file__).resolve().parent.parent

#: What counts, structurally, as "a reference to an instruction file": a run
#: of path characters ending in one of these names, matched without regard
#: to case. A single optional space before the extension is tolerated on
#: the single-word names and the `_RULES` family only -- not on the
#: dotfiles or the compound `copilot-instructions.md`, where it was never
#: asked for and would only add risk.
_CORE = (
    r"(?:AGENTS\s?\.md|CLAUDE\s?\.md|GEMINI\s?\.md|COPILOT\s?\.md|INSTRUCTIONS\s?\.md"
    r"|[A-Za-z][A-Za-z0-9_]*_RULES\s?\.md"
    r"|\.cursorrules|\.aider\.conf\.yml|\.windsurfrules"
    r"|copilot-instructions\.md)"
)
_TOKEN = re.compile(r"[\w./\\~-]*" + _CORE, re.IGNORECASE)

#: The only directory prefixes a path-ish reference is accepted under, case
#: folded. Not "anywhere a file happens to exist" -- a stray file dropped
#: somewhere else and pointed at is exactly the finding this list exists to
#: shut out.
_ALLOWED_PREFIXES = ("templates/", "src/core/templates/")

#: (file relative to REPO_ROOT, exact token as it appears in the source) ->
#: why this one is not expected to resolve, even though it matches the
#: pattern above.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("GETTING_STARTED.md", "~/Projects/my-project/CLAUDE.md"): (
        "the cp walkthrough's own illustrative target under the reader's "
        "home directory, not a path in this repository"
    ),
    ("scripts/check_doc_drift.py", "templates/AGENTS.md"): (
        "a comment explaining why this name is deliberately absent from "
        "the retired-name list below it, not a live pointer -- the file "
        "has never existed at that path"
    ),
    ("scripts/check_doc_drift.py", ".agents/AGENTS.md"): (
        "the retired path itself, recorded inside a Retired(...) entry -- "
        "the same job RETIRED.md does, naming the gone thing on purpose"
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
    files += sorted(
        p for p in (REPO_ROOT / ".claude" / "rules").rglob("*") if p.is_file()
    )
    files += sorted(p for p in (REPO_ROOT / "examples").rglob("*") if p.is_file())
    files += sorted(p for p in (REPO_ROOT / "scripts").rglob("*") if p.is_file())
    return files


def _produced_filenames(tmp_path: Path) -> set[str]:
    """Every bare filename a reference to an instruction file is allowed to
    name, lower-cased for case-insensitive comparison: what `drunken-init`
    writes at a project's root, run for real against a scratch directory,
    plus the basename of every file actually shipped under `templates/` --
    both read back from disk, not restated."""
    scaffold.instruction_files(tmp_path, "demo-project", None)
    produced = {entry.name.lower() for entry in tmp_path.iterdir() if entry.is_file()}
    produced |= {
        p.name.lower() for p in (REPO_ROOT / "templates").rglob("*") if p.is_file()
    }
    return produced


def _despace(token: str) -> str:
    """Collapse the one stray-space variant the pattern allows, so
    resolution compares the same name the pattern recognised."""
    return re.sub(r"\s+", "", token)


def _resolves(token: str, produced: set[str]) -> bool:
    token = _despace(token)
    if "/" not in token and "\\" not in token:
        return token.lower() in produced

    normalized = token.replace("\\", "/")
    if normalized.startswith("~/"):
        # Never a repository-relative path -- the reader's own home
        # directory. Only reached for a token not already in ALLOWLIST.
        return False
    if normalized.startswith("/"):
        # An absolute path is never a location drunken-init or a template
        # writes at. Round 1 used to treat a leading "/" as repo-root --
        # dropped rather than kept, since round 3 needs every path-ish
        # token to go through the same ".." check below, and "absolute" is
        # not a shape that check should have to reason about at all.
        return False
    if normalized.startswith("./"):
        normalized = normalized[2:]

    if "/" not in normalized:
        return normalized.lower() in produced

    # Collapse `.`/`..` segments *before* anything is trusted about the
    # path's shape -- `_ALLOWED_PREFIXES` is a textual prefix check, and
    # `templates/../tests/fixtures/x` starts with `templates/` right up
    # until normalisation says it actually means `tests/fixtures/x`. A
    # token that still climbs above the repo root after collapsing, or
    # that collapses to a bare name, is handled the same way a token
    # written that way from the start would be.
    collapsed = posixpath.normpath(normalized)
    if collapsed == "." or collapsed == ".." or collapsed.startswith("../"):
        return False
    if "/" not in collapsed:
        return collapsed.lower() in produced

    if not collapsed.lower().startswith(_ALLOWED_PREFIXES):
        # Real or not, a path outside the project root, templates/ and
        # src/core/templates/ is not a location drunken-init or a template
        # conventionally produces an instruction file at -- a stray file
        # placed and linked anywhere else does not get to count.
        return False

    candidate = (REPO_ROOT / collapsed).resolve()
    allowed_roots = [(REPO_ROOT / prefix).resolve() for prefix in _ALLOWED_PREFIXES]
    if not any(_is_within(candidate, root) for root in allowed_roots):
        # Belt and braces alongside the textual check above: a symlink or
        # another filesystem-level trick that `posixpath.normpath` cannot
        # see does not get to resolve either.
        return False
    return candidate.is_file()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


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
                    "real file in a conventional location in this repository"
                )
    return problems


def test_every_instruction_file_reference_resolves(tmp_path: Path) -> None:
    problems = scan(tmp_path)
    assert problems == [], "\n".join(problems)


def test_scan_covers_more_than_a_handful_of_files() -> None:
    """A scope this narrow could pass by accident; pin a floor so a future
    refactor that empties `_scan_files()` is caught here too."""
    assert len(_scan_files()) >= 20


# --- Proof the scan actually fires, on the reviewer's mutations across both
# rounds of this ticket. Each is applied to a scratch copy of the real
# file's text (never written back to the tracked file), run through the
# same `scan()` used above, and shown to report exactly the planted line --
# then nothing on disk is touched, so there is nothing to revert. The report
# on this PR separately shows the same findings on the real tracked files,
# mutated and reverted with `git checkout --`.


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
    """DG-393 PR 127 review round 1: a new README paragraph naming
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
    """Round 1, mutation 1: a real filename, a retired directory in front
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
    """Round 1, mutation 2 (the negated sentence) on its own terms: the
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
    """Round 1, mutation 3: if `drunken-init` stopped writing `AGENTS.md`
    (renamed here to a file `scaffold.instruction_files` never produces,
    without touching `scaffold.py` itself), every bare mention anywhere in
    scope stops resolving."""
    produced = {"claude.md"} | {
        p.name.lower() for p in (REPO_ROOT / "templates").rglob("*") if p.is_file()
    }
    assert not _resolves("AGENTS.md", produced)


def test_catches_a_bogus_pointer_in_claude_rules(tmp_path: Path) -> None:
    """Round 2, finding 1: `.claude/rules/` was not scanned at all."""
    mutated = "Also see `.claude/rules/GEMINI_RULES.md` for the vendor-specific list.\n"
    problems = _scan_text(tmp_path, ".claude/rules/python.md", mutated)
    assert problems == [
        ".claude/rules/python.md:1: references '.claude/rules/GEMINI_RULES.md'",
    ]


def test_catches_a_bogus_pointer_in_examples(tmp_path: Path) -> None:
    """Round 2, finding 1: `examples/` was not scanned at all."""
    mutated = "| Instruction file | `examples/00-setup/CLAUDE.md` |\n"
    problems = _scan_text(tmp_path, "examples/00-setup/PROJECT_BRIEF.md", mutated)
    assert problems == [
        "examples/00-setup/PROJECT_BRIEF.md:1: references "
        "'examples/00-setup/CLAUDE.md'",
    ]


def test_catches_a_bogus_pointer_in_scripts(tmp_path: Path) -> None:
    """Round 2, finding 1: `scripts/` was not scanned at all."""
    mutated = "    # See .scripts/AGENTS.md for the generated rulebook.\n"
    problems = _scan_text(tmp_path, "scripts/check_doc_drift.py", mutated)
    assert problems == [
        "scripts/check_doc_drift.py:1: references '.scripts/AGENTS.md'",
    ]


def test_does_not_accept_a_stray_file_outside_the_conventional_locations(
    tmp_path: Path,
) -> None:
    """Round 2, finding 2: a real file is not proof on its own. A stray
    `tests/fixtures/stray/CLAUDE.md` is created for real under *tmp_path*
    (never under the repository), and a reference to it by that same
    repo-relative-looking path must still fail -- `tests/fixtures/` is not
    the project root, `templates/` or `src/core/templates/`."""
    stray = tmp_path / "tests" / "fixtures" / "stray"
    stray.mkdir(parents=True)
    (stray / "CLAUDE.md").write_text("not a real adapter\n", encoding="utf-8")

    # Prove the file really exists, so the failure below is the location
    # rule firing and not a typo in the path.
    assert (stray / "CLAUDE.md").is_file()

    mutated = "See `tests/fixtures/stray/CLAUDE.md` for an example adapter.\n"
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [
        "README.md:1: references 'tests/fixtures/stray/CLAUDE.md'",
    ]


#: A real, permanent, tracked file sitting outside every accepted location
#: (`tests/fixtures/` is not in `_scan_files()`, so it is never itself
#: scanned as a live reference). Round 3's bug let a `templates/../...`
#: token resolve against a real file exactly like this one; proving the fix
#: needs a real target at the far end of the traversal, not a path that
#: merely fails to exist, which the pre-round-3 code would also have
#: rejected -- for the wrong reason.
_REAL_STRAY_FILE = REPO_ROOT / "tests" / "fixtures" / "stray" / "CLAUDE.md"


def test_the_traversal_fixture_is_real() -> None:
    """Guards the proof below: if this ever stops being true, the next test
    would pass for the wrong reason -- nothing at the target, not the
    traversal being rejected."""
    assert _REAL_STRAY_FILE.is_file()


def test_rejects_the_reviewers_traversal_past_templates(tmp_path: Path) -> None:
    """Round 3: `_ALLOWED_PREFIXES` used to be checked with a plain string
    `startswith` before `..` was resolved, so `templates/../tests/fixtures/
    stray/CLAUDE.md` passed the prefix check textually and then resolved
    against the real file above, which sits outside every accepted
    location. Checked two ways: `_resolves()` directly, against the file
    that is actually there, and through the full scan with a planted
    reference, which must report the exact file and line."""
    produced = _produced_filenames(tmp_path)
    token = "templates/../tests/fixtures/stray/CLAUDE.md"
    assert not _resolves(token, produced), (
        "the traversal resolved -- it walked out of templates/ to a real "
        "file outside every accepted location"
    )

    mutated = f"See `{token}` for an example adapter.\n"
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [f"README.md:1: references {token!r}"]


def test_rejects_a_templates_path_that_does_not_exist(tmp_path: Path) -> None:
    """Round 3 proof 2: being inside `templates/` is necessary, not
    sufficient -- the file still has to be real. Confirms the `.is_file()`
    call survived the rewrite of `_resolves()`'s path-ish branch."""
    produced = _produced_filenames(tmp_path)
    token = "templates/NOPE_RULES.md"
    assert not (REPO_ROOT / "templates" / "NOPE_RULES.md").exists(), (
        "test fixture assumption broken: this file exists for real"
    )
    assert not _resolves(token, produced)

    mutated = f"See `{token}` for an example adapter.\n"
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [f"README.md:1: references {token!r}"]


def test_rejects_a_dot_slash_name_that_exists_nowhere(tmp_path: Path) -> None:
    """Round 3 proof 3: `./` stripped down to a bare name still has to
    resolve against something `drunken-init` or a template actually
    produces -- stripping the prefix is not itself a pass. `INSTRUCTIONS.md`
    matches the recognised-name pattern (round 2) but nothing produces it,
    so this is also a second, independent proof that the recognised-but-
    unproduced vendor names stay rejected once a `./` prefix is involved."""
    produced = _produced_filenames(tmp_path)
    token = "./INSTRUCTIONS.md"
    assert "instructions.md" not in produced
    assert not _resolves(token, produced)

    mutated = f"See `{token}` for an example adapter.\n"
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [f"README.md:1: references {token!r}"]


def test_catches_a_lowercase_bogus_filename(tmp_path: Path) -> None:
    """Round 2, finding 3: matching is case-insensitive, so a reference
    spelled in lower case is still found -- and still has to resolve."""
    mutated = "Project rules also live in `agent_rules.md`, kept in sync by hand.\n"
    problems = _scan_text(tmp_path, "README.md", mutated)
    assert problems == [
        "README.md:1: references 'agent_rules.md'",
    ]


def test_lowercase_reference_to_the_real_file_is_not_a_false_positive(
    tmp_path: Path,
) -> None:
    """Same case-insensitivity, the other direction: `agents.md` in lower
    case still names the real file `drunken-init` writes, so it must not be
    flagged."""
    mutated = "see agents.md for the project's own rules\n"
    assert _scan_text(tmp_path, "README.md", mutated) == []


def test_tolerates_a_stray_space_before_the_extension(tmp_path: Path) -> None:
    """Round 2, finding 4 (the space variant): still has to resolve
    normally once the space is folded out -- a space does not excuse a
    bogus filename either."""
    assert _scan_text(tmp_path, "README.md", "see `AGENTS .md` for the map\n") == []
    problems = _scan_text(tmp_path, "README.md", "see `AGENT_RULES .md` instead\n")
    assert problems == ["README.md:1: references 'AGENT_RULES .md'"]


def test_catches_each_new_vendor_name(tmp_path: Path) -> None:
    """Round 2, finding 5: four more vendor names are recognised, and none
    of them is produced by anything yet, so each one still fails."""
    cases = {
        "see `COPILOT.md` for Copilot-specific rules\n": "COPILOT.md",
        "Windsurf reads `.windsurfrules`\n": ".windsurfrules",
        "GitHub Copilot reads `.github/copilot-instructions.md`\n": (
            ".github/copilot-instructions.md"
        ),
        "the full rulebook lives in `INSTRUCTIONS.md`\n": "INSTRUCTIONS.md",
    }
    for text, token in cases.items():
        problems = _scan_text(tmp_path, "README.md", text)
        assert problems == [f"README.md:1: references {token!r}"], (text, problems)


def test_does_not_false_positive_on_the_current_tree(tmp_path: Path) -> None:
    """The real files, scanned for real -- separate from
    `test_every_instruction_file_reference_resolves` only so a failure here
    reads as "the scan itself is wrong", not "a document drifted"."""
    assert scan(tmp_path) == []
