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

Reviewer follow-up on PR #139: a bare `jira_[a-z_]+` regex also matches
`jira_mcp` inside a path like `src/jira_mcp`, which is not a tool name at
all -- a false positive that would fail a role file for naming its own MCP
server in prose. The fix is to only treat a name as a "Jira tool named in
the body" when it is also a *registered* tool, derived by reading
`src/jira_mcp/server.py` for its `def jira_...` / `async def jira_...`
names -- the same authority the MCP server itself runs on, not a second
hand-written list beside it.

DG-402 update: `agents/<role>.md` is now a *generated* adapter (frontmatter
plus one fixed pointer paragraph) -- the role's own prose, including the
sentences this file checks for ("jira_get_comments", "binding", "author",
no "@"), now lives in `skills/roles/<role>/SKILL.md` instead. The tests that
read a role's body text were migrated to read the skill file, not deleted:
the rule they enforce is unchanged, only where that text now lives. The
`tools:` grant itself is still read from the generated `agents/<role>.md`,
since that frontmatter line is the Claude-specific plumbing this ticket
explicitly keeps there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
ROLES_DIR = REPO_ROOT / "skills" / "roles"
SERVER_PY = REPO_ROOT / "src" / "jira_mcp" / "server.py"

#: A bare `jira_<name>` reference in prose or backticks, e.g. `jira_start_task`,
#: not the fully-qualified `mcp__drunken-jira-mcp__jira_start_task` the tools
#: line itself uses. Matches more than real tool names (e.g. `jira_mcp` in a
#: path) -- callers must intersect with `_registered_jira_tools()` to get
#: only names that are actually tools.
_BARE_JIRA_TOOL = re.compile(r"(?<![\w-])jira_[a-z_]+")

#: `def jira_foo(...)` or `async def jira_foo(...)` in the server module --
#: the real vocabulary of registered tools, read off the source rather than
#: duplicated here by hand.
_TOOL_DEF = re.compile(r"^(?:async )?def (jira_[a-z_]+)\(", re.MULTILINE)

_MCP_PREFIX = "mcp__drunken-jira-mcp__"


def _registered_jira_tools() -> set[str]:
    text = SERVER_PY.read_text(encoding="utf-8")
    names = set(_TOOL_DEF.findall(text))
    assert names, "no 'def jira_...' found in server.py -- the regex drifted"
    return names


_REGISTERED_TOOLS = _registered_jira_tools()


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
    """Everything after the closing frontmatter delimiter. Splits on the
    *first* '\\n---' after the opening fence, so a horizontal rule ('---')
    written into the body itself would be read as the fence and truncate
    the body there -- none of the current role files do that, but a future
    one must not either."""
    _, rest = text.split("---\n", 1)
    _, body = rest.split("\n---", 1)
    return body


def _tools_line(text: str) -> list[str]:
    fields = _parse_frontmatter(text)
    assert "tools" in fields, "role file frontmatter carries no 'tools:' line"
    return [t.strip() for t in fields["tools"].split(",")]


def _skill_body(role: str) -> str:
    """The role's own prose, read from `skills/roles/<role>/SKILL.md` --
    DG-402 moved it there from `agents/<role>.md`, which is now a generated
    adapter carrying no role rule of its own. Strips only the YAML
    frontmatter block (`text.split("---", 2)`, the same split the generator
    itself uses), not a second `---` later in the body -- a skill file's own
    shape has one between its title block and `<system_prompt>`, which must
    stay in the body this returns."""
    text = (ROLES_DIR / role / "SKILL.md").read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"skills/roles/{role}/SKILL.md has no closed frontmatter"
    return parts[2]


def _jira_tools_named_in_body(text: str) -> set[str]:
    """Every *registered* `jira_xxx` tool name the body mentions -- bare
    matches are intersected with `_REGISTERED_TOOLS` so a non-tool mention
    like `src/jira_mcp` never counts as a tool being named."""
    body = _body(text)
    bare = set(_BARE_JIRA_TOOL.findall(body))
    return bare & _REGISTERED_TOOLS


def _jira_tools_named_in_text(text: str) -> set[str]:
    """Like :func:`_jira_tools_named_in_body`, but for text that is already
    a body (e.g. a skill file's own prose) rather than a whole role file
    with a frontmatter fence to strip first."""
    bare = set(_BARE_JIRA_TOOL.findall(text))
    return bare & _REGISTERED_TOOLS


def _granted_bare_names(tools: list[str]) -> set[str]:
    return {t[len(_MCP_PREFIX) :] for t in tools if t.startswith(_MCP_PREFIX + "jira_")}


