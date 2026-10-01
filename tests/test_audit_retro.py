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

import pytest

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


def _constraints(text: str) -> str:
    return text.split("<constraints>")[1].split("</constraints>")[0]


def _action_sequence(text: str) -> str:
    return text.split("<action_sequence>")[1].split("</action_sequence>")[0]


def _the_retro(text: str) -> str:
    return text.split("<the_retro>")[1].split("</the_retro>")[0]


def _collapsed(text: str) -> str:
    """Markdown wraps prose across lines, so a phrase spanning a line break
    reads with a newline and indent where the sentence has a single space.
    Collapse runs of whitespace before matching a multi-word phrase."""
    return re.sub(r"\s+", " ", text)


#: The five categories a second review named explicitly (DG-418): the first
#: pass's "secrets, personal data and private filesystem paths" left room for
#: a name, a phone number, an internal hostname, or another project's own
#: ticket key or name to slip through unnamed.
SCRUB_CATEGORIES = (
    "secrets and credentials",
    "personal data (names, emails, phone numbers, ids)",
    "home-directory and drive paths",
    "internal hostnames and URLs",
    "ticket keys or names of other projects",
)

#: Anchored on the three words a second review's own mutation test found
#: missing: the first pass's pattern matched "scrub ... secrets ... personal
#: data ... private filesystem path" regardless of whether the sentence said
#: "before" or "after" either was shown or written — changing just that one
#: word left all 15 tests passing. "before", "shown to the Boss" and
#: "written" must appear together, in that order.
BEFORE_SHOWN_WRITTEN_PATTERN = re.compile(
    r"before.{0,120}shown to the Boss.{0,120}written", re.I | re.S
)

#: Targets only the "before" immediately ahead of "shown to the Boss" — not
#: every other "before" in the skill (step 8's "before reporting it as
#: created", for one) — so the mutation test below changes exactly the word
#: the anchor depends on.
_BEFORE_NEAR_SHOWN = re.compile(r"\bbefore\b(?=.{0,120}shown to the Boss)", re.I | re.S)

#: Step 10's hand-off: who writes an approved lesson into `LESSONS.md`, and how.
PULL_REQUEST_PATTERN = re.compile(
    r"approve.{0,60}exact scrubbed text.{0,150}pull request.{0,150}"
    r"never a direct commit.{0,150}never the retro writing it there itself",
    re.I | re.S,
)


def test_the_retro_anchors_the_scrub_on_before_shown_and_written() -> None:
    """DG-418 second review. `scrub ... secrets ... personal data ...
    private filesystem path` alone does not say *when* the scrub happens;
    the sentence must say "before" it is shown to the Boss or written."""
    retro = _collapsed(_the_retro(TEXT))
    assert BEFORE_SHOWN_WRITTEN_PATTERN.search(retro), (
        "the retro step must say the scrub happens before either showing "
        "the lesson to the Boss or writing it to LESSONS.md"
    )
    assert re.search(r"stays local: report it, never propose it", retro, re.I), (
        "a lesson that cannot be stated without private detail must stay "
        "local, never be proposed"
    )


def test_the_constraints_anchor_the_same_scrub_timing() -> None:
    assert BEFORE_SHOWN_WRITTEN_PATTERN.search(_collapsed(_constraints(TEXT))), (
        "<constraints> must carry the same before-shown-written timing, not "
        "just prose in <the_retro>"
    )


#: The constraints' own wording of the stays-local rule — separate from
#: <the_retro>'s "stays local: report it, never propose it" — so a weakened
#: or deleted constraint sentence would otherwise slip past unnoticed: a
#: third review found it had no test at all, and weakening it to "... may be
#: proposed anyway", or deleting it outright, left all 37 tests passing.
STAYS_LOCAL_CONSTRAINT_PATTERN = re.compile(
    r"cannot be stated without one of these.{0,60}reported as local.{0,60}never proposed",
    re.I | re.S,
)

