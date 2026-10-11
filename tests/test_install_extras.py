# mypy: ignore-errors
"""DG-515 (operator order): drunken-install extras — the drunken-extras plugin's 16 skills and 15
agents reach a machine the same way the core skills/agents do, through the wheel, with no clone.

Plan by default; ``apply=True`` writes. Never removes anything — there is no prune here. An agent
file that already exists and differs from the packaged one is reported, never overwritten, the
same rule ``install_agents`` already enforces for role adapters.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import install_extras as ext


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    """A tiny, fake drunken-extras tree: two skills, two agents, one of each name-mismatched."""
    root = tmp_path / "drunken-extras"
    skills = root / "skills"
    agents = root / "agents"
    (skills / "alpha-skill").mkdir(parents=True)
    (skills / "alpha-skill" / "SKILL.md").write_text(
        "---\nname: alpha-skill\ndescription: a fake extra skill.\n---\nbody\n",
        encoding="utf-8",
    )
    (skills / "beta-skill").mkdir(parents=True)
    (skills / "beta-skill" / "SKILL.md").write_text(
        "---\nname: beta-skill\ndescription: another fake extra skill.\n---\nbody\n",
        encoding="utf-8",
    )
    agents.mkdir(parents=True)
    (agents / "alpha-agent.md").write_text(
        "---\nname: alpha-agent\ndescription: a fake extra agent.\nmodel: claude-sonnet-5\n"
        "tools: Read\n---\n<system_prompt>x</system_prompt>\n",
        encoding="utf-8",
    )
    (agents / "beta-agent.md").write_text(
        "---\nname: beta-agent\ndescription: another fake extra agent.\nmodel: claude-sonnet-5\n"
        "tools: Read\n---\n<system_prompt>y</system_prompt>\n",
        encoding="utf-8",
    )
    return root


def test_plan_lists_everything_as_new_and_writes_nothing(tmp_path, source):
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"

    result = ext.plan_extras(skills_target, agents_target, source=source)

    names = {a.name: a.status for a in result.skills} | {
        a.name: a.status for a in result.agents
    }
    assert names == {
        "alpha-skill": "new",
        "beta-skill": "new",
        "alpha-agent": "new",
        "beta-agent": "new",
    }
    assert not skills_target.exists()
    assert not agents_target.exists()


def test_apply_writes_the_skills_and_agents(tmp_path, source):
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"

    result = ext.install_extras(skills_target, agents_target, source=source, apply=True)

    assert result.applied is True
    assert (skills_target / "alpha-skill" / "SKILL.md").read_bytes() == (
        source / "skills" / "alpha-skill" / "SKILL.md"
    ).read_bytes()
    assert (agents_target / "alpha-agent.md").is_file()
    assert (agents_target / "beta-agent.md").is_file()


def test_apply_is_idempotent(tmp_path, source):
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"
    ext.install_extras(skills_target, agents_target, source=source, apply=True)

    second = ext.install_extras(skills_target, agents_target, source=source, apply=True)

    assert {a.status for a in second.skills} == {"unchanged"}
    assert {a.status for a in second.agents} == {"unchanged"}


def test_only_filters_to_the_named_items(tmp_path, source):
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"

    result = ext.install_extras(
        skills_target,
        agents_target,
        source=source,
        apply=True,
        only=["alpha-skill", "alpha-agent"],
    )

    assert {a.name for a in result.skills} == {"alpha-skill"}
    assert {a.name for a in result.agents} == {"alpha-agent"}
    assert (skills_target / "alpha-skill").exists()
    assert not (skills_target / "beta-skill").exists()
    assert not (agents_target / "beta-agent.md").exists()


def test_an_unknown_only_name_is_refused(tmp_path, source):
    with pytest.raises(ext.InstallRefusedError, match="not-a-real-one"):
        ext.install_extras(
            tmp_path / "skills",
            tmp_path / "agents",
            source=source,
            apply=True,
            only=["not-a-real-one"],
        )


def test_an_existing_agent_that_differs_is_reported_not_overwritten(tmp_path, source):
    agents_target = tmp_path / "agents"
    agents_target.mkdir(parents=True)
    (agents_target / "alpha-agent.md").write_text(
        "hand-edited, not ours\n", encoding="utf-8"
    )

    result = ext.install_extras(
        tmp_path / "skills", agents_target, source=source, apply=True
    )

    action = next(a for a in result.agents if a.name == "alpha-agent")
    assert action.status == "differs"
    assert (agents_target / "alpha-agent.md").read_text(encoding="utf-8") == (
        "hand-edited, not ours\n"
    )


def test_never_removes_anything_installed_here_but_not_shipped(tmp_path, source):
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"
    ext.install_extras(skills_target, agents_target, source=source, apply=True)

    ext.install_extras(
        skills_target,
        agents_target,
        source=source,
        apply=True,
        only=["alpha-skill", "alpha-agent"],
    )

    assert (skills_target / "beta-skill").exists(), "extras never removes anything"
    assert (agents_target / "beta-agent.md").exists(), "extras never removes anything"


def test_status_reports_missing_and_differs(tmp_path, source):
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"
    agents_target.mkdir(parents=True)
    (agents_target / "alpha-agent.md").write_text("hand-edited\n", encoding="utf-8")

    report = ext.extras_status(skills_target, agents_target, source=source)

    assert any("alpha-skill" in line and "missing" in line for line in report)
    assert any("alpha-agent" in line and "differs" in line for line in report)
