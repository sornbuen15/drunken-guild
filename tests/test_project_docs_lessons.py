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


#: The scrub clause itself, read out of the skill rather than restated here.
SCRUB_PATTERN = re.compile(
    r"[Ss]crubbed.{0,120}secrets.{0,120}personal data.{0,120}private filesystem path",
    re.S,
)


def test_the_lessons_row_names_the_scrub_requirement() -> None:
    """DG-418 review (HIGH). LESSONS.md is a tracked file in a project that
    may be public, and an agent's own memory can hold a name, an email, an
    id or a secret. The map's own row must say so, matching the audit
    skill's retro step."""
    the_map = _the_map(PROJECT_DOCS.read_text(encoding="utf-8"))
    assert SCRUB_PATTERN.search(the_map), (
        "the LESSONS.md row must name the scrub requirement — secrets, "
        "personal data and private filesystem paths — before anything is "
        "written there"
    )


def test_removing_the_scrub_clause_leaves_the_row_silent() -> None:
    """Proves the test above is not a tautology: with the scrub clause
    stripped from a scratch copy, the same check now fails."""
    the_map = _the_map(PROJECT_DOCS.read_text(encoding="utf-8"))
    stripped = SCRUB_PATTERN.sub("REMOVED", the_map)
    assert not SCRUB_PATTERN.search(stripped)


def test_template_still_renders_through_scaffold_with_project_and_jira_key() -> None:
    rendered = agents_md("app", "DG")
    assert "{project}" not in rendered
    assert "{jira_key}" not in rendered
    assert "`app`" in rendered
    assert "`DG`" in rendered
    assert ".ai/LESSONS.md" in rendered