#: The constraint's exact sentence, so the mutation tests below change only
#: this sentence and nothing else in <constraints>.
_STAYS_LOCAL_SENTENCE = (
    "A lesson that cannot be stated without one of these is reported as "
    "local, never proposed."
)


def test_the_constraints_require_an_unstatable_lesson_to_stay_local() -> None:
    """DG-418 third review. The FATAL constraint's own sentence had no
    test: weakening it to '... may be proposed anyway', or deleting it,
    left every other test in this file passing."""
    constraints = _collapsed(_constraints(TEXT))
    assert _STAYS_LOCAL_SENTENCE in constraints, (
        "<constraints> must carry this exact sentence verbatim"
    )
    assert STAYS_LOCAL_CONSTRAINT_PATTERN.search(constraints), (
        "<constraints> must say an unstatable lesson is reported as local "
        "and never proposed"
    )


def test_weakening_the_stays_local_clause_breaks_the_check() -> None:
    """Proves the test above is not a tautology: replacing just 'never
    proposed' with a permissive clause — the exact weakening the third
    review named — must fail the check."""
    constraints = _collapsed(_constraints(TEXT))
    weakened = constraints.replace(
        _STAYS_LOCAL_SENTENCE,
        "A lesson that cannot be stated without one of these may be proposed anyway.",
    )
    assert _STAYS_LOCAL_SENTENCE not in weakened, "the mutation did not apply"
    assert not STAYS_LOCAL_CONSTRAINT_PATTERN.search(weakened)


def test_removing_the_stays_local_sentence_breaks_the_check() -> None:
    """Proves the test above is not a tautology a second way: deleting the
    sentence outright must also fail the check."""
    constraints = _collapsed(_constraints(TEXT))
    removed = constraints.replace(_STAYS_LOCAL_SENTENCE, "")
    assert _STAYS_LOCAL_SENTENCE not in removed, "the mutation did not apply"
    assert not STAYS_LOCAL_CONSTRAINT_PATTERN.search(removed)


@pytest.mark.parametrize("category", SCRUB_CATEGORIES)
def test_each_scrub_category_is_named_in_the_retro(category: str) -> None:
    assert category in _collapsed(_the_retro(TEXT)), (
        f"the retro step must name {category!r} explicitly, not fold it "
        "into a shorter, less specific list"
    )


@pytest.mark.parametrize("category", SCRUB_CATEGORIES)
def test_each_scrub_category_is_named_in_the_constraints(category: str) -> None:
    assert category in _collapsed(_constraints(TEXT)), (
        f"<constraints> must name {category!r} too, matching <the_retro>"
    )


def test_flipping_before_to_after_breaks_the_anchor() -> None:
    """Proves the two anchor tests above are not tautologies: a second
    review found the first pass's pattern still matched after the reviewer
    changed only 'before' to 'after' in a scratch copy, and all 15 tests
    still passed. This one fails unless the mutation does."""
    mutated = _BEFORE_NEAR_SHOWN.sub("after", _collapsed(TEXT))
    assert not BEFORE_SHOWN_WRITTEN_PATTERN.search(_the_retro(mutated))
    assert not BEFORE_SHOWN_WRITTEN_PATTERN.search(_constraints(mutated))


def test_step_10_names_the_pull_request_mechanism() -> None:
    """DG-418 review (MEDIUM). 'the retro never writes it there itself' needs
    a defined next actor: the Boss approves the exact scrubbed text, then a
    human or /build adds it to LESSONS.md in a pull request."""
    assert PULL_REQUEST_PATTERN.search(_collapsed(_action_sequence(TEXT))), (
        "step 10 must name the pull-request mechanism that writes an "
        "approved, scrubbed lesson into LESSONS.md"
    )


def test_removing_the_pull_request_clause_leaves_step_10_silent() -> None:
    stripped = PULL_REQUEST_PATTERN.sub("REMOVED", _collapsed(TEXT))
    assert not PULL_REQUEST_PATTERN.search(_collapsed(_action_sequence(stripped)))


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
