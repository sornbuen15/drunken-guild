# mypy: ignore-errors
"""DG-427. The Boss's comment on this ticket (2026-10-02) was explicit: before
anything under `templates/` is retired, list every reference to each file and
what reads it, then retire only files nothing reads; a file something still
reads is either moved into `src/core/templates/` or left at the root with a
stated reason. README's "`templates/` root — per-file inventory" table is
that list. This module checks it mechanically against the real tree, the
same way `test_readme_file_map.py` checks the broader Repository map: a file
added to `templates/` without a row, or a row naming a file that is not
there, is exactly the drift this ticket exists to stop from happening again.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

_HEADING = "## Templates root — per-file inventory (DG-427)"
_PATH_SPAN = re.compile(r"`([^`]+)`")


def _inventory_section(text: str) -> str:
    """From the inventory heading to the next `## ` heading, so a later
    section is never swept in."""
    start = text.index(_HEADING)
    rest = text[start + len(_HEADING) :]
    body = rest.split("\n## ", 1)[0]
    return body


def _table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4:
            continue
        if cells[0].lower() == "file" or set(cells[0]) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def _row_files(cells: list[str]) -> list[str]:
    """Every filename the row's first cell names -- plain, so a path never
    appears with a trailing backtick the way it would straight out of the
    regex match."""
    names = _PATH_SPAN.findall(cells[0])
    assert names, f"row names no backtick path: {cells[0]!r}"
    return names


def _row_is_retired(cells: list[str]) -> bool:
    """A row is retired when either its readers cell or its decision cell
    says so -- the readers cell for `CLAUDE.md` reads "*(retired)* was ...",
    past tense, and the decision cell for every row says "retired" or
    "left at root"/"move" for the rest."""
    return "retired" in cells[1].lower() or "retired" in cells[3].lower()


def _actual_template_files(templates_dir: Path) -> set[str]:
    return {
        str(p.relative_to(templates_dir)).replace("\\", "/")
        for p in templates_dir.rglob("*")
        if p.is_file()
    }


def _check(section: str, templates_dir: Path) -> tuple[set[str], set[str], set[str]]:
    """Returns (missing_rows, stray_rows, retired_but_present) --

    - missing_rows: a real file under *templates_dir* with no live row
      naming it.
    - stray_rows: a live row naming a file that is not actually there.
    - retired_but_present: a row marked retired whose file still exists on
      disk -- the retirement did not actually happen.
    """
    rows = _table_rows(section)
    live_named: set[str] = set()
    retired_named: set[str] = set()
    for cells in rows:
        files = _row_files(cells)
        if _row_is_retired(cells):
            retired_named.update(files)
        else:
            live_named.update(files)

    actual = _actual_template_files(templates_dir)
    missing_rows = actual - live_named - retired_named
    stray_rows = live_named - actual
    retired_but_present = retired_named & actual
    return missing_rows, stray_rows, retired_but_present


def test_inventory_heading_exists() -> None:
    text = README.read_text(encoding="utf-8")
    assert _HEADING in text


def test_inventory_has_rows() -> None:
    section = _inventory_section(README.read_text(encoding="utf-8"))
    assert _table_rows(section), "the inventory table has no data rows to check"


def test_every_real_templates_file_has_a_row_and_every_row_is_real() -> None:
    """ACCEPTANCE: every file under templates/ appears in the table, every
    live row names a file that is actually there, and nothing marked
    retired is still on disk."""
    section = _inventory_section(README.read_text(encoding="utf-8"))
    missing, stray, retired_but_present = _check(section, REPO_ROOT / "templates")

    assert not missing, f"templates/ has file(s) with no row: {sorted(missing)}"
    assert not stray, f"the table names file(s) that do not exist: {sorted(stray)}"
    assert not retired_but_present, (
        f"marked retired but still on disk: {sorted(retired_but_present)}"
    )


def test_checker_catches_a_file_added_without_a_row(tmp_path: Path) -> None:
    """Mutation proof, half one: a file dropped into a scratch `templates/`
    with no matching row must be flagged -- stands in for adding a real file
    to the real `templates/` without updating README, which this suite must
    not do to its own tree."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / ".cursorrules").write_text("x")
    (templates_dir / "NEW_UNDOCUMENTED.md").write_text("x")

    section = """
| file | readers | true under REQ-006 / REQ-015? | decision |
|---|---|---|---|
| `.cursorrules` | someone | yes | left at root |
"""
    missing, stray, retired_but_present = _check(section, templates_dir)

    assert missing == {"NEW_UNDOCUMENTED.md"}
    assert stray == set()
    assert retired_but_present == set()


def test_checker_catches_a_row_whose_file_is_gone(tmp_path: Path) -> None:
    """Mutation proof, half two: a row left behind after its file is removed
    (or renamed) must be flagged, not silently accepted."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / ".cursorrules").write_text("x")

    section = """
| file | readers | true under REQ-006 / REQ-015? | decision |
|---|---|---|---|
| `.cursorrules` | someone | yes | left at root |
| `GONE.md` | nobody any more | yes | left at root |
"""
    missing, stray, retired_but_present = _check(section, templates_dir)

    assert missing == set()
    assert stray == {"GONE.md"}
    assert retired_but_present == set()


def test_checker_catches_a_retired_file_that_never_actually_left(
    tmp_path: Path,
) -> None:
    """A row claiming retirement while the file is still physically present
    under templates/ -- the retirement half of the acceptance criterion."""
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "CLAUDE.md").write_text("x")

    section = """
| file | readers | true under REQ-006 / REQ-015? | decision |
|---|---|---|---|
| `CLAUDE.md` | *(retired)* was somewhere | no | **retired** (DG-427) |
"""
    missing, stray, retired_but_present = _check(section, templates_dir)

    assert missing == set()
    assert stray == set()
    assert retired_but_present == {"CLAUDE.md"}


def test_checker_accepts_a_clean_matching_tree(tmp_path: Path) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / ".cursorrules").write_text("x")
    ci_dir = templates_dir / "ci"
    ci_dir.mkdir()
    (ci_dir / "dependency-audit.yml").write_text("x")

    section = """
| file | readers | true under REQ-006 / REQ-015? | decision |
|---|---|---|---|
| `.cursorrules` | someone | yes | left at root |
| `ci/dependency-audit.yml` | someone | yes | left at root |
"""
    assert _check(section, templates_dir) == (set(), set(), set())
