# mypy: ignore-errors
"""Every skill description says when to use it, in words a person says — DG-395.

REQ-010. Claude Code, Antigravity and Gemini CLI choose a skill from its
description alone, and Aider is to get the same text as a preloaded index
(DG-404). A description that says what a skill *is* but not when it applies
leaves the agent to guess, which is the failure REQ-002 names: the rules are
followed, but nothing says when to reach for them.

Two shapes are held here. The description opens with the situation — the index
cuts each one at 160 characters (`_truncate.py 160`), and the "Apply when…"
sentence used to sit past the cut. And it quotes at least one plain request, the
way a person would say it, with no two skills claiming the same one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / "skills"

#: What the generated index keeps of each description.
INDEX_CUT = 160

#: A quoted request of at least three words: "help me write down what we're building".
REQUEST = re.compile(r'"([^"]+?\s[^"]+?\s[^"]+?)"')


def _description(skill: Path) -> str:
    text = skill.read_text(encoding="utf-8")
    fm = text.split("---", 2)[1]
    folded = re.search(r"^description:\s*[>|]\s*\n((?:[ \t]+.*\n?)+)", fm, re.M)
    if folded:
        return " ".join(line.strip() for line in folded.group(1).splitlines())
    one_line = re.search(r"^description:\s*(.+)$", fm, re.M)
    assert one_line, f"{skill} has no description"
    return one_line.group(1).strip().strip('"')


def _skills() -> list[Path]:
    return sorted(SKILLS.glob("*/*/SKILL.md"))


def test_the_skills_are_found() -> None:
    """Guards the guard: an empty glob would pass every test below."""
    assert len(_skills()) >= 12


@pytest.mark.parametrize("skill", _skills(), ids=lambda p: p.parent.name)
def test_the_description_opens_with_the_situation(skill: Path) -> None:
    head = _description(skill)[:INDEX_CUT]

    assert head.startswith("Use when "), (
        f"{skill.parent.name}: the index keeps {INDEX_CUT} characters, and they "
        f"must say when to use the skill. They say: {head!r}"
    )


@pytest.mark.parametrize("skill", _skills(), ids=lambda p: p.parent.name)
def test_the_description_quotes_a_plain_request(skill: Path) -> None:
    assert REQUEST.search(_description(skill)), (
        f"{skill.parent.name}: quote at least one request as a person would "
        'say it, e.g. "help me write down what we\'re building".'
    )


def test_no_two_skills_claim_the_same_request() -> None:
    claimed: dict[str, str] = {}
    clashes = []
    for skill in _skills():
        for request in REQUEST.findall(_description(skill)):
            key = " ".join(request.lower().split())
            if key in claimed:
                clashes.append(f"{request!r}: {claimed[key]} and {skill.parent.name}")
            claimed[key] = skill.parent.name

    assert not clashes, clashes
