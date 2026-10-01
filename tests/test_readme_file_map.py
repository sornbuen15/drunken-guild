# mypy: ignore-errors
"""DG-426. The "Repository map" table in README.md says which file or folder
lives where, who it is for, whether a person edits it by hand, and what
generates or checks it. These tests parse that table the way a reader would
and verify it against the real tree, rather than trusting the prose.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

#: The exact, small set of paths this table covers (DG-426's SCOPE list).
#: Kept here, separately from the parser, so a row silently added or dropped
#: is caught by comparing two independent sources: the table itself and this
#: constant.
COVERED_PATHS = frozenset(
    {
        ".ai/",
        "AGENTS.md",
        "CLAUDE.md",
        "skills/",
        "agents/",
        "plugins/",
        "src/core/templates/",
        "templates/",
        "examples/",
        "scripts/install/",
    }
)

_PATH_SPAN = re.compile(r"`([^`]+)`")


def _repository_map_section(text: str) -> str:
    """The table's own section: from its heading to the next `##` heading."""
    start = text.index("## Repository map")
    rest = text[start:]
    body = rest.split("\n## ", 1)[0]
    return body


def _table_rows(section: str) -> list[list[str]]:
    """Data rows of the `| path | for whom | hand-edited | generated / checked
    by |` table -- the header and the `|---|---|---|---|` separator skipped."""
    rows: list[list[str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4:
            continue
        if cells[0].lower() == "path" or set(cells[0]) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def _row_path(cells: list[str]) -> str:
    """The literal path a row names -- the first backtick span in its first
    cell, e.g. `` `templates/` `` -> `templates/`."""
    match = _PATH_SPAN.search(cells[0])
    assert match, f"row names no backtick path: {cells[0]!r}"
    return match.group(1)


def _missing_paths(rows: list[list[str]], repo_root: Path) -> list[str]:
    """Paths a row names that do not exist in the tree, file or directory."""
    missing = []
    for cells in rows:
        path = _row_path(cells)
        if not (repo_root / path).exists():
            missing.append(path)
    return missing


def _paths_outside_covered(rows: list[list[str]], covered: frozenset[str]) -> list[str]:
    """Paths a row names that are not in the covered set -- the table naming
    something this ticket's scope does not cover."""
    return [_row_path(cells) for cells in rows if _row_path(cells) not in covered]


def test_repository_map_section_exists() -> None:
    text = README.read_text(encoding="utf-8")
    assert "## Repository map" in text


def test_repository_map_has_data_rows() -> None:
    section = _repository_map_section(README.read_text(encoding="utf-8"))
    rows = _table_rows(section)
    assert rows, "Repository map table has no data rows to check"


def test_every_row_path_exists_in_the_tree() -> None:
    """ACCEPTANCE: the section exists and every path it names exists."""
    section = _repository_map_section(README.read_text(encoding="utf-8"))
    rows = _table_rows(section)
    missing = _missing_paths(rows, REPO_ROOT)
    assert not missing, f"Repository map names path(s) that do not exist: {missing}"


def test_table_names_exactly_the_covered_set() -> None:
    """Catches a row silently added or a row silently dropped: the table's
    paths and this file's COVERED_PATHS constant must agree."""
    section = _repository_map_section(README.read_text(encoding="utf-8"))
    rows = _table_rows(section)
    named = {_row_path(cells) for cells in rows}
    assert named == COVERED_PATHS


def test_checker_catches_a_row_whose_path_was_removed() -> None:
    """Proof for test_every_row_path_exists_in_the_tree, fed through the real
    checker: a row naming a path that does not exist must be flagged. Stands
    in for deleting a real path out from under a real row, which this test
    suite must not do to its own tree."""
    rows = [["`templates/this-does-not-exist.md`", "nobody", "no", "nothing"]]
    assert _missing_paths(rows, REPO_ROOT) == ["templates/this-does-not-exist.md"]


def test_checker_passes_when_every_row_path_exists() -> None:
    rows = [["`README.md`", "readers", "yes", "nothing"]]
    assert _missing_paths(rows, REPO_ROOT) == []


def test_checker_catches_a_row_naming_a_path_outside_the_covered_set() -> None:
    """Proof for test_table_names_exactly_the_covered_set: a row naming a path
    this ticket's scope does not cover must be flagged, not silently
    accepted."""
    rows = [["`scripts/`", "nobody", "no", "nothing"]]
    assert _paths_outside_covered(rows, COVERED_PATHS) == ["scripts/"]


def test_checker_accepts_a_row_naming_a_covered_path() -> None:
    rows = [["`templates/`", "nobody", "no", "nothing"]]
    assert _paths_outside_covered(rows, COVERED_PATHS) == []
