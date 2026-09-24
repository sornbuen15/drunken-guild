# mypy: ignore-errors
"""What the MCP server costs before anyone calls it — DG-361.

A tool's docstring *is* its description, and every description is sent to the
model in every session that declares this server. Ten of them came to 3.7K: the
third largest always-on cost in this project, behind CLAUDE.md and the skill
listing, and the only one nobody had looked at.

The line this file draws is not "shorter is better". A description has one job —
let a caller call the tool correctly — and the failure it prevents is an agent
that invents an argument or ignores a refusal. What does *not* belong is process
knowledge: the ticket shape, the word budget, what backlog membership means.
That lives in the `jira-tickets` skill, which loads when it is relevant and costs
nothing otherwise.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent / "src" / "jira_mcp" / "server.py"

#: Total across every tool description. 3.7K when this was written, cut to 1800.
#: Raised to 1900 by DG-368 for one new capability (jira_edit_labels, ~100
#: characters) — a tool, not process text, so it cannot move to the skill.
TOTAL_BUDGET = 1900

#: No single tool should need more than this. The longest was 869.
PER_TOOL_BUDGET = 320


def _decorated(kind: str) -> list[tuple[str, str]]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(kind in ast.unparse(d) for d in node.decorator_list):
            doc = ast.get_docstring(node) or ""
            out.append((node.name, " ".join(doc.split())))
    return out


def tools() -> list[tuple[str, str]]:
    return _decorated("mcp.tool")


def test_the_tools_are_found() -> None:
    """Guards the guard: a parser that matched nothing would make every budget
    below pass against an empty set."""
    names = {name for name, _ in tools()}
    assert len(names) >= 10, f"expected the full tool set, found {sorted(names)}"
    assert "jira_search_issues" in names


def test_the_total_description_budget_is_respected() -> None:
    total = sum(len(doc) for _, doc in tools())
    assert total <= TOTAL_BUDGET, (
        f"tool descriptions total {total} characters against a budget of "
        f"{TOTAL_BUDGET}. Every session declaring this server pays this before "
        "a single tool is called. Move process reasoning into the jira-tickets "
        "skill, which loads only when it is needed."
    )


@pytest.mark.parametrize("name, doc", tools())
def test_no_single_description_is_an_essay(name: str, doc: str) -> None:
    assert len(doc) <= PER_TOOL_BUDGET, (
        f"{name} carries {len(doc)} characters. A description exists to let a "
        "caller call the tool correctly; the reasoning belongs in the skill."
    )


@pytest.mark.parametrize("name, doc", tools())
def test_every_description_still_says_what_it_needs(name: str, doc: str) -> None:
    """Trimming must not take the two things a caller cannot infer.

    `project` is the argument DG-341 made mandatory, and a tool that does not
    name it invites the guess that defect was about. The second is emptiness: a
    description that says nothing at all is not a saving, it is a tool nobody
    knows when to use.
    """
    assert doc, f"{name} has no description at all"
    assert re.search(r"\bproject\b", doc), (
        f"{name} never mentions the project argument, which every tool takes "
        "first and refuses to guess (DG-341)."
    )
