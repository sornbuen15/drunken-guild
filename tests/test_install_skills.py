# mypy: ignore-errors
"""DG-499 (REQ-022). ``drunken-install skills`` installs and updates the packaged skills.

Every test passes an explicit target under ``tmp_path``: nothing here may ever reach the real
``~/.claude`` (DG-458 is a PowerShell installer that once did).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from core import install

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"


def tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.startswith(".drunken-install-")
    }


def make_source(tmp_path: Path, skills: dict[str, dict[str, str]]) -> Path:
    src = tmp_path / "src-skills"
    for name, files in skills.items():
        for rel, text in files.items():
            path = src / "group" / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    (src / "INDEX.md").write_bytes(b"# index\n")
    return src


TWO = {
    "alpha": {"SKILL.md": "alpha v1\n", "extra/notes.md": "n1\n"},
    "beta": {"SKILL.md": "beta v1\n"},
}


def symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


class TestInstallAndUpdate:
    def test_a_fresh_install_copies_every_file_byte_for_byte(self, tmp_path):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "claude" / "skills"

        result = install.install_skills(target, source=src)

        assert sorted(a.name for a in result.skills) == ["alpha", "beta"]
        assert {a.status for a in result.skills} == {"new"}
        assert tree(target) == {
            "alpha/SKILL.md": b"alpha v1\n",
            "alpha/extra/notes.md": b"n1\n",
            "beta/SKILL.md": b"beta v1\n",
            "INDEX.md": b"# index\n",
        }

    def test_a_second_run_changes_nothing(self, tmp_path):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        install.install_skills(target, source=src)
        before = {p: p.stat().st_mtime_ns for p in target.rglob("*") if p.is_file()}

        second = install.install_skills(target, source=src)

        assert {a.status for a in second.skills} == {"unchanged"}
        assert second.index_updated is False
        assert {
            p: p.stat().st_mtime_ns for p in target.rglob("*") if p.is_file()
        } == before, "an unchanged file must not be rewritten"

    def test_an_update_rewrites_only_the_files_that_differ(self, tmp_path):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        install.install_skills(target, source=src)
        (src / "group" / "alpha" / "SKILL.md").write_bytes(b"alpha v2\n")
        beta_before = (target / "beta" / "SKILL.md").stat().st_mtime_ns

        result = install.install_skills(target, source=src)

        by_name = {a.name: a for a in result.skills}
        assert by_name["alpha"].status == "updated" and by_name["alpha"].files == [
            "SKILL.md"
        ]
        assert by_name["beta"].status == "unchanged"
        assert (target / "alpha" / "SKILL.md").read_bytes() == b"alpha v2\n"
        assert (target / "beta" / "SKILL.md").stat().st_mtime_ns == beta_before

    def test_a_hand_edited_installed_file_is_put_back(self, tmp_path):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        install.install_skills(target, source=src)
        (target / "alpha" / "SKILL.md").write_text("locally edited\n", encoding="utf-8")

        install.install_skills(target, source=src)

        assert (target / "alpha" / "SKILL.md").read_bytes() == b"alpha v1\n"

    def test_dry_run_writes_nothing_at_all(self, tmp_path):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "never-created"

        result = install.install_skills(target, source=src, apply=False)

        assert {a.status for a in result.skills} == {"new"}
        assert not target.exists()

    def test_an_interrupted_write_leaves_the_old_file_and_no_temp_file(
        self, tmp_path, monkeypatch
    ):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        install.install_skills(target, source=src)
        (src / "group" / "alpha" / "SKILL.md").write_bytes(b"alpha v2\n")

        def boom(*_a, **_k):
            raise OSError("disk went away")

        monkeypatch.setattr(install.os, "replace", boom)
        with pytest.raises(OSError):
            install.install_skills(target, source=src)
        monkeypatch.undo()

        assert (target / "alpha" / "SKILL.md").read_bytes() == b"alpha v1\n"
        assert not [p for p in target.rglob(".drunken-install-*")]


class TestNeverThroughALink:
    def test_a_target_skill_folder_that_is_a_link_is_refused_and_the_rest_install(
        self, tmp_path
    ):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        target.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        symlink_or_skip(target / "alpha", elsewhere, directory=True)

        result = install.install_skills(target, source=src)

        by_name = {a.name: a for a in result.skills}
        assert by_name["alpha"].status == "refused"
        assert list(elsewhere.iterdir()) == [], (
            "nothing may be written through the link"
        )
        assert (target / "beta" / "SKILL.md").read_bytes() == b"beta v1\n"

    def test_a_target_root_that_is_a_link_refuses_the_whole_run(self, tmp_path):
        src = make_source(tmp_path, TWO)
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        symlink_or_skip(link, real, directory=True)

        with pytest.raises(install.InstallRefusedError):
            install.install_skills(link, source=src)

        assert list(real.iterdir()) == []

    def test_a_source_symlink_is_refused(self, tmp_path):
        src = make_source(tmp_path, TWO)
        outside = tmp_path / "outside.md"
        outside.write_text("secret\n", encoding="utf-8")
        symlink_or_skip(src / "group" / "beta" / "leak.md", outside)

        with pytest.raises(install.InstallRefusedError):
            install.install_skills(tmp_path / "t", source=src)

    def test_two_skills_with_one_folder_name_are_refused(self, tmp_path):
        src = make_source(tmp_path, {"alpha": {"SKILL.md": "a\n"}})
        other = src / "other-group" / "alpha"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("b\n", encoding="utf-8")

        with pytest.raises(install.InstallRefusedError):
            install.install_skills(tmp_path / "t", source=src)


class TestPruneIsNarrow:
    def _installed_with_orphans(self, tmp_path, monkeypatch):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        install.install_skills(target, source=src)
        for name in ("old-retired", "my-own"):
            (target / name).mkdir()
            (target / name / "SKILL.md").write_text("x\n", encoding="utf-8")
        (target / "plain-retired").write_text("not a skill dir\n", encoding="utf-8")
        monkeypatch.setattr(
            install,
            "retired_names",
            lambda: frozenset({"old-retired", "plain-retired"}),
        )
        return src, target

    def test_without_prune_nothing_is_removed_and_orphans_are_named(
        self, tmp_path, monkeypatch
    ):
        src, target = self._installed_with_orphans(tmp_path, monkeypatch)

        result = install.install_skills(target, source=src)

        assert {o.name: o.kind for o in result.orphans} == {
            "old-retired": "retired",
            "my-own": "unrecognised",
        }
        assert (target / "old-retired").exists() and (target / "my-own").exists()

    def test_prune_alone_lists_and_removes_nothing(self, tmp_path, monkeypatch):
        src, target = self._installed_with_orphans(tmp_path, monkeypatch)

        result = install.install_skills(target, source=src, prune=True)

        assert result.pruned == []
        assert (target / "old-retired").exists()

    def test_prune_apply_removes_only_a_retired_skill_folder(
        self, tmp_path, monkeypatch
    ):
        src, target = self._installed_with_orphans(tmp_path, monkeypatch)

        result = install.install_skills(
            target, source=src, prune=True, prune_apply=True
        )

        assert result.pruned == ["old-retired"]
        assert not (target / "old-retired").exists()
        assert (target / "my-own" / "SKILL.md").exists(), (
            "an unrecognised skill is never removed"
        )
        assert (target / "plain-retired").read_text(
            encoding="utf-8"
        ) == "not a skill dir\n"

    def test_prune_apply_without_prune_is_refused(self, tmp_path):
        src = make_source(tmp_path, TWO)

        with pytest.raises(install.InstallRefusedError):
            install.install_skills(tmp_path / "t", source=src, prune_apply=True)

    def test_a_retired_name_that_is_a_link_is_not_removed(self, tmp_path, monkeypatch):
        src, target = self._installed_with_orphans(tmp_path, monkeypatch)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "keep.txt").write_text("keep\n", encoding="utf-8")
        shutil.rmtree(target / "old-retired")
        symlink_or_skip(target / "old-retired", elsewhere, directory=True)

        install.install_skills(target, source=src, prune=True, prune_apply=True)

        assert (elsewhere / "keep.txt").exists()


class TestTheCommand:
    def test_main_installs_into_the_given_target(self, tmp_path, capsys):
        target = tmp_path / "t"

        code = install.main(["skills", "--target", str(target)])

        out = capsys.readouterr().out
        assert code == 0, out
        assert (target / "flow" / "prd" / "SKILL.md").exists() is False, (
            "installs by folder name"
        )
        assert (target / "prd" / "SKILL.md").read_bytes() == (
            SKILLS / "flow" / "prd" / "SKILL.md"
        ).read_bytes()
        assert "[+] installed" in out

    def test_main_dry_run_says_so_and_writes_nothing(self, tmp_path, capsys):
        target = tmp_path / "t"

        code = install.main(["skills", "--target", str(target), "--dry-run"])

        assert code == 0
        assert not target.exists()
        assert "dry run" in capsys.readouterr().out

    def test_main_exits_one_when_a_skill_is_refused(self, tmp_path, capsys):
        target = tmp_path / "t"
        target.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        symlink_or_skip(target / "prd", elsewhere, directory=True)

        code = install.main(["skills", "--target", str(target)])

        assert code == 1
        assert "refused" in capsys.readouterr().out


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash to run the script")
class TestSameResultAsTheScript:
    """Differential: the old script and this command leave the same tree from the same source."""

    def test_the_tree_equals_install_skills_sh(self, tmp_path):
        copy = tmp_path / "repo"
        shutil.copytree(REPO / "skills", copy / "skills")
        shutil.copytree(REPO / "scripts" / "install", copy / "scripts" / "install")
        home = tmp_path / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home)}
        done = subprocess.run(
            ["bash", str(copy / "scripts" / "install" / "install_skills.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            pytest.skip(
                f"the script cannot run in this environment: {done.stderr[-200:]}"
            )
        scripted = tree(home / ".claude" / "skills")

        ours_target = tmp_path / "ours"
        install.install_skills(ours_target, source=copy / "skills")

        assert tree(ours_target) == scripted


class TestALinkPlantedAfterThePlanIsNotFollowed:
    """Review of #186 (BLOCK): only the plan checked for a link, so one planted between the plan and
    the write was followed, and the shipped files landed in the folder it pointed at."""

    def test_a_skill_folder_turned_into_a_link_before_the_write_is_refused(
        self, tmp_path, monkeypatch
    ):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        target.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        real_plan = install._plan_skill

        def plan_then_plant(name, folder, root):
            action = real_plan(name, folder, root)
            if name == "alpha" and not (root / "alpha").exists():
                symlink_or_skip(root / "alpha", elsewhere, directory=True)
            return action

        monkeypatch.setattr(install, "_plan_skill", plan_then_plant)

        with pytest.raises(install.InstallRefusedError):
            install.install_skills(target, source=src)

        assert list(elsewhere.iterdir()) == [], (
            "the files were written through the link"
        )

    def test_a_nested_folder_turned_into_a_link_inside_a_skill_is_refused(
        self, tmp_path
    ):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        (target / "alpha").mkdir(parents=True)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        symlink_or_skip(target / "alpha" / "extra", elsewhere, directory=True)

        result = install.install_skills(target, source=src)

        assert {a.name: a.status for a in result.skills}["alpha"] == "refused"
        assert list(elsewhere.iterdir()) == []


class TestPruneNamesMustBePlainNames:
    def test__prune_never_removes_a_parent_looking_name(self, tmp_path):
        root = tmp_path / "root"
        target = root / "skills"
        target.mkdir(parents=True)
        (root / "keep.txt").write_bytes(b"keep" + bytes([10]))

        removed = install._prune(
            target,
            [
                install.Orphan("..", "retired"),
                install.Orphan("a/b", "retired"),
                install.Orphan(".", "retired"),
            ],
        )

        assert removed == []
        assert (root / "keep.txt").exists() and target.exists()

    def test_hostile_lines_in_the_retired_list_are_ignored(self, tmp_path, monkeypatch):
        fake = tmp_path / "scripts" / "install"
        fake.mkdir(parents=True)
        (fake / "retired_skills.txt").write_bytes(
            b"# comment\nold-one\n..\n../../x\na/b\nc:d\n.\n"
        )
        monkeypatch.setattr(install, "_package_dir", lambda name: tmp_path / name)

        assert install.retired_names() == frozenset({"old-one"})


class TestARootLinkPlantedAfterThePlan:
    def test_the_target_root_turned_into_a_link_before_the_write_is_refused(
        self, tmp_path, monkeypatch
    ):
        src = make_source(tmp_path, TWO)
        target = tmp_path / "t"
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        real_plan = install._plan_skill

        def plan_then_plant(name, folder, root):
            action = real_plan(name, folder, root)
            if not root.exists():
                symlink_or_skip(root, elsewhere, directory=True)
            return action

        monkeypatch.setattr(install, "_plan_skill", plan_then_plant)

        with pytest.raises((install.InstallRefusedError, OSError)):
            install.install_skills(target, source=src)

        assert list(elsewhere.iterdir()) == [], (
            "the files were written through the root link"
        )
