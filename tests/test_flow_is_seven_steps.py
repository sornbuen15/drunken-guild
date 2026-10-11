# mypy: ignore-errors
"""The flow is seven steps, each owning one stage of the standard — DG-386.

REQ-001 asks that the flow run in the order the standard spec-driven sequence
uses, with each stage mapped to one step. Q7 of /clarify added `/replan` as a
step of its own, which made DG-353's "six commands" wrong in every file that
said it. This file holds both halves: the mapping is written down where a reader
looks for the flow (README), and nothing still counts six.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FLOW = REPO / "skills" / "flow"

#: The standard's stages, in order. Each is owned by exactly one step.
STAGES = [
    "requirement",
    "clarify",
    "spec",
    "plan and tasks",
    "implement",
    "validate",
    "replan",
]

#: "six commands", "six flow commands", "six-step flow" and the like.
SIX = re.compile(r"\bsix[ -](flow )?(commands|steps|step flow)\b", re.I)


def _mapping() -> dict[str, str]:
    """The README's stage → step table, as {stage: step}."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*([a-z][a-z ]*?)\s*\|\s*`(/[a-z]+)`\s*\|", text, re.M)
    return dict(rows)


def test_every_stage_maps_to_exactly_one_step() -> None:
    mapping = _mapping()

    assert list(mapping) == STAGES, (
        "README's flow table must list the standard's stages in order, once each"
    )


def test_every_step_maps_to_exactly_one_stage() -> None:
    steps = list(_mapping().values())
    skills = sorted(f"/{p.parent.name}" for p in FLOW.glob("*/SKILL.md"))

    assert sorted(steps) == skills, "every flow skill is a step, and only those"
    assert len(steps) == len(set(steps)), "a step owns one stage, not two"


def test_no_document_still_counts_six_steps() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.md", "*.py", "*.toml"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    here = Path(__file__).name
    found = [
        f"{name}:{n}"
        for name in tracked
        if not name.endswith(here)
        for n, line in enumerate(
            (REPO / name).read_text(encoding="utf-8").splitlines(), 1
        )
        if SIX.search(line)
    ]

    assert not found, f"still says the flow is six steps: {found}"
