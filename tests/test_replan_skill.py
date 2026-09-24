# mypy: ignore-errors
"""DG-389. `/replan` is a step of its own (REQ-004).

When a requirement is added, cut or changed after `/breakdown`, the plan has to
follow: the PRD first, by `/prd`'s rules, then the tickets that trace to it. The
Boss dropped `/refine` (REQ-005) because ordering work is theirs, so the one
thing this step must never do is decide what comes first.

A skill is prose, so these tests read it. They pin what the ticket's acceptance
needs to be *said*: shown before written, ids never renumbered or reused, and no
ordering — and that it is published in the index an agent reads.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "flow" / "replan" / "SKILL.md"
INDEX = ROOT / "skills" / "INDEX.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _frontmatter() -> str:
    return _text().split("---", 2)[1]


def test_the_skill_exists_in_the_flow() -> None:
    assert SKILL.is_file(), f"{SKILL} is missing"


def test_it_is_triggered_by_its_own_command() -> None:
    fm = _frontmatter()
    assert re.search(r"^name: replan$", fm, re.MULTILINE)
    assert "Trigger on /replan" in fm


def test_the_description_names_when_to_use_it() -> None:
    """REQ-010: an agent chooses from the description alone."""
    fm = _frontmatter().lower()
    for situation in ("added", "cut", "changed"):
        assert situation in fm, f"description does not say a requirement {situation}"


def test_nothing_is_written_before_the_boss_sees_it() -> None:
    text = _text()
    assert re.search(r'priority="FATAL" name="[^"]*Before[^"]*"', text), (
        "no FATAL rule that the change list is shown before anything is written"
    )


def test_ids_defer_to_prd_rather_than_restating_it() -> None:
    """One surface: the id rule lives in /prd, and /replan points at it."""
    text = _text()
    assert "renumber" in text and "reuse" in text
    assert "`prd` skill" in text or "/prd" in text


def test_it_never_orders_work() -> None:
    text = _text()
    assert re.search(r'priority="FATAL">[^<]*order', text), (
        "no FATAL constraint that /replan does not order work"
    )
    for tool in ("jira_move_to_board", "jira_set_rank"):
        assert tool not in text.replace(f"Never call `{tool}`", ""), (
            f"/replan names {tool} as something it does"
        )


def test_it_is_published_in_the_index() -> None:
    assert "- `replan` (`/replan`) — " in INDEX.read_text(encoding="utf-8")
