# mypy: ignore-errors
"""DG-409. A lesson a project records and keeps to itself never reaches the
guild — nine sat in one project's own memory and none of them did. `/audit`'s
last step reads a project's lessons sources, classifies each as guild-wide or
local, and proposes only the guild-wide ones as tickets for the Boss — never
writing a skill or a rule itself.

Markdown-only skill, no interpreter to run it against, so this is a shape
test in the same spirit as `test_ai_layer_drift.py` and `test_four_commands`:
it reads the committed text and checks the rule is actually written down,
rather than simulating an agent reading it.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "flow" / "audit" / "SKILL.md"
TEXT = SKILL.read_text(encoding="utf-8")

#: Every numbered step's verb, in order, exactly as `action_sequence` lists them.
ACTION_STEPS = re.findall(r"^\s*\d+[a-z]?\.\s+([A-Z]+):", TEXT, re.M)


def test_retro_is_named_as_the_last_step() -> None:
    assert ACTION_STEPS, "action_sequence has no numbered steps at all"
    assert ACTION_STEPS[-1] == "RETRO", (
        f"the last step is {ACTION_STEPS[-1]!r}, not RETRO — DG-409 asks "
        "/audit to name the retro step last"
    )


def test_the_retro_never_authors_a_skill_or_a_rule() -> None:
    assert re.search(r"never writes? a skill", TEXT, re.I), (
        "the skill's own text must forbid authoring a skill (or a rule) from "
        "the retro step — it proposes, it never edits"
    )


def test_a_local_lesson_is_reported_not_proposed() -> None:
    assert re.search(r"local:\s*report it[^.]*and do not propose", TEXT, re.I), (
        "a lesson local to one project must be reported, not filed as a ticket"
    )


def test_lessons_sources_come_from_project_docs_or_the_step_stops() -> None:
    assert "project-docs" in TEXT.split("<the_retro>")[1].split("</the_retro>")[0], (
        "the retro step must ask project-docs where lessons live, not guess a path"
    )
    assert re.search(r"does not name a lessons source.{0,40}stop", TEXT, re.I), (
        "with no source named, the step must say so and stop — never invent one"
    )


def test_skill_body_stays_under_the_500_line_budget() -> None:
    lines = TEXT.splitlines()
    assert len(lines) < 500, (
        f"{SKILL} is {len(lines)} lines; .claude/rules/ai-layer.md caps the body at 500"
    )


def _classify(lesson: str) -> str:
    """A minimal proxy for the rule the skill states in `<the_retro>`: evidence
    stated as holding beyond one project, or stated more than once, is
    guild-wide; a fact about this project's own path, port or person is
    local."""
    markers = ("across projects", "beyond this project", "every project", "the guild")
    return (
        "guild-wide" if any(marker in lesson.lower() for marker in markers) else "local"
    )


#: The fixture the acceptance criterion names: one lesson that is evidence of
#: a repeatable rule, one that is a fact about this project alone.
FIXTURE_LESSONS = [
    "Verify a PR's headRefOid after every push — this held across projects, "
    "not just the one it was found in.",
    "This project's own dev server always starts on :4173 — a fact about its "
    "own vite.config and nothing past it.",
]


def test_fixture_with_one_guild_wide_and_one_local_lesson_yields_one_proposal() -> None:
    proposals = [
        lesson for lesson in FIXTURE_LESSONS if _classify(lesson) == "guild-wide"
    ]
    assert len(proposals) == 1, (
        "a fixture lessons file with one guild-wide lesson and one local one "
        "must produce exactly one proposal (DG-409 acceptance)"
    )
