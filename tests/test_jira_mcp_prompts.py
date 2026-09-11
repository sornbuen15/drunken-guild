# mypy: ignore-errors
"""The Jira server's prompts point at a skill; they do not restate a process.

DG-339. `drunken-jira-mcp` shipped five prompts that each described a process
a skill already owns, and described it differently: `init_project` read a
`DESIGN.md` no other surface mentions and called the blocking approval,
`sprint_planning` told the agent to "adjust priorities" on a Jira where
`priority` cannot be set, and treated moving a ticket onto the board as a
status change. A prompt is one more place a rule can be written, which makes
it one more place it can disagree.

Enumerated through the server's own `list_prompts`, not a hard-coded list, so
a prompt added later is held to the same rule without anyone remembering to
add it here.
"""

import asyncio
import re
from pathlib import Path

import pytest

from jira_mcp import server

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A skill exists when the generated index lists it by name.
INDEXED_SKILLS = set(
    re.findall(
        r"^- `([a-z0-9-]+)`", (REPO_ROOT / "skills" / "INDEX.md").read_text(), re.M
    )
)

#: Things a prompt must not tell an agent, each for a reason that holds on
#: every instance this server talks to.
FORBIDDEN = {
    r"\bpriorit(y|ies)\b": "priority cannot be set on a team-managed project; urgency is a label",
    r"DESIGN\.md": "no project document is called DESIGN.md; see the project-docs skill",
    r"request_boss_approval(?!_async)": "the blocking approval is the fallback, never the default",
}


def _prompts() -> dict[str, str]:
    async def collect() -> dict[str, str]:
        texts = {}
        for prompt in await server.mcp.list_prompts():
            result = await server.mcp.get_prompt(prompt.name, {})
            texts[prompt.name] = "\n".join(m.content.text for m in result.messages)
        return texts

    return asyncio.run(collect())


PROMPTS = _prompts()


def test_the_server_still_offers_its_prompts() -> None:
    """Guards the guard: an empty listing would make every test below pass."""
    assert {"init_project", "refinement", "sprint_planning"} <= set(PROMPTS)


@pytest.mark.parametrize("name", sorted(PROMPTS))
def test_every_prompt_names_a_skill_that_exists(name) -> None:
    named = set(re.findall(r"`([a-z0-9-]+)`", PROMPTS[name])) & INDEXED_SKILLS
    assert named, (
        f"{name} names no skill from skills/INDEX.md, so it is describing a process "
        "itself -- and a second description is a second thing that can disagree."
    )


@pytest.mark.parametrize("name", sorted(PROMPTS))
def test_every_prompt_says_to_stop_without_its_skill(name) -> None:
    """A project can run this server without the skills installed. The prompt
    must not then improvise the process from its own memory of it."""
    assert re.search(r"not installed", PROMPTS[name]), name


@pytest.mark.parametrize("name", sorted(PROMPTS))
@pytest.mark.parametrize("pattern", sorted(FORBIDDEN))
def test_no_prompt_restates_a_retired_or_impossible_rule(name, pattern) -> None:
    assert not re.search(pattern, PROMPTS[name], re.I), f"{name}: {FORBIDDEN[pattern]}"
