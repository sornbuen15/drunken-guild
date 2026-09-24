# mypy: ignore-errors
"""DG-388. The Brief is the project's constitution (REQ-016).

Spec-driven tools open a project with a "constitution": mission, tech stack,
roadmap, in files of their own. drunken-guild already has that agreement — the
Brief at the top of PRD.md — and the roadmap is Jira. A second file saying the
same thing is a second surface that drifts, which is why the brief and the
requirements were merged into one file in the first place.

So `/prd` must say the word, so an agent that arrives looking for a constitution
lands on the Brief, and nothing may generate the file the word suggests.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRD_SKILL = ROOT / "skills" / "flow" / "prd" / "SKILL.md"

#: Files a constitution-style workflow would create. None may be produced here.
FORBIDDEN = re.compile(
    r"\b(constitution|mission|roadmap|tech-stack|tech_stack)\.md\b", re.I
)


def test_prd_names_constitution_as_the_brief() -> None:
    text = PRD_SKILL.read_text(encoding="utf-8")
    assert re.search(r"constitution", text, re.I), "/prd never says 'constitution'"
    brief = text.split("## Brief", 1)[0]
    assert re.search(r"Brief[^.]*constitution|constitution[^.]*Brief", brief), (
        "'constitution' is not tied to the Brief before the shape is shown"
    )


def test_prd_says_no_separate_file_and_the_roadmap_is_jira() -> None:
    text = PRD_SKILL.read_text(encoding="utf-8").lower()
    assert "roadmap" in text and "jira" in text


def test_nothing_generates_a_constitution_file() -> None:
    hits = []
    for base in ("skills", "templates", "src", "scripts"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in {".md", ".py", ".sh", ".ps1"} or not path.is_file():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line) and "no " not in line.lower():
                    hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert not hits, f"a constitution-style file is named: {hits}"
