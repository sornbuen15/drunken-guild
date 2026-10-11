# mypy: ignore-errors
"""DG-418. DG-409 added a retro step to `/audit` that reads a project's
recorded lessons, but `project-docs` named no lessons location at all, so the
step stopped with "nothing to read" on every project.

Decided by the Boss 2026-10-01: a tracked file is the source, `.ai/LESSONS.md`
by default, named in `project-docs`'s map and carried as a row in the
`AGENTS.md` template's Documents table. An agent's own memory stays its
scratch space — never a second lessons source.
"""

import re
from pathlib import Path

import pytest

from core.scaffold import agents_md

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DOCS = REPO_ROOT / "skills" / "documents" / "project-docs" / "SKILL.md"
TEMPLATE = REPO_ROOT / "src" / "core" / "templates" / "AGENTS.md"


def _the_map(text: str) -> str:
    return text.split("<the_map>", 1)[1].split("</the_map>", 1)[0]


def test_the_map_names_a_lessons_document() -> None:
    the_map = _the_map(PROJECT_DOCS.read_text(encoding="utf-8"))
    assert "LESSONS.md" in the_map, (
        "project-docs's map must name where a project's recorded lessons live"
    )


def test_the_default_lessons_path_is_listed_with_the_other_defaults() -> None:
    the_map = _the_map(PROJECT_DOCS.read_text(encoding="utf-8"))
    defaults_line = the_map.split("these are the defaults", 1)[1]
    assert ".ai/LESSONS.md" in defaults_line, (
        "the default lessons path must sit alongside the other default paths, "
        "not just the map table"
    )


def test_agents_md_template_documents_table_carries_the_lessons_row() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    documents_section = text.split("## Documents", 1)[1].split("## Jira", 1)[0]
    assert "LESSONS.md" in documents_section, (
        "the template's Documents table must carry a row for the project's "
        "recorded lessons"
    )
    assert ".ai/LESSONS.md" in documents_section


def test_lessons_row_is_outside_the_guild_block() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    block = text.split("<!-- guild-block:start -->", 1)[1].split(
        "<!-- guild-block:end -->", 1
    )[0]
    assert "LESSONS.md" not in block, (
        "the Documents table, including the lessons row, lives outside the "
        "guild block — only the pointer table lives inside it"
    )


def _collapsed(text: str) -> str:
    """Markdown wraps prose across lines, so a phrase spanning a line break
    reads with a newline and indent where the sentence has a single space.
    Collapse runs of whitespace before matching a multi-word phrase."""
    return re.sub(r"\s+", " ", text)


#: The five categories a second review named explicitly (DG-418): the first
#: pass's "secrets, personal data and private filesystem paths" left room
#: for a name, a phone number, an internal hostname, or another project's
#: own ticket key or name to slip through unnamed.
SCRUB_CATEGORIES = (
    "secrets and credentials",
    "personal data (names, emails, phone numbers, ids)",
    "home-directory and drive paths",
    "internal hostnames and URLs",
    "ticket keys or names of other projects",
)

#: Anchored on the three words a second review's own mutation test found
#: missing from the first pass: "before", "shown to the Boss" and "written"
#: must appear together, in that order — not just "scrubbed ... secrets
#: ... personal data ... private filesystem path" regardless of when.
BEFORE_SHOWN_WRITTEN_PATTERN = re.compile(
    r"before.{0,150}shown to the Boss.{0,150}written", re.I | re.S
)

#: Targets only the "before" immediately ahead of "shown to the Boss" in the
#: row, so the mutation test below changes exactly the word the anchor
#: depends on.
_BEFORE_NEAR_SHOWN = re.compile(r"\bbefore\b(?=.{0,150}shown to the Boss)", re.I | re.S)


def test_the_lessons_row_anchors_the_scrub_on_before_shown_and_written() -> None:
    """DG-418 second review. `scrubbed ... secrets ... personal data ...
    private filesystem path` alone does not say *when* the scrub happens;
    the row must say "before" it is shown to the Boss or written."""
    the_map = _collapsed(_the_map(PROJECT_DOCS.read_text(encoding="utf-8")))
    assert BEFORE_SHOWN_WRITTEN_PATTERN.search(the_map), (
        "the LESSONS.md row must say the scrub happens before either "
        "showing a lesson to the Boss or writing it to LESSONS.md"
    )


@pytest.mark.parametrize("category", SCRUB_CATEGORIES)
def test_each_scrub_category_is_named_in_the_lessons_row(category: str) -> None:
    the_map = _collapsed(_the_map(PROJECT_DOCS.read_text(encoding="utf-8")))
    assert category in the_map, (
        f"the LESSONS.md row must name {category!r} explicitly, not fold "
        "it into a shorter, less specific list"
    )


def test_flipping_before_to_after_breaks_the_anchor() -> None:
    """Proves the anchor test above is not a tautology: a second review
    found the first pass's pattern still matched after the reviewer changed
    only 'before' to 'after' in a scratch copy. This one fails unless the
    mutation does."""
    the_map = _collapsed(_the_map(PROJECT_DOCS.read_text(encoding="utf-8")))
    mutated = _BEFORE_NEAR_SHOWN.sub("after", the_map)
    assert not BEFORE_SHOWN_WRITTEN_PATTERN.search(mutated)


def test_template_still_renders_through_scaffold_with_project_and_jira_key() -> None:
    rendered = agents_md("app", "DG")
    assert "{project}" not in rendered
    assert "{jira_key}" not in rendered
    assert "`app`" in rendered
    assert "`DG`" in rendered
    assert ".ai/LESSONS.md" in rendered
