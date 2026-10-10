# mypy: ignore-errors
"""DG-500, DG-501 (REQ-022). ``drunken-install agents`` and ``drunken-install status``.

Explicit targets under ``tmp_path`` throughout; nothing here may reach the real ``~/.claude``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

from core import install

REPO = Path(__file__).resolve().parent.parent


def symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


def make_agents(
    tmp_path: Path, roles: dict[str, str], *, manifest: object = "auto"
) -> Path:
    src = tmp_path / "agents-src"
    src.mkdir()
    for role in roles:
        (src / f"{role}.md").write_bytes(
            f"---\nname: {role}\n---\nbody {role}\n".encode()
        )
    (src / "INDEX.md").write_bytes(b"# agents index\n")
    if manifest == "auto":
        manifest = {
            r: {"skill": s, "model": "m", "tools": ["Read"]} for r, s in roles.items()
        }
    if manifest is not None:
        (src / "_sources.json").write_text(json.dumps(manifest), encoding="utf-8")
    return src


def installed_skills(tmp_path: Path, names: list[str]) -> Path:
    root = tmp_path / "skills-target"
    for name in names:
        (root / name).mkdir(parents=True)
        (root / name / "SKILL.md").write_bytes(b"skill\n")
    return root


ROLES = {"manager": "manager", "worker": "worker"}


class TestInstallAgents:
    def test_installs_every_adapter_byte_for_byte_when_the_skills_are_there(
        self, tmp_path
    ):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "agents-target"

        result = install.install_agents(target, skills, source=src)

        assert {a.name: a.status for a in result.agents} == {
            "manager": "new",
            "worker": "new",
        }
        assert (target / "worker.md").read_bytes() == (src / "worker.md").read_bytes()
        assert (target / "INDEX.md").read_bytes() == b"# agents index\n"

    def test_a_rerun_changes_nothing(self, tmp_path):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "agents-target"
        install.install_agents(target, skills, source=src)

        again = install.install_agents(target, skills, source=src)

        assert {a.status for a in again.agents} == {"unchanged"}
        assert again.index_updated is False

    def test_dry_run_writes_nothing(self, tmp_path):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "never"

        install.install_agents(target, skills, source=src, apply=False)

        assert not target.exists()

    def test_an_installed_agent_not_shipped_is_reported_and_kept(self, tmp_path):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "agents-target"
        target.mkdir()
        (target / "mine.md").write_text("mine\n", encoding="utf-8")

        result = install.install_agents(target, skills, source=src)

        assert result.orphans == ["mine"]
        assert (target / "mine.md").exists()


class TestAllOrNothing:
    """DG-459: a short or absent manifest used to install the other roles anyway."""

    def _nothing_written(self, target: Path) -> None:
        assert not target.exists() or not list(target.iterdir())

    def test_an_absent_manifest_installs_nothing(self, tmp_path):
        src = make_agents(tmp_path, ROLES, manifest=None)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "agents-target"

        with pytest.raises(install.InstallRefusedError):
            install.install_agents(target, skills, source=src)

        self._nothing_written(target)

    def test_a_manifest_that_lacks_one_role_installs_none_of_them(self, tmp_path):
        src = make_agents(
            tmp_path,
            ROLES,
            manifest={"manager": {"skill": "manager", "model": "m", "tools": []}},
        )
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "agents-target"

        with pytest.raises(install.InstallRefusedError) as raised:
            install.install_agents(target, skills, source=src)

        assert "worker" in str(raised.value)
        self._nothing_written(target)

    def test_a_missing_skill_installs_no_agent_at_all(self, tmp_path):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager"])  # worker's skill absent
        target = tmp_path / "agents-target"

        with pytest.raises(install.InstallRefusedError) as raised:
            install.install_agents(target, skills, source=src)

        assert "'worker'" in str(raised.value)
        self._nothing_written(target)

    @pytest.mark.parametrize(
        "manifest",
        [
            [],
            {},
            {"manager": {}},
            {"manager": {"skill": ""}},
            {"manager": {"skill": 5}},
            "text",
        ],
    )
    def test_a_malformed_manifest_refuses(self, tmp_path, manifest):
        src = make_agents(tmp_path, {"manager": "manager"}, manifest=manifest)
        skills = installed_skills(tmp_path, ["manager"])

        with pytest.raises(install.InstallRefusedError):
            install.install_agents(tmp_path / "t", skills, source=src)

    def test_a_skill_folder_the_person_linked_still_satisfies_the_gate(self, tmp_path):
        # The gate asks whether the skill exists, as the shell script did. A person who linked a
        # skill folder made that choice; refusing the agents for it would punish a dev checkout.
        src = make_agents(tmp_path, {"manager": "manager"})
        skills = tmp_path / "skills-target"
        skills.mkdir()
        real = tmp_path / "real"
        real.mkdir()
        (real / "SKILL.md").write_bytes(b"x\n")
        symlink_or_skip(skills / "manager", real, directory=True)

        result = install.install_agents(tmp_path / "t", skills, source=src)

        assert [a.status for a in result.agents] == ["new"]


class TestLinks:
    def test_a_target_that_is_a_link_is_refused(self, tmp_path):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        symlink_or_skip(link, real, directory=True)

        with pytest.raises(install.InstallRefusedError):
            install.install_agents(link, skills, source=src)

        assert list(real.iterdir()) == []

    def test_an_adapter_file_that_is_a_link_is_refused_and_the_other_installs(
        self, tmp_path
    ):
        src = make_agents(tmp_path, ROLES)
        skills = installed_skills(tmp_path, ["manager", "worker"])
        target = tmp_path / "agents-target"
        target.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("do not touch\n", encoding="utf-8")
        symlink_or_skip(target / "worker.md", outside)

        result = install.install_agents(target, skills, source=src)

        assert {a.name: a.status for a in result.agents}["worker"] == "refused"
        assert outside.read_text(encoding="utf-8") == "do not touch\n"
        assert (target / "manager.md").exists()


class TestThePackagedAdaptersAreFresh:
    def test_the_shipped_adapters_equal_what_the_generator_writes_from_the_skills(
        self, tmp_path
    ):
        sys.path.insert(0, str(REPO / "scripts" / "install"))
        try:
            import _generate_agents as gen
        finally:
            sys.path.remove(str(REPO / "scripts" / "install"))
        out = tmp_path / "generated"

        gen.generate(out, REPO / "skills", REPO / "agents" / "_sources.json")

        for generated in sorted(out.glob("*.md")):
            shipped = (REPO / "agents" / generated.name).read_bytes()
            assert generated.read_bytes() == shipped, (
                f"agents/{generated.name} is stale: regenerate it with scripts/install/install_agents"
            )


class TestStatus:
    def _installed(self, tmp_path):
        skills_src = tmp_path / "skills-src"
        for name in ("alpha", "beta"):
            (skills_src / "g" / name).mkdir(parents=True)
            (skills_src / "g" / name / "SKILL.md").write_bytes(f"{name} v1\n".encode())
        (skills_src / "INDEX.md").write_bytes(b"# i\n")
        agents_src = make_agents(tmp_path, {"worker": "alpha"})
        skills_t = tmp_path / "skills-t"
        agents_t = tmp_path / "agents-t"
        install.install_skills(skills_t, source=skills_src)
        install.install_agents(agents_t, skills_t, source=agents_src)
        return skills_src, agents_src, skills_t, agents_t

    def test_an_unchanged_install_is_up_to_date(self, tmp_path):
        skills_src, agents_src, skills_t, agents_t = self._installed(tmp_path)

        report = install.status(
            skills_t, agents_t, skills_source=skills_src, agents_source=agents_src
        )

        assert report.up_to_date

    def test_it_names_what_an_update_would_change_and_changes_nothing(self, tmp_path):
        skills_src, agents_src, skills_t, agents_t = self._installed(tmp_path)
        (skills_src / "g" / "alpha" / "SKILL.md").write_bytes(b"alpha v2\n")
        (agents_src / "worker.md").write_bytes(b"new worker\n")
        before = sorted(
            (p.relative_to(tmp_path).as_posix(), p.read_bytes())
            for p in tmp_path.rglob("*")
            if p.is_file()
        )

        report = install.status(
            skills_t, agents_t, skills_source=skills_src, agents_source=agents_src
        )

        assert report.skills_changes == ["updated: alpha"]
        assert report.agents_changes == ["updated: worker"]
        assert not report.up_to_date
        after = sorted(
            (p.relative_to(tmp_path).as_posix(), p.read_bytes())
            for p in tmp_path.rglob("*")
            if p.is_file()
        )
        assert after == before, "status wrote something"

    def test_status_on_a_machine_with_nothing_installed_creates_no_folder(
        self, tmp_path
    ):
        skills_src, agents_src, _, _ = self._installed(tmp_path)
        fresh_skills = tmp_path / "fresh-skills"
        fresh_agents = tmp_path / "fresh-agents"

        report = install.status(
            fresh_skills,
            fresh_agents,
            skills_source=skills_src,
            agents_source=agents_src,
        )

        assert any(c.startswith("new:") for c in report.skills_changes)
        assert not fresh_skills.exists() and not fresh_agents.exists()

    def test_the_command_prints_the_changelog_and_exits_zero(self, tmp_path, capsys):
        code = install.main(
            [
                "status",
                "--target",
                str(tmp_path / "s"),
                "--agents-target",
                str(tmp_path / "a"),
            ]
        )

        out = capsys.readouterr().out
        assert code == 0
        assert "an update would change" in out and "changelog" in out


class TestAllCommand:
    def test_all_installs_skills_then_agents_into_the_given_targets(
        self, tmp_path, capsys
    ):
        skills_t = tmp_path / "skills-t"
        agents_t = tmp_path / "agents-t"

        code = install.main(
            ["all", "--target", str(skills_t), "--agents-target", str(agents_t)]
        )

        assert code == 0, capsys.readouterr().out
        assert (skills_t / "worker" / "SKILL.md").exists()
        assert (agents_t / "worker.md").exists()

    def test_agents_alone_refuse_when_the_skills_are_not_installed(
        self, tmp_path, capsys
    ):
        code = install.main(
            [
                "agents",
                "--target",
                str(tmp_path / "empty-skills"),
                "--agents-target",
                str(tmp_path / "agents-t"),
            ]
        )

        assert code == 1
        assert not (tmp_path / "agents-t").exists()


class TestTheChangelog:
    """DG-501: a change to how the flow works has an entry; the version this tree declares has one."""

    def _top(self) -> str:
        text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        heading, _ = install.newest_changelog_section(text)
        return heading

    def _version(self) -> str:
        text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)

    def test_the_newest_heading_is_the_declared_version_or_unreleased(self):
        top = self._top()

        assert top.startswith("Unreleased") or top.split()[0] == self._version(), (
            f"CHANGELOG.md's newest heading is {top!r} but pyproject declares {self._version()!r}"
        )

    def test_the_newest_section_has_a_body(self):
        text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")

        _, body = install.newest_changelog_section(text)

        assert len(body.split()) > 20

    def test_a_section_is_found_and_cut_at_the_next_heading(self):
        heading, body = install.newest_changelog_section(
            "# Changelog\n\n## 3.0.0\nnew things\n\n## 2.0.0\nold things\n"
        )

        assert (heading, body) == ("3.0.0", "new things")
