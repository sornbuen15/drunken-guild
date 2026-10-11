# mypy: ignore-errors
"""DG-479/DG-480: ``core.git_hooks.install_pre_push_hook`` is the one
supported way to put the native pre-push privacy scan into a checkout
(``drunken-init --install-git-hooks``). An agent does not run an installer
in a main checkout (CLAUDE.md), so every scratch repository here is a real
`git init` under ``tmp_path`` — never the tracked worktree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core import git_hooks
from core.errors import ValidationError

GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *GIT_IDENTITY, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


class TestFreshInstall:
    def test_installs_an_executable_hook_carrying_the_marker(self, tmp_path: Path):
        root = tmp_path / "proj"
        _init_repo(root)

        report = git_hooks.install_pre_push_hook(root)

        target = root / ".git" / "hooks" / "pre-push"
        assert target.is_file(), report
        assert git_hooks.is_ours(target)
        assert "installed" in report

    @pytest.mark.skipif(
        sys.platform == "win32", reason="NTFS has no POSIX execute bit to check"
    )
    def test_the_installed_hook_is_executable(self, tmp_path: Path):
        import os
        import stat

        root = tmp_path / "proj"
        _init_repo(root)

        git_hooks.install_pre_push_hook(root)

        target = root / ".git" / "hooks" / "pre-push"
        assert os.access(target, os.X_OK)
        assert stat.S_IMODE(target.stat().st_mode) & stat.S_IXUSR


class TestIdempotent:
    def test_installing_twice_over_our_own_unchanged_hook_is_a_no_op_report(
        self, tmp_path: Path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        git_hooks.install_pre_push_hook(root)
        target = root / ".git" / "hooks" / "pre-push"
        before = target.read_text(encoding="utf-8")
        before_mtime = target.stat().st_mtime_ns

        report = git_hooks.install_pre_push_hook(root)

        assert "unchanged" in report
        assert target.read_text(encoding="utf-8") == before
        assert target.stat().st_mtime_ns == before_mtime, (
            "an unchanged install must not rewrite the file at all"
        )

    def test_installing_over_our_own_hook_with_different_content_updates_in_place(
        self, tmp_path: Path
    ):
        """A template edited upstream: still ours (marker present), but no
        longer byte-identical -- must be updated, not refused as foreign."""
        root = tmp_path / "proj"
        _init_repo(root)
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-push").write_text(
            f"#!/bin/sh\n{git_hooks.MARKER}\n# an older version of this hook\nexit 0\n",
            encoding="utf-8",
        )

        report = git_hooks.install_pre_push_hook(root)

        assert "updated" in report
        assert (hooks_dir / "pre-push").read_text(
            encoding="utf-8"
        ) == git_hooks._read_template()


class TestForeignHookNeverOverwrittenOrDeleted:
    def test_a_pre_push_file_with_no_marker_is_refused(self, tmp_path: Path):
        root = tmp_path / "proj"
        _init_repo(root)
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        foreign = hooks_dir / "pre-push"
        foreign.write_text(
            "#!/bin/sh\necho someone else's hook\nexit 0\n", encoding="utf-8"
        )
        before = foreign.read_text(encoding="utf-8")

        with pytest.raises(git_hooks.ForeignPrePushHookError):
            git_hooks.install_pre_push_hook(root)

        assert foreign.is_file(), "a foreign hook must never be deleted"
        assert foreign.read_text(encoding="utf-8") == before, (
            "a foreign hook must never be overwritten either"
        )

    def test_the_refusal_is_a_drunkenerror_with_a_remediation(self, tmp_path: Path):
        root = tmp_path / "proj"
        _init_repo(root)
        hooks_dir = root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        (hooks_dir / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        with pytest.raises(ValidationError) as excinfo:
            git_hooks.install_pre_push_hook(root)

        assert excinfo.value.remediation


class TestHonoursCoreHooksPath:
    def test_installs_into_the_configured_hooks_path_not_dot_git_hooks(
        self, tmp_path: Path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "myhooks").mkdir()
        _git("config", "core.hooksPath", "myhooks", cwd=root)

        report = git_hooks.install_pre_push_hook(root)

        assert (root / "myhooks" / "pre-push").is_file(), report
        assert not (root / ".git" / "hooks" / "pre-push").exists()


class TestLinkedWorktreesShareOneHooksDir:
    def test_installing_from_a_worktree_writes_to_the_shared_main_hooks_dir(
        self, tmp_path: Path
    ):
        main = tmp_path / "main"
        _init_repo(main)
        (main / "f.txt").write_text("x", encoding="utf-8")
        _git("add", "-A", cwd=main)
        _git("commit", "-m", "initial", "-q", cwd=main)
        worktree = tmp_path / "wt"
        _git("worktree", "add", "-b", "wtbranch", str(worktree), cwd=main)

        report = git_hooks.install_pre_push_hook(worktree)

        assert (main / ".git" / "hooks" / "pre-push").is_file(), report
        # The worktree's own `.git` is a file, not a directory -- nothing is
        # ever written there; everything lands in the shared common dir.
        assert (worktree / ".git").is_file()

    def test_a_hook_installed_from_the_main_checkout_is_seen_from_the_worktree_too(
        self, tmp_path: Path
    ):
        main = tmp_path / "main"
        _init_repo(main)
        (main / "f.txt").write_text("x", encoding="utf-8")
        _git("add", "-A", cwd=main)
        _git("commit", "-m", "initial", "-q", cwd=main)
        worktree = tmp_path / "wt"
        _git("worktree", "add", "-b", "wtbranch", str(worktree), cwd=main)

        git_hooks.install_pre_push_hook(main)

        # Installing again *from the worktree* must see the main checkout's
        # hook as already ours and report unchanged -- never write a second,
        # worktree-local copy, since there is nowhere for one to live.
        report = git_hooks.install_pre_push_hook(worktree)
        assert "unchanged" in report


class TestNotAGitRepository:
    def test_refuses_with_a_clear_error_outside_any_checkout(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()

        with pytest.raises(ValidationError):
            git_hooks.install_pre_push_hook(plain)


class TestIsOurs:
    def test_false_for_a_missing_file(self, tmp_path: Path):
        assert git_hooks.is_ours(tmp_path / "does-not-exist") is False

    def test_false_for_a_file_with_no_marker(self, tmp_path: Path):
        path = tmp_path / "pre-push"
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        assert git_hooks.is_ours(path) is False

    def test_true_for_a_file_carrying_the_marker(self, tmp_path: Path):
        path = tmp_path / "pre-push"
        path.write_text(f"#!/bin/sh\n{git_hooks.MARKER}\nexit 0\n", encoding="utf-8")
        assert git_hooks.is_ours(path) is True


class TestTemplateMatchesTheCommittedScript:
    def test_the_installed_hook_is_byte_identical_to_the_tracked_template(
        self, tmp_path: Path
    ):
        """The installer must copy the real, committed script verbatim --
        never a second, drifting string constant."""
        root = tmp_path / "proj"
        _init_repo(root)

        git_hooks.install_pre_push_hook(root)

        installed = (root / ".git" / "hooks" / "pre-push").read_text(encoding="utf-8")
        tracked = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "git_hooks"
            / "pre-push"
        ).read_text(encoding="utf-8")
        assert installed == tracked

    def test_the_marker_constant_matches_line_two_of_the_tracked_script(self):
        tracked = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "git_hooks"
            / "pre-push"
        ).read_text(encoding="utf-8")
        second_line = tracked.splitlines()[1]
        assert second_line == git_hooks.MARKER
