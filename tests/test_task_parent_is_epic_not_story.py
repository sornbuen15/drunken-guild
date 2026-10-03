# mypy: ignore-errors
"""DG-448: `jira_create_issue` for a Task with a Story as parent fails with
"Please select valid parent issue" (HTTP 400) on this team-managed project --
Story and Task are both direct children of the Epic, and a Task that belongs
to a Story names it in the description instead. `jira-tickets` and
`breakdown` -- and, found by grepping the whole repo for the same claim,
README.md, GETTING_STARTED.md, agents/manager.md, examples/README.md,
examples/contributing/SKILL-annotated.md and the `jira_create_issue`
docstring/remediation in src/jira_mcp/server.py -- used to describe a
four-level chain (`Story -> Task`) that this Jira cannot create.

Reviewer finding on PR #136: the first version of this file covered only the
two skills. Reverting just README.md's line left all tests green, so the fix
could half-revert silently in any of the other files. Every file the finding
named now has its own structural check below, run against the real file on
disk -- not a fixture standing in for it.

Each check pulls the specific hierarchy statement out of its file with a
targeted regex -- not a blob grep -- so a change to unrelated prose
elsewhere cannot hide a real regression, and reads it structurally (parsing
arrow-chain groups or indentation depth, or matching the exact phrase a
docstring must carry) rather than testing for a bare substring.

The "Proof" section at the bottom unit-tests the extraction functions
themselves: it feeds each one a literal reintroducing "Task to Story" / a
`Story -> Task` chain and shows that function alone flags it. That is a
narrower claim than "the real files are covered" -- the tests above this
section are what cover the real files, confirmed by the end-to-end mutation
run quoted in the PR description (each real file edited to restore the old
claim, the full suite re-run and shown red, then `git checkout --` to
restore it).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JIRA_TICKETS = REPO_ROOT / "skills" / "workflow" / "jira-tickets" / "SKILL.md"
BREAKDOWN = REPO_ROOT / "skills" / "flow" / "breakdown" / "SKILL.md"
README = REPO_ROOT / "README.md"
GETTING_STARTED = REPO_ROOT / "GETTING_STARTED.md"
MANAGER = REPO_ROOT / "agents" / "manager.md"
EXAMPLES_README = REPO_ROOT / "examples" / "README.md"
SKILL_ANNOTATED = REPO_ROOT / "examples" / "contributing" / "SKILL-annotated.md"
SERVER_PY = REPO_ROOT / "src" / "jira_mcp" / "server.py"

#: An affirmative claim that a Task parents to a Story -- "Task to Story" or
#: "Task parents to Story", immediately adjacent so a negation in between
#: ("Task cannot parent to a Story") does not false-positive.
_TASK_PARENTS_TO_STORY = re.compile(
    r"Task\s+(?:parents?\s+to\s+|to\s+)(?:a\s+)?Story", re.IGNORECASE
)

#: The same claim drawn as an arrow diagram -- "Story -> Task" or
#: "Task -> Story" directly adjacent, either arrow glyph.
_STORY_TASK_ARROW_ADJACENT = re.compile(
    r"Story\s*(?:→|->)\s*Task|Task\s*(?:→|->)\s*Story", re.IGNORECASE
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


def _story_task_arrow_chain(text: str) -> str:
    """The `REQ... -> Epic -> ... -> Subtask` diagram line, wherever it sits
    in the file -- stops at the first `Subtask`, so it never reaches past
    the diagram into unrelated prose on a following line (`.` does not
    match a newline here, so the match cannot cross a line break either)."""
    match = re.search(r"REQ\S*\s*(?:→|->).*?Subtask", text)
    assert match, "no REQ...Subtask arrow chain found"
    return match.group(0)


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


def test_breakdown_action_sequence_does_not_say_tasks_per_story() -> None:
    text = BREAKDOWN.read_text(encoding="utf-8")
    match = re.search(r"3\. MAP:.*?(?=\n\s*4\. CHECK:)", text, re.DOTALL)
    assert match, "MAP step not found"
    assert not _TASK_PARENTS_TO_STORY.search(match.group(0))
    assert "Tasks per Story" not in match.group(0)


# --- Every file that carries a `REQ -> Epic -> ... -> Subtask` arrow-chain
# diagram: Story and Task must share one hop (siblings under the Epic), not
# be chained as consecutive hops. Reviewer finding on PR #136 -- the first
# version of this file checked only BREAKDOWN; README.md, GETTING_STARTED.md,
# examples/README.md and examples/contributing/SKILL-annotated.md carry the
# identical diagram and were not covered, so a revert of any one of them
# stayed green.

ARROW_CHAIN_FILES = {
    "breakdown/SKILL.md": BREAKDOWN,
    "README.md": README,
    "GETTING_STARTED.md": GETTING_STARTED,
    "examples/README.md": EXAMPLES_README,
    "examples/contributing/SKILL-annotated.md": SKILL_ANNOTATED,
}


def test_every_arrow_chain_file_is_found_and_named() -> None:
    """Guards the guard: a path that stopped existing would make the
    parametrized test below vacuous rather than failing."""
    for label, path in ARROW_CHAIN_FILES.items():
        assert path.is_file(), f"{label}: {path} does not exist"


def test_readme_arrow_chain_has_story_and_task_as_siblings() -> None:
    _assert_arrow_chain_siblings(README)


def test_getting_started_arrow_chain_has_story_and_task_as_siblings() -> None:
    _assert_arrow_chain_siblings(GETTING_STARTED)


def test_examples_readme_arrow_chain_has_story_and_task_as_siblings() -> None:
    _assert_arrow_chain_siblings(EXAMPLES_README)


def test_skill_annotated_arrow_chain_has_story_and_task_as_siblings() -> None:
    _assert_arrow_chain_siblings(SKILL_ANNOTATED)


def test_breakdown_arrow_chain_has_story_and_task_as_siblings() -> None:
    _assert_arrow_chain_siblings(BREAKDOWN)


def _assert_arrow_chain_siblings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    line = _story_task_arrow_chain(text)
    assert not _TASK_PARENTS_TO_STORY.search(line), line
    assert not _STORY_TASK_ARROW_ADJACENT.search(line), line
    groups = _arrow_groups(line)
    story_idx = next(i for i, g in enumerate(groups) if "Story" in g)
    task_idx = next(i for i, g in enumerate(groups) if "Task" in g)
    assert story_idx == task_idx, (
        f"{path}: Story and Task must share one arrow hop (both children of "
        f"Epic), got groups={groups}"
    )


# --- agents/manager.md: not an arrow-chain diagram -- "Epic -> Story and
# Epic -> Task" is two separate hops in one sentence, not a single chain
# `_arrow_groups` can parse. Checked directly instead.


def test_manager_md_does_not_chain_story_into_task() -> None:
    text = MANAGER.read_text(encoding="utf-8")
    match = re.search(r"Break work down as.*?(?=\n\s*-\s|\Z)", text, re.DOTALL)
    assert match, "the 'Break work down' bullet was not found in agents/manager.md"
    bullet = match.group(0)
    assert not _TASK_PARENTS_TO_STORY.search(bullet), bullet
    assert not _STORY_TASK_ARROW_ADJACENT.search(bullet), bullet
    assert re.search(r"Epic\s*(?:→|->)\s*Story", bullet), bullet
    assert re.search(r"Epic\s*(?:→|->)\s*Task", bullet), bullet


# --- src/jira_mcp/server.py: `jira_create_issue`'s docstring and the
# `ValidationError` remediation it raises when `parent` does not resolve to
# exactly one key. Both must say a Task is an acceptable `parent` value
# (needed for a Subtask) and neither may claim a Task parents to a Story.


def _jira_create_issue_source() -> str:
    text = SERVER_PY.read_text(encoding="utf-8")
    start = text.index("async def jira_create_issue")
    end = text.index("\n\n\n", start)
    return text[start:end]


def test_server_py_docstring_allows_task_as_a_parent_key() -> None:
    source = _jira_create_issue_source()
    match = re.search(r'"""(.*?)"""', source, re.DOTALL)
    assert match, "jira_create_issue has no docstring"
    docstring = match.group(1)
    assert not _TASK_PARENTS_TO_STORY.search(docstring), docstring
    assert re.search(r"Epic,\s*Story\s*or\s*Task\s*key", docstring), docstring


def test_server_py_remediation_allows_task_as_a_parent_key() -> None:
    source = _jira_create_issue_source()
    match = re.search(r'remediation="([^"]*)"', source)
    assert match, "no remediation= string found on the parent-key ValidationError"
    remediation = match.group(1)
    assert not _TASK_PARENTS_TO_STORY.search(remediation), remediation
    assert re.search(r"Epic,\s*Story\s*or\s*Task\s*key", remediation), remediation


# --- Proof: the extraction functions above, in isolation, catch the
# realistic mutation DG-448 names. This is a narrower claim than "the real
# files are covered" -- these feed the functions a literal, not a file --
# coverage of the real files is the tests above, and the PR description
# quotes the end-to-end run: each real file edited to restore the old claim,
# the suite re-run and shown red, then restored with `git checkout --`.


def test_check_catches_task_to_story_restored_in_parent_bullet() -> None:
    bullet = "Story parents to Epic, Task to Story, Subtask to Task."
    assert _TASK_PARENTS_TO_STORY.search(bullet)


def test_check_catches_story_task_chained_in_an_arrow_diagram() -> None:
    line = "REQ-xxx  →  Epic  →  Story  →  Task  →  Subtask"
    assert _STORY_TASK_ARROW_ADJACENT.search(line)
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
