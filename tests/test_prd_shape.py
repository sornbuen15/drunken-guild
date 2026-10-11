# mypy: ignore-errors
"""DG-377. drunken-guild keeps its own requirements in `.ai/PRD.md`.

The 2.0.0 target used to be said to live in "SESSION_CHECKPOINT.md §0" -- a
section that never existed, in a file that is deliberately not in git. So the
standard's own target was the one thing the standard did not keep.

`/audit` traces tickets through their `req:REQ-xxx` label to a requirement in
this file, so the shape is what matters: every live requirement carries an id,
a MoSCoW class and an acceptance sentence; a dropped one keeps its id, struck
through, with the reason. `DOMAIN.md` maps every live requirement to exactly
one bounded context, because each context is one Epic.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRD = ROOT / ".ai" / "PRD.md"
DOMAIN = ROOT / ".ai" / "DOMAIN.md"

HEADING = re.compile(r"^### (~~)?(REQ-\d{3}) — ", re.MULTILINE)
CLASSES = {"Must", "Should", "Could", "Won't"}


def _sections() -> dict[str, tuple[bool, str]]:
    text = PRD.read_text(encoding="utf-8")
    marks = list(HEADING.finditer(text))
    out = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end() : end].split("\n## ", 1)[0]
        out[m.group(2)] = (bool(m.group(1)), body)
    return out


def _live() -> set[str]:
    return {rid for rid, (dropped, _) in _sections().items() if not dropped}


def test_the_prd_exists_where_project_docs_looks_for_it() -> None:
    assert PRD.is_file(), f"{PRD} is missing"


def test_ids_are_sequential_and_never_reused() -> None:
    ids = [m.group(2) for m in HEADING.finditer(PRD.read_text(encoding="utf-8"))]
    numbers = [int(i.split("-")[1]) for i in ids]
    assert numbers == list(range(1, len(numbers) + 1)), ids


def test_every_live_requirement_has_a_class_and_an_acceptance() -> None:
    for rid, (dropped, body) in _sections().items():
        if dropped:
            continue
        klass = re.search(r"^\*\*Class:\*\* (.+)$", body, re.MULTILINE)
        assert klass and klass.group(1).strip() in CLASSES, f"{rid}: no MoSCoW class"
        assert re.search(r"^\*\*Acceptance:\*\* \S", body, re.MULTILINE), (
            f"{rid}: no acceptance sentence"
        )


def test_a_dropped_requirement_says_when_and_why() -> None:
    for rid, (dropped, body) in _sections().items():
        if dropped:
            assert re.search(
                r"^\*\*Dropped\*\* \d{4}-\d{2}-\d{2}", body, re.MULTILINE
            ), f"{rid}: struck through without a dated reason"


def test_every_live_requirement_belongs_to_exactly_one_context() -> None:
    assert DOMAIN.is_file(), f"{DOMAIN} is missing"
    text = DOMAIN.read_text(encoding="utf-8")
    table = text.split("## Bounded contexts", 1)[1].split("\n## ", 1)[0]
    rows = [r for r in table.splitlines() if r.startswith("| **")]
    assert rows, "no bounded contexts"
    seen: dict[str, int] = {}
    for row in rows:
        for rid in re.findall(r"REQ-\d{3}", row):
            seen[rid] = seen.get(rid, 0) + 1
    live = _live()
    assert set(seen) == live, (
        f"unmapped: {sorted(live - set(seen))}, unknown: {sorted(set(seen) - live)}"
    )
    assert all(n == 1 for n in seen.values()), {k: v for k, v in seen.items() if v > 1}
