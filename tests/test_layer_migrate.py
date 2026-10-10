# mypy: ignore-errors
"""DG-446 (REQ-019, REQ-020). One command moves a project's committed AI layer out.

Back up, untrack, exclude, restore what is missing. Every repository here is real git under
``tmp_path``: the thing under test is what the index and ``git status`` actually say afterwards, and
a mocked git would only prove the author's own assumption about that.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from core import layer_migrate
from core.errors import DrunkenError

IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *IDENTITY, *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, f"git {' '.join(args)}: {done.stderr}"
    return done.stdout


def make_project(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    git("init", "-q", "--initial-branch=main", cwd=root)
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    git("add", "-A", cwd=root)
    git("commit", "-qm", "initial", cwd=root)
    return root


LAYER = {
    "AGENTS.md": "# rules\nbe careful\n",
    "CLAUDE.md": "@AGENTS.md\n",
    ".claude/settings.json": '{"model": "haiku"}\n',
    "main.py": "print('hi')\n",
}


def tracked(root: Path) -> list[str]:
    return git("ls-files", cwd=root).split()


def exclude_text(root: Path) -> str:
    path = root / ".git" / "info" / "exclude"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture
def backups(tmp_path: Path) -> Path:
    return tmp_path / "backups"


class TestMigrates:
    def test_untracks_the_layer_and_keeps_it_on_disk_and_out_of_git(
        self, tmp_path, backups
    ):
        root = make_project(tmp_path / "alpha", LAYER)

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert sorted(result.migrated) == [
            ".claude/settings.json",
            "AGENTS.md",
            "CLAUDE.md",
        ]
        assert tracked(root) == ["main.py"], "only the work stays tracked"
        for name in result.migrated:
            assert (root / name).read_bytes() == LAYER[name].encode("utf-8"), (
                f"{name} must stay on disk, byte for byte — the agent still reads it"
            )
        status = git("status", "--porcelain", cwd=root).splitlines()
        assert sorted(line[:2] for line in status) == ["D ", "D ", "D "], (
            "the untracking is staged for the person to commit, and nothing else changed"
        )
        assert "AGENTS.md" in exclude_text(root), (
            "the exclude file hides them from now on"
        )

    def test_a_backup_outside_the_repo_holds_every_file_byte_for_byte(
        self, tmp_path, backups
    ):
        root = make_project(tmp_path / "alpha", LAYER)

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert result.backup_dir == backups / "run1"
        assert root not in result.backup_dir.parents
        for name in result.migrated:
            assert (result.backup_dir / name).read_bytes() == LAYER[name].encode(
                "utf-8"
            )

    def test_running_twice_does_nothing_the_second_time(self, tmp_path, backups):
        root = make_project(tmp_path / "alpha", LAYER)
        layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)
        git("commit", "-qm", "untrack the AI layer", cwd=root)

        second = layer_migrate.migrate_ai_layer_out(root, backups / "run2", apply=True)

        assert second.migrated == []
        assert not (backups / "run2").exists(), (
            "no empty backup directory is left behind"
        )
        assert git("status", "--porcelain", cwd=root).strip() == ""

    def test_a_project_tracking_nothing_is_left_untouched(self, tmp_path, backups):
        root = make_project(tmp_path / "alpha", {"main.py": "x = 1\n"})
        before = exclude_text(root)

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert result.migrated == []
        assert exclude_text(root) == before


class TestDryRunChangesNothing:
    def test_it_lists_the_plan_and_writes_nothing(self, tmp_path, backups):
        root = make_project(tmp_path / "alpha", LAYER)
        index_before = git("ls-files", "-s", cwd=root)

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=False)

        assert sorted(result.migrated) == [
            ".claude/settings.json",
            "AGENTS.md",
            "CLAUDE.md",
        ]
        assert git("ls-files", "-s", cwd=root) == index_before
        assert not (backups / "run1").exists()
        assert "AGENTS.md" not in exclude_text(root)


class TestNothingIsLost:
    def test_a_backup_that_fails_leaves_the_index_alone(
        self, tmp_path, backups, monkeypatch
    ):
        # Mutation guard: untracking before the backup is verified would pass every test above.
        root = make_project(tmp_path / "alpha", LAYER)
        index_before = git("ls-files", "-s", cwd=root)

        def boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(layer_migrate.shutil, "copy2", boom)

        with pytest.raises((OSError, DrunkenError)):
            layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert git("ls-files", "-s", cwd=root) == index_before
        assert "AGENTS.md" not in exclude_text(root)

    def test_a_backup_dir_that_already_holds_files_is_refused(self, tmp_path, backups):
        root = make_project(tmp_path / "alpha", LAYER)
        (backups / "run1").mkdir(parents=True)
        (backups / "run1" / "someone-elses.txt").write_text("keep", encoding="utf-8")
        index_before = git("ls-files", "-s", cwd=root)

        with pytest.raises(DrunkenError):
            layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert git("ls-files", "-s", cwd=root) == index_before
        assert (backups / "run1" / "someone-elses.txt").read_text(
            encoding="utf-8"
        ) == "keep"

    def test_a_tracked_file_missing_from_disk_is_restored_from_the_index(
        self, tmp_path, backups
    ):
        root = make_project(tmp_path / "alpha", LAYER)
        (root / "AGENTS.md").unlink()

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert "AGENTS.md" in result.restored
        assert (root / "AGENTS.md").read_bytes() == LAYER["AGENTS.md"].encode("utf-8")
        assert (result.backup_dir / "AGENTS.md").read_bytes() == LAYER[
            "AGENTS.md"
        ].encode("utf-8")

    def test_uncommitted_edits_are_in_the_backup_not_only_the_committed_text(
        self, tmp_path, backups
    ):
        root = make_project(tmp_path / "alpha", LAYER)
        (root / "AGENTS.md").write_text(
            "# rules\nedited, not committed\n", encoding="utf-8"
        )

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert "edited, not committed" in (result.backup_dir / "AGENTS.md").read_text(
            encoding="utf-8"
        )
        assert "edited, not committed" in (root / "AGENTS.md").read_text(
            encoding="utf-8"
        )

    def test_a_path_with_glob_characters_and_spaces_is_untracked_literally(
        self, tmp_path, backups
    ):
        files = {
            **LAYER,
            "packages/we ird[1]/CLAUDE.md": "@AGENTS.md\n",
            "packages/other/CLAUDE.md": "x\n",
        }
        root = make_project(tmp_path / "alpha", files)

        layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert tracked(root) == ["main.py"], tracked(root)


class TestRefusals:
    def test_a_tracked_symlink_is_refused_before_anything_changes(
        self, tmp_path, backups
    ):
        root = tmp_path / "alpha"
        root.mkdir()
        git("init", "-q", "--initial-branch=main", cwd=root)
        (root / "real.md").write_text("rules\n", encoding="utf-8")
        try:
            os.symlink(root / "real.md", root / "AGENTS.md")
        except OSError as exc:
            pytest.skip(f"cannot create a symlink here: {exc}")
        git("add", "-A", cwd=root)
        git("commit", "-qm", "initial", cwd=root)
        index_before = git("ls-files", "-s", cwd=root)

        with pytest.raises(DrunkenError):
            layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert git("ls-files", "-s", cwd=root) == index_before

    def test_a_folder_that_is_not_a_git_repository_is_refused(self, tmp_path, backups):
        (tmp_path / "plain").mkdir()

        with pytest.raises(DrunkenError):
            layer_migrate.migrate_ai_layer_out(
                tmp_path / "plain", backups / "run1", apply=True
            )


class TestSecretShapedContentIsReportedNeverPrinted:
    def test_a_finding_names_the_file_and_never_the_value(self, tmp_path, backups):
        token = "ghp_" + "Z3taFakeFakeFakeFakeFakeFakeFake0123"
        root = make_project(
            tmp_path / "alpha", {**LAYER, "AGENTS.md": f"token: {token}\n"}
        )

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert result.findings, (
            "a token-shaped value in a migrated file must be reported"
        )
        for line in result.findings:
            assert "AGENTS.md" in line
            assert token not in line
        assert "AGENTS.md" in result.migrated, (
            "reporting is not a reason to leave it tracked"
        )
        assert result.history_note, "git history still holds it; say so"


class TestAnInterruptedRunCanBeRerun:
    """Review of #183: a run that stopped after untracking but before excluding read as 'nothing to
    migrate' on the rerun. Excluding first means a stop leaves the files still tracked."""

    def test_a_failed_untrack_leaves_the_files_tracked_and_the_rerun_finishes(
        self, tmp_path, backups, monkeypatch
    ):
        root = make_project(tmp_path / "alpha", LAYER)

        def boom(*_a, **_k):
            raise layer_migrate.MigrationError("git went away")

        monkeypatch.setattr(layer_migrate, "_untrack", boom)
        with pytest.raises(layer_migrate.MigrationError):
            layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)
        assert "AGENTS.md" in tracked(root), "the first run must not look finished"
        monkeypatch.undo()

        second = layer_migrate.migrate_ai_layer_out(root, backups / "run2", apply=True)

        assert sorted(second.migrated) == [
            ".claude/settings.json",
            "AGENTS.md",
            "CLAUDE.md",
        ]
        assert tracked(root) == ["main.py"]
        assert (backups / "run1").exists(), (
            "the first backup is never clobbered by the rerun"
        )

    def test_the_exclude_is_written_before_the_index_changes(
        self, tmp_path, backups, monkeypatch
    ):
        root = make_project(tmp_path / "alpha", LAYER)
        seen = {}
        real = layer_migrate._untrack

        def spy(git_root, rels):
            seen["exclude_at_untrack"] = "AGENTS.md" in exclude_text(root)
            real(git_root, rels)

        monkeypatch.setattr(layer_migrate, "_untrack", spy)
        layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert seen["exclude_at_untrack"] is True


class TestTheBackupIsVerifiedAndPrivate:
    def test_a_backup_that_does_not_match_stops_before_the_index_changes(
        self, tmp_path, backups, monkeypatch
    ):
        # Review of #183: removing the compare left every test green.
        root = make_project(tmp_path / "alpha", LAYER)
        index_before = git("ls-files", "-s", cwd=root)
        monkeypatch.setattr(layer_migrate.filecmp, "cmp", lambda *_a, **_k: False)

        with pytest.raises(layer_migrate.MigrationError):
            layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert git("ls-files", "-s", cwd=root) == index_before

    @pytest.mark.skipif(os.name == "nt", reason="Windows ignores POSIX mode bits")
    def test_the_backup_is_owner_only_on_posix(self, tmp_path, backups):
        root = make_project(tmp_path / "alpha", LAYER)

        result = layer_migrate.migrate_ai_layer_out(root, backups / "run1", apply=True)

        assert (result.backup_dir.stat().st_mode & 0o077) == 0
        assert ((result.backup_dir / "AGENTS.md").stat().st_mode & 0o077) == 0
