# mypy: ignore-errors
"""DG-448: `jira_create_issue` for a Task with a Story as parent fails with
"Please select valid parent issue" (HTTP 400) on this team-managed project --
Story and Task are both direct children of the Epic, and a Task that belongs
to a Story names it in the description instead. `jira-tickets` and
`breakdown` used to describe a four-level chain (`Story -> Task`) that this
Jira cannot create.

Each check below pulls the specific hierarchy statement out of the file with
a targeted regex -- not a blob grep -- so a change to unrelated prose
elsewhere cannot hide a real regression, and reads it structurally (parsing
indentation depth or arrow-chain groups) rather than testing for a bare
substring. The "Proof" section at the bottom feeds the same extraction
functions a reintroduced "Task to Story" / `Story -> Task` chain -- the
realistic mutation DG-448 names -- and shows it is caught.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JIRA_TICKETS = REPO_ROOT / "skills" / "workflow" / "jira-tickets" / "SKILL.md"
BREAKDOWN = REPO_ROOT / "skills" / "flow" / "breakdown" / "SKILL.md"

#: An affirmative claim that a Task parents to a Story -- "Task to Story" or
#: "Task parents to Story", immediately adjacent so a negation in between
#: ("Task cannot parent to a Story") does not false-positive.
_TASK_PARENTS_TO_STORY = re.compile(
    r"Task\s+(?:parents?\s+to\s+|to\s+)(?:a\s+)?Story", re.IGNORECASE
)


def _parent_bullet(text: str) -> str:
    """The `**\\`parent\\`** -- ...` bullet in jira-tickets §5, pulled out by
    its own heading, stopped at the next list item or a blank line rather
    than at the end of the file."""
    match = re.search(
        r"\*\*`parent`\*\*\s*—\s*(.+?)(?=\n- \*\*|\n\n|\Z)", text, re.DOTALL
    )
    assert match, "no `parent` field bullet found in jira-tickets SKILL.md"
    return match.group(1)


def _indentation_tree(block: str) -> dict[str, str | None]:
    """Parse an indentation-style tree (one bare node name per line, deeper
    lines indented further) into {node: nearest shallower node}. Blank lines
    and lines whose indent is 0 start a new, unrelated root."""
    parents: dict[str, str | None] = {}
    stack: list[tuple[int, str]] = []
    for line in block.splitlines():
        if not line.strip():
            stack = []
            continue
        indent = len(line) - len(line.lstrip(" "))
        name = line.split()[0]
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parents[name] = stack[-1][1] if stack else None
        stack.append((indent, name))
    return parents


def _arrow_groups(line: str) -> list[frozenset[str]]:
    """Split an arrow-chain diagram line like `A -> B | C -> D` into ordered
    groups of sibling node names: [{"A"}, {"B", "C"}, {"D"}]."""
    hops = re.split(r"→|->", line)
    return [frozenset(n.strip() for n in hop.split("|") if n.strip()) for hop in hops]


def test_jira_tickets_parent_bullet_does_not_claim_task_parents_to_story() -> None:
    text = JIRA_TICKETS.read_text(encoding="utf-8")
    bullet = _parent_bullet(text)
    assert not _TASK_PARENTS_TO_STORY.search(bullet), bullet
    assert "Epic" in bullet and "Task" in bullet


def test_jira_tickets_hierarchy_diagram_has_task_and_story_as_siblings() -> None:
    text = JIRA_TICKETS.read_text(encoding="utf-8")
    start = text.index("REQ-xxx       lives")
    end = text.index("Bug           sits", start)
    tree = _indentation_tree(text[start:end])
    assert tree["Task"] == tree["Story"] == "Epic", tree
    assert tree["Task"] != "Story"


def test_breakdown_hierarchy_line_has_story_and_task_as_siblings() -> None:
    text = BREAKDOWN.read_text(encoding="utf-8")
    match = re.search(r"REQ-xxx.*?Subtask", text)
    assert match, "hierarchy line not found in breakdown SKILL.md"
    line = match.group(0)
    assert not _TASK_PARENTS_TO_STORY.search(line), line
    groups = _arrow_groups(line)
    story_idx = next(i for i, g in enumerate(groups) if "Story" in g)
    task_idx = next(i for i, g in enumerate(groups) if "Task" in g)
    assert story_idx == task_idx, (
        "Story and Task must share one arrow hop (both children of Epic), "
        f"got groups={groups}"
    )


def test_breakdown_action_sequence_does_not_say_tasks_per_story() -> None:
    text = BREAKDOWN.read_text(encoding="utf-8")
    match = re.search(r"3\. MAP:.*?(?=\n\s*4\. CHECK:)", text, re.DOTALL)
    assert match, "MAP step not found"
    assert not _TASK_PARENTS_TO_STORY.search(match.group(0))
    assert "Tasks per Story" not in match.group(0)


# --- Proof: the extraction functions above are shown to catch the realistic
# mutation DG-448 names -- restoring "Task to Story" / a Story->Task chain.


def test_check_catches_task_to_story_restored_in_parent_bullet() -> None:
    bullet = "Story parents to Epic, Task to Story, Subtask to Task."
    assert _TASK_PARENTS_TO_STORY.search(bullet)


def test_check_catches_story_task_chained_in_an_arrow_diagram() -> None:
    line = "REQ-xxx  →  Epic  →  Story  →  Task  →  Subtask"
    groups = _arrow_groups(line)
    story_idx = next(i for i, g in enumerate(groups) if "Story" in g)
    task_idx = next(i for i, g in enumerate(groups) if "Task" in g)
    assert story_idx != task_idx


def test_check_catches_task_nested_under_story_in_an_indentation_tree() -> None:
    block = (
        "REQ-xxx       lives in PRD.md. Never a Jira issue.\n"
        "  Epic          one bounded context from DOMAIN.md\n"
        "    Story         one behaviour a customer would notice\n"
        "      Task          one vertical slice, finishable in a day\n"
        "        Subtask       one ordered step of that task\n"
        "\n"
        "Bug           sits beside the hierarchy, parented where the defect lives\n"
    )
    tree = _indentation_tree(block)
    assert tree["Task"] == "Story"
    assert tree["Task"] != "Epic"
