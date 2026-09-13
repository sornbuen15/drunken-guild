# mypy: ignore-errors
"""What is paid for on every turn, and what is scoped to where it applies — DG-360.

`CLAUDE.md` is loaded into every session, on every turn, before anything else.
Claude Code's own documentation targets **under 200 lines per file** and says a
longer one both consumes more context and *reduces adherence* — which is the
symptom rather than the cost: clearly written rules followed inconsistently.

This file measures that, because a budget nobody measures is a budget that only
grows. It was 350 lines when this was written.

The mechanism that makes shrinking possible without losing a rule is
`.claude/rules/*.md`: a rule file carrying `paths:` frontmatter loads **only when
Claude reads a file matching the pattern**, so instructions for the AI layer cost
nothing while working in `src/`, and vice versa. A rule file *without* `paths:`
loads unconditionally — same as CLAUDE.md — so it saves nothing and belongs in
CLAUDE.md instead, where a reader can find it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Claude Code's documented target for a single instruction file.
CLAUDE_MD_LINE_TARGET = 200

RULES_DIR = REPO_ROOT / ".claude" / "rules"


def rule_files() -> list[Path]:
    return sorted(RULES_DIR.rglob("*.md")) if RULES_DIR.is_dir() else []


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return match.group(1) if match else ""


class TestTheAlwaysOnBudget:
    def test_claude_md_is_under_the_documented_target(self) -> None:
        """Not a style preference: the documentation ties length to adherence.

        If this fails, the fix is not to delete a rule. It is to move the ones
        that only matter for part of the tree into `.claude/rules/` with
        `paths:`, where they load when they are relevant and cost nothing when
        they are not.
        """
        lines = len((REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines())
        assert lines < CLAUDE_MD_LINE_TARGET, (
            f"CLAUDE.md is {lines} lines against a target of "
            f"{CLAUDE_MD_LINE_TARGET}. Longer files consume more context on "
            "every turn and reduce adherence — move a path-specific section to "
            ".claude/rules/, do not delete a rule to fit."
        )

    def test_there_is_at_least_one_path_scoped_rule(self) -> None:
        """Guards the guard. With no rules files the test above can be satisfied
        by deleting content, which is the opposite of the intent."""
        assert rule_files(), (
            "No .claude/rules/*.md exists, so nothing was scoped — CLAUDE.md "
            "being short would mean rules were dropped rather than moved."
        )


class TestEveryRuleIsScopedOrBelongsInClaudeMd:
    def test_each_rule_declares_paths(self) -> None:
        """A rule without `paths:` loads on every turn exactly like CLAUDE.md,
        so putting one here buys nothing and costs a reader the second place to
        look. If a rule really must always apply, it belongs in CLAUDE.md."""
        unscoped = [
            path.relative_to(REPO_ROOT)
            for path in rule_files()
            if "paths:" not in frontmatter(path)
        ]
        assert not unscoped, (
            f"{unscoped} carry no `paths:` frontmatter, so they load "
            "unconditionally — the same cost as CLAUDE.md, in a file nobody "
            "thinks to read. Scope them, or move them into CLAUDE.md."
        )

    @pytest.mark.parametrize("required", ["skills/", "src/"])
    def test_the_two_halves_are_both_covered(self, required: str) -> None:
        """This repository is two deliverables. Each half's rules should reach a
        session working in that half, which means some rule's `paths:` has to
        name it."""
        declared = " ".join(frontmatter(path) for path in rule_files())
        assert required in declared, (
            f"No rule's `paths:` mentions {required!r}, so a session working "
            "there loads none of its rules."
        )


class TestTheDriftCheckSeesTheRules:
    def test_rules_are_scanned_for_retired_names(self) -> None:
        """`.claude` is in the drift check's skip list, because linked worktrees
        live under it and hold whole copies of the repo at older commits. Rules
        are instructions, not history: an instruction naming something retired is
        the exact bug that check exists for, so it must be scanned even though
        its parent directory is skipped."""
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import check_doc_drift as drift

        scanned = {path.resolve() for path in drift.documents()}
        missing = [
            path.relative_to(REPO_ROOT)
            for path in rule_files()
            if path.resolve() not in scanned
        ]
        assert not missing, (
            f"{missing} are instruction files the drift check never reads, so a "
            "retired name could sit in them indefinitely."
        )
