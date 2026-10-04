# mypy: ignore-errors
"""DG-440 (REQ-019/REQ-020). The .git/info/exclude writer.

Hides a project's copied-in AI layer from its own git, between markers,
idempotently, in a plain clone and in a `git worktree`. The patterns come
from the one AI-layer list (DG-437, `core.ai_layer`) — this module adds no
second list of paths.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core import exclude
from core.errors import DrunkenError


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed in {cwd}: {result.stderr}"
    )
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run_git("init", "-q", cwd=path)
    _run_git("config", "user.email", "test@example.com", cwd=path)
    _run_git("config", "user.name", "Test", cwd=path)
    # A repo with no commit has no HEAD, which some git plumbing dislikes —
    # give every scratch repo one, same as a real clone would have.
    (path / "README.md").write_text("scratch\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=path)
    _run_git("commit", "-q", "-m", "initial", cwd=path)
    return path


class TestPlainClone:
    def test_creates_info_and_exclude_when_absent(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        # `git init` itself seeds info/exclude with a boilerplate comment on
        # most git versions, so this proves the *parent directory* case —
        # delete info/ entirely to get the genuinely-absent case this
        # ACCEPTANCE line names.
        info_dir = repo / ".git" / "info"
        if info_dir.exists():
            for child in info_dir.iterdir():
                child.unlink()
            info_dir.rmdir()
        assert not info_dir.exists()

        result = exclude.exclude_ai_layer(repo)

        exclude_path = repo / ".git" / "info" / "exclude"
        assert exclude_path.exists()
        assert exclude_path == result.exclude_path
        assert result.added, "first run should report the patterns it added"

    def test_lists_every_ai_layer_pattern(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        exclude.exclude_ai_layer(repo)

        text = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        for pattern in exclude.default_ai_layer_patterns():
            assert pattern in text, f"{pattern!r} missing from info/exclude"

    def test_idempotent_second_run_changes_nothing(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        exclude.exclude_ai_layer(repo)
        exclude_path = repo / ".git" / "info" / "exclude"
        first_text = exclude_path.read_text(encoding="utf-8")

        result = exclude.exclude_ai_layer(repo)

        second_text = exclude_path.read_text(encoding="utf-8")
        assert second_text == first_text, "re-running changed the file"
        assert result.added == (), "re-running should report nothing added"

        # Realistic mutation: a naive, non-idempotent implementation just
        # appends the block again every time. Prove that failure mode would
        # actually be caught here.
        marker_count = first_text.count(exclude.MARKER_START)
        assert marker_count == 1, (
            f"expected exactly one marker block, found {marker_count} — "
            "a non-idempotent appender would fail this"
        )

    def test_preserves_existing_content_and_missing_trailing_newline(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_path = info_dir / "exclude"
        # Deliberately no trailing newline, as a hand-edited file might have.
        exclude_path.write_text("*.pyc", encoding="utf-8")

        exclude.exclude_ai_layer(repo)

        text = exclude_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert lines[0] == "*.pyc", "existing content must survive untouched"
        # The realistic mutation: concatenating straight onto the existing
        # line without a newline would corrupt it into "*.pyc# >>> ...".
        assert "*.pyc#" not in text
        assert "*.pyc\n" in text or text.startswith("*.pyc\n")

    def test_not_a_git_repository_is_a_clear_error_and_creates_nothing(
        self, tmp_path: Path
    ) -> None:
        plain_folder = tmp_path / "not-a-repo"
        plain_folder.mkdir()

        with pytest.raises(DrunkenError):
            exclude.exclude_ai_layer(plain_folder)

        assert not (plain_folder / ".git").exists(), (
            "a failed call must never create a stray .git"
        )

    def test_git_status_is_clean_after_excluding_files_on_disk(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        (repo / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        claude_dir = repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")

        exclude.exclude_ai_layer(repo)

        status = _run_git("status", "--porcelain", cwd=repo)
        assert status.stdout.strip() == "", (
            f"git status is not clean after excluding: {status.stdout!r}"
        )

    def test_check_ignore_reports_each_listed_path_as_ignored(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        (repo / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        claude_dir = repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")
        (repo / ".aider.conf.yml").write_text("\n", encoding="utf-8")

        exclude.exclude_ai_layer(repo)

        for relative in (
            "CLAUDE.md",
            "AGENTS.md",
            ".claude/settings.json",
            ".aider.conf.yml",
        ):
            result = _run_git("check-ignore", relative, cwd=repo)
            assert result.stdout.strip() == relative, (
                f"{relative} is not reported as ignored by check-ignore"
            )


class TestGitWorktree:
    def test_worktree_exclude_lands_in_the_common_dir_not_a_dot_git_dir(
        self, tmp_path: Path
    ) -> None:
        main_repo = _init_repo(tmp_path / "main")
        worktree_path = tmp_path / "wt"
        _run_git(
            "worktree",
            "add",
            "-q",
            "-b",
            "wt-branch",
            str(worktree_path),
            "HEAD",
            cwd=main_repo,
        )

        # In a worktree, .git is a *file*, not a directory. A realistic
        # mutation (treating .git as always a directory and writing
        # <worktree>/.git/info/exclude) must be caught by this test.
        assert (worktree_path / ".git").is_file(), (
            "this test only proves anything if .git is a file here"
        )

        result = exclude.exclude_ai_layer(worktree_path)

        # info/exclude is shared repository state, not per-worktree: it must
        # resolve into the *main* repo's .git directory, never into a
        # directory literally named .git under the worktree path.
        assert result.exclude_path == main_repo / ".git" / "info" / "exclude"
        assert result.exclude_path.exists()
        text = result.exclude_path.read_text(encoding="utf-8")
        assert exclude.MARKER_START in text

    def test_worktree_idempotent(self, tmp_path: Path) -> None:
        main_repo = _init_repo(tmp_path / "main")
        worktree_path = tmp_path / "wt"
        _run_git(
            "worktree",
            "add",
            "-q",
            "-b",
            "wt-branch2",
            str(worktree_path),
            "HEAD",
            cwd=main_repo,
        )

        exclude.exclude_ai_layer(worktree_path)
        exclude_path = main_repo / ".git" / "info" / "exclude"
        first_text = exclude_path.read_text(encoding="utf-8")

        result = exclude.exclude_ai_layer(worktree_path)

        assert exclude_path.read_text(encoding="utf-8") == first_text
        assert result.added == ()

    def test_worktree_git_status_clean_after_excluding(self, tmp_path: Path) -> None:
        main_repo = _init_repo(tmp_path / "main")
        worktree_path = tmp_path / "wt"
        _run_git(
            "worktree",
            "add",
            "-q",
            "-b",
            "wt-branch3",
            str(worktree_path),
            "HEAD",
            cwd=main_repo,
        )
        (worktree_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

        exclude.exclude_ai_layer(worktree_path)

        status = _run_git("status", "--porcelain", cwd=worktree_path)
        assert status.stdout.strip() == "", (
            f"git status is not clean in the worktree after excluding: "
            f"{status.stdout!r}"
        )


class TestNeverWritesOutsideTheRepo:
    def test_exclude_path_stays_under_the_resolved_git_dir(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        result = exclude.exclude_ai_layer(repo)

        git_dir = (repo / ".git").resolve()
        assert str(result.exclude_path.resolve()).startswith(str(git_dir)), (
            "the exclude file must live inside the resolved git directory"
        )
