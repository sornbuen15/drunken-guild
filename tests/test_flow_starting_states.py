# mypy: ignore-errors
"""Every flow step says what it does in each state a project can be in — DG-495, REQ-024.

REQ-024: a step runs in a project whatever it finds, without asking the Boss whether the step may
be skipped, and finishes fast when it has nothing to change. Found 2026-10-09: every flow skill but
``/prd`` stopped at "no PRD.md"; ``/ddd`` forbade reading a codebase; ``/breakdown`` never searched
before creating. This is the one place the five states are written down; a skill that does not name
all five, each with a behaviour, fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FLOW = REPO / "skills" / "flow"
SKILLS = sorted(p.name for p in FLOW.iterdir() if (p / "SKILL.md").is_file())

#: The five starting states, as the bold label each skill writes in its ``<starting_states>`` block.
STATES = (
    "New folder",
    "Code, no PRD",
    "Requirements in another shape",
    "Existing backlog",
    "One task or bug",
)

#: A refusal to run. A state's line may say what is *absent*, but never tell the step to stop.
REFUSAL = re.compile(
    r"\b(stop and point|stop,|must stop|cannot run|refuse to run)\b", re.I
)
#: Asking permission to skip is exactly what REQ-024 rules out.
SKIP_ASK = re.compile(r"\b(ask|asks|asking)\b[^.\n]{0,60}\b(skip|skipped)\b", re.I)


def _block(skill: str) -> str:
    text = (FLOW / skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"<starting_states>(.*?)</starting_states>", text, re.S)
    assert m, f"skills/flow/{skill}/SKILL.md has no <starting_states> block (REQ-024)"
    return m.group(1)


def _lines(skill: str) -> dict[str, str]:
    """{state label: the text after it}, a state's text running to the next label."""
    block = _block(skill)
    found: dict[str, str] = {}
    labels = [(s, block.find(f"**{s}**")) for s in STATES]
    present = sorted((i, s) for s, i in labels if i >= 0)
    for n, (i, s) in enumerate(present):
        end = present[n + 1][0] if n + 1 < len(present) else len(block)
        found[s] = block[i + len(s) + 4 : end].strip()
    return found


def test_the_flow_has_seven_skills() -> None:
    assert len(SKILLS) == 7, f"expected the seven flow skills, found {SKILLS}"


@pytest.mark.parametrize("skill", SKILLS)
def test_every_skill_names_all_five_states(skill: str) -> None:
    got = _lines(skill)

    assert list(got) == list(STATES), (
        f"{skill}: must name, in order, exactly {list(STATES)}; found {list(got)}"
    )


@pytest.mark.parametrize("skill", SKILLS)
def test_every_state_says_what_the_step_does(skill: str) -> None:
    for state, text in _lines(skill).items():
        words = len(re.sub(r"[^\w]+", " ", text).split())
        assert words >= 8, (
            f"{skill} / {state}: a state needs a behaviour, got {words} words"
        )


@pytest.mark.parametrize("skill", SKILLS)
def test_no_state_refuses_to_run_or_asks_to_skip(skill: str) -> None:
    for state, text in _lines(skill).items():
        assert not REFUSAL.search(text), (
            f"{skill} / {state}: a state may not stop the step"
        )
        assert not SKIP_ASK.search(text), (
            f"{skill} / {state}: never ask whether to skip a step"
        )


def test_the_guard_can_fail_on_a_missing_state() -> None:
    """The check itself: one state removed from a real block must read as missing."""
    block = _block("prd")
    mutated = block.replace("**One task or bug**", "**Something else**")

    assert "**One task or bug**" not in mutated
    assert list(_lines_of(mutated)) != list(STATES)


def _lines_of(block: str) -> dict[str, str]:
    present = sorted((block.find(f"**{s}**"), s) for s in STATES if f"**{s}**" in block)
    return {s: "" for _, s in present}


@pytest.mark.parametrize("skill", SKILLS)
def test_every_skill_ends_by_naming_its_next_step(skill: str) -> None:
    """REQ-012 / DG-387: the output format of each flow skill carries a ``Next:`` line."""
    text = (FLOW / skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"<output_format>(.*?)</output_format>", text, re.S)
    assert m, f"{skill}: no <output_format> block"

    assert re.search(r"\bNext:", m.group(1)), (
        f"{skill}: output format never names the next step"
    )