@pytest.mark.parametrize("role", ["worker", "reviewer", "manager"])
def test_every_jira_tool_named_in_the_skill_body_is_granted_in_tools(
    role: str,
) -> None:
    """DG-402: the grant lives in the generated `agents/<role>.md`; the
    prose naming a tool now lives in `skills/roles/<role>/SKILL.md`. Reading
    `named` from the stub adapter's own body would pass vacuously -- the
    generator never writes a `jira_...` mention there -- which is exactly
    the silently-stopped-testing-anything failure mode a migration must not
    introduce."""
    agent_text = (AGENTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    tools = _tools_line(agent_text)
    granted = _granted_bare_names(tools)
    named = _jira_tools_named_in_text(_skill_body(role))
    missing = named - granted
    assert not missing, (
        f"{role}'s skill names {sorted(missing)} in its body but "
        f"agents/{role}.md does not grant it in the 'tools:' frontmatter "
        f"line -- the role could never call it"
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
    """DG-402: this text now lives in the skill, not the generated adapter --
    `agents/<role>.md` still *grants* jira_get_comments (checked above), but
    the instruction to use it first is the role's own prose."""
    for role in ("worker", "reviewer"):
        body = _skill_body(role)
        assert "jira_get_comments" in body, (
            f"skills/roles/{role}/SKILL.md never tells the role to read "
            "comments before starting or reviewing, though agents/"
            f"{role}.md grants jira_get_comments"
        )
        assert "binding" in body, (
            f"skills/roles/{role}/SKILL.md does not say a Boss decision "
            "recorded in a comment is binding"
        )


def test_worker_and_reviewer_text_gates_a_boss_decision_on_authorship() -> None:
    """Reviewer follow-up on PR #139: a comment's body can claim anything,
    including 'as the Boss' -- only the comment's own author field can say
    who actually wrote it. The role text must point at that field, not at
    phrasing inside the comment, and no name or email belongs in this repo
    text either way. DG-402: this text now lives in the skill, not the
    generated adapter."""
    for role in ("worker", "reviewer"):
        body = _skill_body(role)
        assert "author" in body, (
            f"skills/roles/{role}/SKILL.md does not say a Boss decision is "
            "gated on the comment's author field -- a comment body claiming "
            "to speak for the Boss could be read as binding"
        )
        assert "@" not in body, (
            f"skills/roles/{role}/SKILL.md names an email address -- no "
            "person's contact detail belongs in this repo's instruction text"
        )


# --- Proof the derivation above actually catches the realistic mutations
# the ticket and the review name: removing the tool from one real file, a
# near-miss spelling in the grant, a new role file that names a Jira tool
# in its body but omits it from 'tools:', and the false positive the first
# version of this file was vulnerable to.


def test_mutation_removing_jira_get_comments_from_tools_line_is_caught() -> None:
    """DG-402: the grant is mutated on the generated adapter; the name is
    still read from the real (unmutated) skill body, since that is where
    the worker is actually told to call it."""
    agent_text = (AGENTS_DIR / "worker.md").read_text(encoding="utf-8")
    mutated_agent = agent_text.replace(f", {_MCP_PREFIX}jira_get_comments", "")
    tools = _tools_line(mutated_agent)
    granted = _granted_bare_names(tools)
    named = _jira_tools_named_in_text(_skill_body("worker"))
    assert "jira_get_comments" in (named - granted), (
        "removing jira_get_comments from the tools line must still be "
        "caught now that the check also requires the name to be registered"
    )


def test_mutation_near_miss_spelling_in_the_grant_is_caught() -> None:
    """The grant itself gets a plausible typo (missing the trailing 's')
    while the skill still names the real, correctly-spelled tool -- exact
    string matching must not treat these as the same tool."""
    agent_text = (AGENTS_DIR / "worker.md").read_text(encoding="utf-8")
    mutated_agent = agent_text.replace(
        f"{_MCP_PREFIX}jira_get_comments", f"{_MCP_PREFIX}jira_get_comment"
    )
    tools = _tools_line(mutated_agent)
    granted = _granted_bare_names(tools)
    named = _jira_tools_named_in_text(_skill_body("worker"))
    assert "jira_get_comments" in (named - granted), (
        "a near-miss spelling in the tools line grant must not be read as "
        "granting the real tool the skill names"
    )


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


def test_a_prose_mention_of_the_mcp_server_path_is_not_treated_as_a_tool(
    tmp_path: Path,
) -> None:
    """The false positive the bare regex was vulnerable to: a role body
    mentioning `src/jira_mcp` (or any other non-tool `jira_...` word) must
    not be read as naming a tool it then appears to be missing."""
    fixture = tmp_path / "scribe.md"
    fixture.write_text(
        "---\n"
        "name: scribe\n"
        "description: A throwaway fixture role.\n"
        "model: claude-sonnet-5\n"
        "tools: Read, Grep\n"
        "---\n"
        "\n"
        "<system_prompt>\n"
        "  Never touch src/jira_mcp; it is out of scope for this role.\n"
        "</system_prompt>\n",
        encoding="utf-8",
    )
    text = fixture.read_text(encoding="utf-8")
    tools = _tools_line(text)
    granted = _granted_bare_names(tools)
    named = _jira_tools_named_in_body(text)
    assert named == set(), (
        "a prose mention of 'src/jira_mcp' was read as naming a registered "
        "tool -- it is a path, not a tool"
    )
    assert not (named - granted)


def test_mutation_removing_the_author_sentence_is_caught() -> None:
    """Mutation proof for the authorship check above: delete the sentence
    and the check must go red. DG-402: the sentence now lives in the skill."""
    for role in ("worker", "reviewer"):
        body = _skill_body(role)
        mutated_body = re.sub(
            r"[^.]*\bauthor\w*\b[^.]*\.", "", body, flags=re.IGNORECASE
        )
        assert "author" not in mutated_body, (
            f"mutation did not remove the author sentence from "
            f"skills/roles/{role}/SKILL.md -- fix the mutation, not the assertion"
        )
