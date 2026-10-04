# mypy: ignore-errors
"""DG-449. worker.md, reviewer.md and manager.md each declare their tools
explicitly in frontmatter, and none of them listed
`mcp__drunken-jira-mcp__jira_get_comments` -- so a worker or reviewer could
not read a comment at all. DG-427's worker never saw the Boss's decision
("ONE template folder"), recorded only as a comment, and wrote the opposite
into its PR.

This derives, from each role file's own body, which bare Jira tool names
(`jira_something`) it names in prose -- and checks every one of them is
actually granted in the frontmatter `tools:` line. It also asserts directly
that the three shipped roles carry `jira_get_comments`, since a role is
allowed to grant a tool it never names literally in its body (the comment
read is implied by the workflow, not spelled out everywhere).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

_ROLE_FILES = sorted(AGENTS_DIR.glob("*.md"))
_ROLE_FILES = [p for p in _ROLE_FILES if p.name != "INDEX.md"]

#: A bare `jira_<name>` reference in prose or backticks, e.g. `jira_start_task`,
#: not the fully-qualified `mcp__drunken-jira-mcp__jira_start_task` the tools
#: line itself uses.
_BARE_JIRA_TOOL = re.compile(r"(?<![\w-])jira_[a-z_]+")

_MCP_PREFIX = "mcp__drunken-jira-mcp__"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Pull the `key: value` frontmatter lines out of an agent file. Good
    enough for the single-line fields this repo's agents use (`name`,
    `tools`, ...) -- the same shape the real installer and its own tests
    parse."""
    assert text.startswith("---\n"), "role file has no frontmatter delimiter"
    _, rest = text.split("---\n", 1)
    block, _ = rest.split("\n---", 1)
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _body(text: str) -> str:
    """Everything after the closing frontmatter delimiter."""
    _, rest = text.split("---\n", 1)
    _, body = rest.split("\n---", 1)
    return body


def _tools_line(text: str) -> list[str]:
    fields = _parse_frontmatter(text)
    assert "tools" in fields, "role file frontmatter carries no 'tools:' line"
    return [t.strip() for t in fields["tools"].split(",")]


def _jira_tools_named_in_body(text: str) -> set[str]:
    """Every bare `jira_xxx` name the body mentions, outside the frontmatter
    `tools:` line itself (which spells the names fully-qualified, so the bare
    pattern never matches there anyway)."""
    body = _body(text)
    return set(_BARE_JIRA_TOOL.findall(body))


def _granted_bare_names(tools: list[str]) -> set[str]:
    return {t[len(_MCP_PREFIX) :] for t in tools if t.startswith(_MCP_PREFIX + "jira_")}


@pytest.mark.parametrize("path", _ROLE_FILES, ids=[p.name for p in _ROLE_FILES])
def test_every_jira_tool_named_in_the_body_is_granted_in_tools(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")
    tools = _tools_line(text)
    granted = _granted_bare_names(tools)
    named = _jira_tools_named_in_body(text)
    missing = named - granted
    assert not missing, (
        f"{path.name} names {sorted(missing)} in its body but does not grant "
        f"it in the 'tools:' frontmatter line -- the role could never call it"
    )


@pytest.mark.parametrize("role", ["worker", "reviewer", "manager"])
def test_role_carries_jira_get_comments(role: str) -> None:
    path = AGENTS_DIR / f"{role}.md"
    text = path.read_text(encoding="utf-8")
    tools = _tools_line(text)
    assert f"{_MCP_PREFIX}jira_get_comments" in tools, (
        f"{path.name} does not grant jira_get_comments -- this role cannot "
        "read a ticket's comments, including a binding Boss decision "
        "recorded only there (DG-427)"
    )


def test_worker_and_reviewer_are_told_to_read_comments_first() -> None:
    for role in ("worker", "reviewer"):
        text = (AGENTS_DIR / f"{role}.md").read_text(encoding="utf-8")
        body = _body(text)
        assert "jira_get_comments" in body, (
            f"{role}.md grants jira_get_comments but never tells the role "
            "to use it before starting or reviewing"
        )
        assert "binding" in body, (
            f"{role}.md does not say a Boss decision recorded in a comment is binding"
        )


# --- Proof the derivation above actually catches the realistic mutations
# the ticket names: removing the tool from one real file, and a new role
# file that names a Jira tool in its body but omits it from 'tools:'.


def test_mutation_removing_jira_get_comments_from_tools_line_is_caught() -> None:
    text = (AGENTS_DIR / "worker.md").read_text(encoding="utf-8")
    mutated = text.replace(f", {_MCP_PREFIX}jira_get_comments", "")
    assert f"{_MCP_PREFIX}jira_get_comments" not in _tools_line(mutated)
    # And the dedicated per-role check would fail against it:
    tools = _tools_line(mutated)
    assert f"{_MCP_PREFIX}jira_get_comments" not in tools


def test_mutation_new_role_naming_a_tool_it_does_not_grant_is_caught(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "scout.md"
    fixture.write_text(
        "---\n"
        "name: scout\n"
        "description: A throwaway fixture role.\n"
        "model: claude-sonnet-5\n"
        "tools: Read, Grep, mcp__drunken-jira-mcp__jira_search_issues\n"
        "---\n"
        "\n"
        "<system_prompt>\n"
        "  Before anything, call `jira_get_comments` on the ticket.\n"
        "</system_prompt>\n",
        encoding="utf-8",
    )
    text = fixture.read_text(encoding="utf-8")
    tools = _tools_line(text)
    granted = _granted_bare_names(tools)
    named = _jira_tools_named_in_body(text)
    missing = named - granted
    assert missing == {"jira_get_comments"}, (
        "the fixture role names jira_get_comments in its body without "
        "granting it -- the derivation must flag exactly that"
    )
