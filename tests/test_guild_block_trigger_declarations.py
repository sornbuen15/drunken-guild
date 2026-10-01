# mypy: ignore-errors
"""DG-429. Every `/command` a guild-block row names must be a trigger the
named skill actually declares in its frontmatter `description` -- otherwise
the row tells an agent to type a command no skill ever fires on.

Reads the guild block and the skills structurally: the block is parsed into
its table rows (not grepped as a blob), and each skill's frontmatter is
parsed with `yaml.safe_load` (not grepped either), so a row that merely
*mentions* a word, or a description that merely *mentions* a skill's own
name, cannot pass. Only an exact `Trigger on /<name>.` sentence inside the
owning skill's parsed description counts.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "skills"

_BACKTICK_SLASH_COMMAND = re.compile(r"`(/[a-z][a-z0-9-]*)`")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _guild_block(text: str) -> str:
    return text.split("<!-- guild-block:start -->", 1)[1].split(
        "<!-- guild-block:end -->", 1
    )[0]


def _slash_commands_in_block(block: str) -> set[str]:
    """Every backtick-wrapped `/word` token in the block's rows -- the
    structural shape every real command already takes there (`` `/build` ``,
    `` `/jira-tickets` ``), as opposed to a bare 'build' mentioned in prose."""
    return {match.lstrip("/") for match in _BACKTICK_SLASH_COMMAND.findall(block)}


def _skill_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    assert match, f"{path} has no YAML frontmatter block"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data


def _skill_declaring(name: str, skills_root: Path) -> Path | None:
    """Structural lookup: the skill whose *parsed* frontmatter `name:` field
    equals `name` -- not a path guess, not a directory-name match."""
    for skill_md in skills_root.rglob("SKILL.md"):
        if _skill_frontmatter(skill_md).get("name") == name:
            return skill_md
    return None


def _missing_trigger_declarations(block: str, skills_root: Path) -> list[str]:
    """One problem string per command the block names that either has no
    skill declaring that `name`, or whose skill's description does not
    carry an exact `Trigger on /<name>.` sentence."""
    problems = []
    for command in sorted(_slash_commands_in_block(block)):
        skill_path = _skill_declaring(command, skills_root)
        if skill_path is None:
            problems.append(f"/{command}: no skill's frontmatter name matches it")
            continue
        description = _skill_frontmatter(skill_path).get("description", "")
        if f"Trigger on /{command}." not in description:
            try:
                shown = skill_path.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                shown = skill_path.as_posix()
            problems.append(
                f"/{command}: {shown} does not declare "
                f"'Trigger on /{command}.' in its description"
            )
    return problems


def test_every_slash_command_in_guild_block_is_declared_as_a_trigger() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    block = _guild_block(text)
    commands = _slash_commands_in_block(block)
    assert commands, "no backtick-wrapped /command found in the guild block"
    problems = _missing_trigger_declarations(block, SKILLS_ROOT)
    assert not problems, "\n".join(problems)


# --- Proof: the checker is shown to fail on the two realistic mutations the
# ticket names, fed through the real functions above, not a bespoke fixture.


def test_check_catches_a_guild_block_command_no_skill_declares() -> None:
    block = "| **situation** | run `/no-such-skill` |\n"
    problems = _missing_trigger_declarations(block, SKILLS_ROOT)
    assert problems == ["/no-such-skill: no skill's frontmatter name matches it"]


def test_check_catches_a_skill_whose_trigger_line_is_removed(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "workflow" / "ask-boss"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: "ask-boss"\ndescription: "Ask the Boss for permission. '
        'Apply before any destructive action."\n---\n\n# Skill\n',
        encoding="utf-8",
    )
    block = "| **situation** | `/ask-boss` |\n"
    problems = _missing_trigger_declarations(block, skills_root)
    assert problems == [
        f"/ask-boss: {(skill_dir / 'SKILL.md').as_posix()} does not declare "
        "'Trigger on /ask-boss.' in its description"
    ]
