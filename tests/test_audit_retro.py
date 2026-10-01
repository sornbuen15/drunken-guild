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


def test_lessons_sources_come_from_project_docs() -> None:
    assert "project-docs" in TEXT.split("<the_retro>")[1].split("</the_retro>")[0], (
        "the retro step must ask project-docs where lessons live, not guess a path"
    )


def test_retro_no_longer_stops_on_a_missing_source() -> None:
    """DG-418. project-docs now always names a lessons location
    (`.ai/LESSONS.md` by default), so the retro step no longer describes
    stopping because none was named."""
    retro = TEXT.split("<the_retro>")[1].split("</the_retro>")[0]
    assert "LESSONS.md" in retro, (
        "the retro step must read the lessons file project-docs names"
    )
    assert "does not name a lessons source" not in retro, (
        "the old stop-on-missing-source wording must be gone now that "
        "project-docs always names a default"
    )


def test_retro_may_read_its_own_memory_never_anothers() -> None:
    """DG-418 (Boss decision, 2026-10-01). An agent's own memory is its
    scratch space: the retro may read its own when it exists, and promotes
    lessons with evidence into LESSONS.md as a proposal — it never reads
    another agent's private state."""
    retro = TEXT.split("<the_retro>")[1].split("</the_retro>")[0]
    assert re.search(r"own memory", retro, re.I)
    assert re.search(r"never read another agent", retro, re.I)


def test_skill_body_stays_under_the_500_line_budget() -> None:
    lines = TEXT.splitlines()
    assert len(lines) < 500, (
        f"{SKILL} is {len(lines)} lines; .claude/rules/ai-layer.md caps the body at 500"
    )


#: The classify sentence itself, read out of `<the_retro>` rather than
#: restated here — so editing the skill's own wording changes what a lesson
#: must say to be proposed.
CLASSIFY_RULE = re.compile(
    r"Evidence of a repeatable rule — (.*?) — is guild-wide:", re.S
)
_STRIP_PREFIX = re.compile(
    r"^(stated as holding |stated as |the boss saying it applies to )", re.I
)


def _markers_from_skill(text: str) -> tuple[str, ...]:
    """The guild-wide markers `<the_retro>` actually names, extracted from its
    prose. Empty if the classify sentence is not there to read."""
    match = CLASSIFY_RULE.search(text)
    if not match:
        return ()
    clause = re.sub(r"\s+", " ", match.group(1))
    markers = []
    for phrase in re.split(r",| or ", clause):
        phrase = _STRIP_PREFIX.sub("", phrase.strip().strip(",")).strip()
        if len(phrase.split()) >= 2:
            markers.append(phrase.lower())
    return tuple(markers)


def _classify(lesson: str, markers: tuple[str, ...]) -> str:
    return (
        "guild-wide" if any(marker in lesson.lower() for marker in markers) else "local"
    )


#: The fixture the acceptance criterion names: one lesson that is evidence of
#: a repeatable rule — in the skill's own words — one that is a fact about
#: this project alone.
FIXTURE_LESSONS = [
    "Verify a PR's headRefOid after every push — the Boss said this holds "
    "beyond this project, not just the one it was found in.",
    "This project's own dev server always starts on :4173 — a fact about its "
    "own vite.config and nothing past it.",
]


def test_markers_are_actually_parsed_out_of_the_skill_text() -> None:
    assert _markers_from_skill(TEXT), (
        "no guild-wide markers could be read out of <the_retro> — the extractor "
        "is out of sync with the skill's own prose"
    )


def test_fixture_with_one_guild_wide_and_one_local_lesson_yields_one_proposal() -> None:
    markers = _markers_from_skill(TEXT)
    proposals = [
        lesson
        for lesson in FIXTURE_LESSONS
        if _classify(lesson, markers) == "guild-wide"
    ]
    assert len(proposals) == 1, (
        "a fixture lessons file with one guild-wide lesson and one local one "
        "must produce exactly one proposal (DG-409 acceptance)"
    )


def test_removing_the_classify_rule_leaves_nothing_to_propose() -> None:
    """Proves the test above is not a tautology: strip the classify sentence
    from a scratch copy of the text and the same fixture now proposes
    nothing, because there are no markers left to read."""
    stripped = CLASSIFY_RULE.sub("REMOVED", TEXT)
    markers = _markers_from_skill(stripped)
    assert markers == (), "the classify sentence should leave no markers once removed"
    proposals = [
        lesson
        for lesson in FIXTURE_LESSONS
        if _classify(lesson, markers) == "guild-wide"
    ]
    assert proposals == [], "with the classify rule gone, nothing can be guild-wide"
