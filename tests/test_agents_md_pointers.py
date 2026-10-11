# mypy: ignore-errors
"""DG-393. Every reference to a *project's own* AGENTS.md -- in project-docs,
build, audit, the jira-mcp project-id error, README, GETTING_STARTED and
templates/PROJECT_BRIEF -- must name the exact file `drunken-init` writes at
the project root, or it sends an agent looking for a map that is not there.

Each site below is anchored on the actual sentence making the pointer (not a
bare `AGENTS.md` substring search over the whole file, which would also catch
this repo's own `AGENTS.md`, `src/core/templates/AGENTS.md` -- the packaged
template -- and the self-referential links in README/GETTING_STARTED's own
file tables, none of which are the "a project's instruction file" claim
DG-393's SCOPE is about). The anchor's own wording has to survive, so a
negated or reworded sentence breaks the match the same as deleting it would;
the captured filename then has to resolve against what `drunken-init` really
writes, read back off a scratch directory after actually running
`scaffold.instruction_files` -- so a path-prefixed or namespaced reference
(`.agents/AGENTS.md`, a retired location that is never read) fails exactly
like a typo would, and a rename on the producing side fails this test too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core import scaffold

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A run of path-ish characters ending in `AGENTS.md`, so a prefixed or
#: namespaced reference is captured whole, not matched on the trailing
#: filename alone.
_FILENAME = r"[\w./\\-]*AGENTS\.md"

#: Every site DG-393's SCOPE names, each paired with the anchor(s) for the
#: sentence actually making the pointer there. `{name}` is substituted with
#: `_FILENAME` and captured as the group `token`.
_SITES: dict[Path, list[str]] = {
    REPO_ROOT / "src" / "jira_mcp" / "server.py": [
        r"project's (?P<token>{name}) names which one",
    ],
    REPO_ROOT / "skills" / "flow" / "build" / "SKILL.md": [
        r"project's `(?P<token>{name})` does not say where",
    ],
    REPO_ROOT / "skills" / "flow" / "audit" / "SKILL.md": [
        r"recorded in its `(?P<token>{name})`",
        r"target from (?P<token>{name})\)",
    ],
    REPO_ROOT / "skills" / "documents" / "project-docs" / "SKILL.md": [
        r"`(?P<token>{name})` at the project root is the map",
    ],
    REPO_ROOT / "README.md": [
        r"project's root `(?P<token>{name})` is the map",
    ],
    REPO_ROOT / "GETTING_STARTED.md": [
        r"project's root `(?P<token>{name})`\. When there is no map",
        r"record the paths in `(?P<token>{name})` and the skills follow",
        r"recorded in its own `(?P<token>{name})`",
    ],
    REPO_ROOT / "templates" / "PROJECT_BRIEF.md": [
        r"project's root `(?P<token>{name})`",
    ],
}


def produced_instruction_filenames(tmp_path: Path) -> set[str]:
    """What `drunken-init` actually writes at a project's root, read back
    from disk after running the real scaffolding step -- not a list
    maintained by hand beside it, which would just be a second copy of the
    same fact."""
    scaffold.instruction_files(tmp_path, "demo-project", None)
    return {entry.name for entry in tmp_path.iterdir() if entry.is_file()}


_CASES = [(path, anchor) for path, anchors in _SITES.items() for anchor in anchors]


@pytest.mark.parametrize(
    "path,anchor",
    _CASES,
    ids=[f"{p.relative_to(REPO_ROOT)}::{a[:24]}" for p, a in _CASES],
)
def test_site_points_at_a_file_drunken_init_actually_writes(
    path: Path, anchor: str, tmp_path: Path
) -> None:
    produced = produced_instruction_filenames(tmp_path)
    assert "AGENTS.md" in produced, (
        "scaffold.instruction_files no longer writes AGENTS.md at all -- "
        f"it produced {sorted(produced)} instead"
    )

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(anchor.format(name=_FILENAME))
    match = pattern.search(text)
    assert match, (
        f"{path.relative_to(REPO_ROOT)} no longer carries the sentence this "
        f"pointer depends on (looked for: {anchor!r})"
    )

    token = match.group("token")
    assert token == "AGENTS.md", (
        f"{path.relative_to(REPO_ROOT)} points at {token!r}, not the bare "
        "AGENTS.md drunken-init writes at the project root -- that path is "
        "either never produced or never read"
    )
