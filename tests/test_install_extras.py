# mypy: ignore-errors
"""DG-512 (operator order): drunken-install extras — the drunken-extras plugin's optional skills and 15
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
    # A second file, so an install can be interrupted after the first and before the second —
    # the "incomplete" case a single-file skill cannot exercise.
    (skills / "alpha-skill" / "extra.md").write_text(
        "a second file of the alpha-skill folder.\n", encoding="utf-8"
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


class TestAnInterruptedInstallIsReportedIncomplete:
    """DG-512 reviewer MEDIUM finding, round 2: a skill folder that was partly written —
    `alpha-skill/SKILL.md` identical to the source but `alpha-skill/extra.md` never landed — must
    not read as fully up to date. The old `_plan_skill_action` required `(dest / r).is_file()`
    before counting a file as changed, so a missing file was computed into `changed` and then
    silently dropped by the `existing_mismatch` filter, and the folder came back `("alpha-skill",
    "unchanged")` with nothing to write."""

    @staticmethod
    def _interrupt(skills_target: Path) -> None:
        (skills_target / "alpha-skill" / "extra.md").unlink()

    def test_plan_reports_incomplete_not_unchanged(self, tmp_path, source):
        skills_target = tmp_path / "skills"
        agents_target = tmp_path / "agents"
        ext.install_extras(skills_target, agents_target, source=source, apply=True)
        self._interrupt(skills_target)

        result = ext.plan_extras(skills_target, agents_target, source=source)

        action = next(a for a in result.skills if a.name == "alpha-skill")
        assert action.status == "incomplete", (
            f"a folder missing one of its files must not read as 'unchanged' "
            f"(got {action.status!r})"
        )
        assert action.files == ["extra.md"]

    def test_status_reports_the_incomplete_skill(self, tmp_path, source):
        skills_target = tmp_path / "skills"
        agents_target = tmp_path / "agents"
        ext.install_extras(skills_target, agents_target, source=source, apply=True)
        self._interrupt(skills_target)

        report = ext.extras_status(skills_target, agents_target, source=source)

        assert any("alpha-skill" in line and "incomplete" in line for line in report), (
            report
        )

    def test_apply_fills_only_the_missing_file(self, tmp_path, source):
        skills_target = tmp_path / "skills"
        agents_target = tmp_path / "agents"
        ext.install_extras(skills_target, agents_target, source=source, apply=True)
        self._interrupt(skills_target)
        skill_md_before = (skills_target / "alpha-skill" / "SKILL.md").read_bytes()

        ext.install_extras(skills_target, agents_target, source=source, apply=True)

        assert (skills_target / "alpha-skill" / "extra.md").read_bytes() == (
            source / "skills" / "alpha-skill" / "extra.md"
        ).read_bytes(), "the missing file must be filled in"
        assert (
            skills_target / "alpha-skill" / "SKILL.md"
        ).read_bytes() == skill_md_before, (
            "a file that already matched must not be rewritten"
        )

    def test_a_differing_file_in_the_same_folder_is_still_reported_and_untouched(
        self, tmp_path, source
    ):
        skills_target = tmp_path / "skills"
        agents_target = tmp_path / "agents"
        ext.install_extras(skills_target, agents_target, source=source, apply=True)
        self._interrupt(skills_target)
        (skills_target / "alpha-skill" / "SKILL.md").write_text(
            "hand-edited, not ours\n", encoding="utf-8"
        )

        result = ext.install_extras(
            skills_target, agents_target, source=source, apply=True
        )

        action = next(a for a in result.skills if a.name == "alpha-skill")
        assert action.status == "differs", (
            f"a folder with one file that differs must report 'differs', even while "
            f"another file in it is also missing (got {action.status!r})"
        )
        assert (skills_target / "alpha-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "hand-edited, not ours\n", "the differing file must never be overwritten"
        assert (skills_target / "alpha-skill" / "extra.md").read_bytes() == (
            source / "skills" / "alpha-skill" / "extra.md"
        ).read_bytes(), (
            "the missing file must still be filled even when a sibling differs"
        )

    def test_mutation_reverting_the_missing_file_check_reproduces_the_bug(
        self, tmp_path, source
    ):
        """Restore the old shape — classify a folder by `_differs` filtered through
        `(dest / r).is_file()` — and show the exact bug resurfaces: the interrupted folder reads
        as `"unchanged"` again, nothing to write."""
        original = ext._plan_skill_action

        def buggy(name: str, src: Path, target_root: Path):
            dest = target_root / name
            if ext._is_link(dest):
                return ext._Action(
                    name, "refused", reason=f"{dest} is a link, not touched"
                )
            rels = [p.relative_to(src) for p in sorted(src.rglob("*")) if p.is_file()]
            if not dest.exists():
                return ext._Action(name, "new", [r.as_posix() for r in rels])
            changed = [r.as_posix() for r in rels if ext._differs(src / r, dest / r)]
            if changed:
                existing_mismatch = any(
                    (dest / r).is_file() and ext._differs(src / r, dest / r)
                    for r in rels
                )
                if existing_mismatch:
                    return ext._Action(
                        name,
                        "differs",
                        reason=f"{dest} exists and differs; not overwritten",
                    )
            return ext._Action(name, "unchanged")

        ext._plan_skill_action = buggy
        try:
            skills_target = tmp_path / "skills"
            agents_target = tmp_path / "agents"
            ext.install_extras(skills_target, agents_target, source=source, apply=True)
            self._interrupt(skills_target)

            result = ext.plan_extras(skills_target, agents_target, source=source)

            action = next(a for a in result.skills if a.name == "alpha-skill")
            assert action.status == "unchanged", (
                "the mutation should reproduce the old bug (an interrupted folder reads as "
                f"'unchanged') -- got {action.status!r} instead, so the mutation stopped "
                "mutating anything real"
            )
        finally:
            ext._plan_skill_action = original
