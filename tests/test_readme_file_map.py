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

#: A backtick span whose text contains any of these characters is a code
#: literal -- a TOML table header (`[tool.setuptools.package-data]`), a
#: Python literal (`core = ["templates/*.md"]`) -- and not a path. Stated
#: rule, not a silent skip: anything with brackets, parens, braces, `=` or a
#: quote inside the span is excluded from the "must exist" check in column 4.
_CODE_LITERAL_CHARS = frozenset("[]{}()=\"'")

#: A bare backtick word with no slash and no recognised extension -- `src`,
#: `git`, a command name -- is prose, not a path this check can verify.
#: Stated rule: required to have a `/` or end in one of these, or it is
#: skipped, not flagged.
_PATH_EXTENSIONS = (
    ".py",
    ".sh",
    ".ps1",
    ".md",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
)


def _looks_like_a_path(token: str) -> bool:
    return "/" in token or token.endswith(_PATH_EXTENSIONS)


def _path_candidates_in_cell(cell: str) -> list[str]:
    """The paths a "generated / checked by" cell cites, for the
    "must also exist" check -- skipping, by the stated rules above, anything
    that is a code literal, a bare flag (`--index-only`) or a bare word with
    no path shape (`src`). A pytest node id (`path/to/test.py::test_name`) is
    reduced to its file. A span with a trailing flag
    (`` `scripts/x.sh --index-only` ``) is reduced to its first token."""
    candidates = []
    for span in _PATH_SPAN.findall(cell):
        if _CODE_LITERAL_CHARS & set(span):
            continue
        node_path = span.split("::", 1)[0]
        tokens = node_path.split()
        if not tokens:
            continue
        token = tokens[0]
        if token.startswith("-"):
            continue
        if _looks_like_a_path(token):
            candidates.append(token)
    return candidates


def _missing_cited_paths(rows: list[list[str]], repo_root: Path) -> list[str]:
    """Paths cited in column 4 (what generates or checks the row) that do not
    exist in the tree -- catches a cited file being renamed out from under a
    row the "path exists" check above never looks at, because that check only
    verifies column 1."""
    missing = []
    for cells in rows:
        for candidate in _path_candidates_in_cell(cells[3]):
            if not (repo_root / candidate).exists():
                missing.append(candidate)
    return missing


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


def test_legacy_note_cites_the_retiring_ticket() -> None:
    """DG-427 now retires templates/CLAUDE.md. The LEGACY note must name it,
    not say no ticket exists -- this fails if the reference is dropped or
    reverted to that older wording."""
    section = _repository_map_section(README.read_text(encoding="utf-8"))
    assert "LEGACY" in section
    assert "DG-427" in section
    assert "no open ticket" not in section.lower()


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


def test_every_cited_path_in_column_four_exists() -> None:
    """Reviewer note on PR 123: a path cited as the owner/checker in column 4
    (e.g. `tests/test_install_index_determinism.py`) must exist too, not just
    the row's own column-1 path -- a renamed checker file must not pass
    silently."""
    section = _repository_map_section(README.read_text(encoding="utf-8"))
    rows = _table_rows(section)
    missing = _missing_cited_paths(rows, REPO_ROOT)
    assert not missing, f"column 4 cites path(s) that do not exist: {missing}"


def test_checker_catches_a_cited_path_renamed_in_a_scratch_copy() -> None:
    """Proof for test_every_cited_path_in_column_four_exists, exactly as the
    reviewer reproduced it: rename a real cited file in a scratch copy of the
    table text (never the file on disk) and confirm the checker now flags
    it, where it silently passed before this test existed."""
    section = _repository_map_section(README.read_text(encoding="utf-8"))
    real_path = "tests/test_install_index_determinism.py"
    renamed_path = "tests/test_install_index_determinism_renamed.py"
    assert real_path in section, "fixture assumption: the real path is cited"

    scratch = section.replace(real_path, renamed_path)
    rows = _table_rows(scratch)
    assert renamed_path in _missing_cited_paths(rows, REPO_ROOT)


def test_path_candidates_skip_a_code_literal() -> None:
    """Stated rule, not a silent skip: a TOML table header or a Python
    literal inside backticks is not a path."""
    cell = (
        "packaged via `pyproject.toml`'s `[tool.setuptools.package-data]` "
        '(`core = ["templates/*.md"]`)'
    )
    assert _path_candidates_in_cell(cell) == ["pyproject.toml"]


def test_path_candidates_skip_a_bare_flag() -> None:
    cell = "generated by `scripts/install/install_skills.sh --index-only`"
    assert _path_candidates_in_cell(cell) == ["scripts/install/install_skills.sh"]


def test_path_candidates_skip_a_bare_word_with_no_path_shape() -> None:
    cell = "the installed tool carries only `src`"
    assert _path_candidates_in_cell(cell) == []


def test_path_candidates_reduce_a_pytest_node_id_to_its_file() -> None:
    cell = "`tests/test_agents_md.py::test_claude_md_holds_no_rule_agents_md_lacks`"
    assert _path_candidates_in_cell(cell) == ["tests/test_agents_md.py"]
