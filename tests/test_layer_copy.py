# mypy: ignore-errors
"""DG-441 (REQ-019/REQ-020). ``drunken-init`` copies a project's AI layer in
from the config repo.

Copy, never symlink; files on `core.ai_layer`'s one list only; never
overwrite a file the project's own git already tracks (refused, nothing
written); an existing *untracked* file is skipped and reported, not
clobbered, unless the caller explicitly asks to overwrite; the exclude
writer (DG-440) always runs afterwards so `git status` stays clean.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core import exclude, layer_copy
from core.errors import DrunkenError


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
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
    (path / "README.md").write_text("scratch\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=path)
    _run_git("commit", "-q", "-m", "initial", cwd=path)
    return path


def _config_repo(tmp_path: Path) -> Path:
    return (tmp_path / "config-repo").resolve()


class TestHappyPath:
    def test_populates_the_checkout_excludes_and_leaves_git_status_clean(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        (project_folder / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        claude_dir = project_folder / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "instructions\n"
        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
        assert (repo / ".claude" / "settings.json").read_text(
            encoding="utf-8"
        ) == "{}\n"
        assert set(result.copied) == {
            "AGENTS.md",
            "CLAUDE.md",
            ".claude/settings.json",
        }

        status = _run_git("status", "--porcelain", cwd=repo)
        assert status.stdout.strip() == "", (
            f"git status is not clean after the copy: {status.stdout!r}"
        )


class TestNeverSymlinks:
    def test_copied_files_are_real_files_not_symlinks(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        destination = repo / "AGENTS.md"
        assert destination.is_file()
        # The realistic mutation this guards against: `os.symlink` instead
        # of a real copy. A symlink would still read back the right content
        # and pass a content-only assertion, which is exactly why this
        # checks the filesystem type too.
        assert not destination.is_symlink(), (
            "AGENTS.md must be a real copy, never a symlink into the config repo"
        )


class TestOnlyAiLayerFilesAreCopied:
    def test_a_file_not_on_the_list_is_never_copied(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        # Not on core.ai_layer's list — must never land in the checkout.
        (project_folder / "notes.txt").write_text("private notes\n", encoding="utf-8")

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert not (repo / "notes.txt").exists()
        assert "notes.txt" not in result.copied


class TestExistingUntrackedFileIsSkippedByDefault:
    def test_an_existing_untracked_file_is_not_overwritten_and_is_reported(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "AGENTS.md").write_text("MINE, DO NOT TOUCH\n", encoding="utf-8")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        # The realistic mutation this guards against: copying over whatever
        # is already there. The existing content must survive untouched.
        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == (
            "MINE, DO NOT TOUCH\n"
        )
        assert "AGENTS.md" not in result.copied
        assert any(skip.relative == "AGENTS.md" for skip in result.skipped)

    def test_an_explicit_overwrite_flag_replaces_an_untracked_file(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "AGENTS.md").write_text("MINE, DO NOT TOUCH\n", encoding="utf-8")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
            overwrite=True,
        )

        assert (repo / "AGENTS.md").read_text(
            encoding="utf-8"
        ) == "from the config repo\n"
        assert "AGENTS.md" in result.copied


class TestATrackedFileIsRefusedOutright:
    def test_a_git_tracked_file_is_refused_naming_the_path_nothing_written(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "AGENTS.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked AGENTS.md", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )
        (project_folder / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

        with pytest.raises(DrunkenError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert str((repo / "AGENTS.md").resolve()) in str(exc_info.value)
        # The realistic mutation this guards against: copying the other
        # files before noticing the conflict. Nothing at all is written —
        # not even the file that was not in conflict.
        assert not (repo / "CLAUDE.md").exists()
        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == (
            "tracked, committed\n"
        )
        exclude_path = repo / ".git" / "info" / "exclude"
        exclude_text = (
            exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        )
        assert exclude.MARKER_START not in exclude_text


class TestTheExcludeWriterAlwaysRuns:
    def test_check_ignore_reports_the_copied_files_as_ignored(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        (project_folder / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

        layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        for relative in ("AGENTS.md", "CLAUDE.md"):
            result = _run_git("check-ignore", relative, cwd=repo)
            assert result.stdout.strip() == relative


class TestRefusesWhenTheProjectRootIsNotAGitRepository:
    def test_a_plain_folder_is_refused_and_nothing_is_written(
        self, tmp_path: Path
    ) -> None:
        plain_folder = tmp_path / "not-a-repo"
        plain_folder.mkdir()
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=plain_folder,
                git_root=plain_folder,
            )

        assert not (plain_folder / "AGENTS.md").exists()
        assert not (plain_folder / ".git").exists()


class TestRefusesWhenTheConfigRepoFolderIsMissing:
    def test_an_unknown_project_folder_is_refused_naming_it(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        config_repo.mkdir(parents=True)
        # Note: no "sample" folder created inside the config repo.

        with pytest.raises(DrunkenError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert "sample" in str(exc_info.value)
        assert not (repo / "AGENTS.md").exists()


class TestPathTraversalInTheConfigRepo:
    def test_a_traversing_project_id_is_refused_and_nothing_outside_is_read(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        config_repo.mkdir(parents=True)
        # A secret living *outside* the config repo, at the same level as it.
        secret_dir = tmp_path / "escaped"
        secret_dir.mkdir()
        (secret_dir / "AGENTS.md").write_text("ESCAPED CONTENT\n", encoding="utf-8")

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="../escaped",
                project_root=repo,
                git_root=repo,
            )

        assert not (repo / "AGENTS.md").exists()


class TestSubfolderRegisteredProject:
    """Comment (a) on DG-441: `exclude_ai_layer` refuses a `repo_root` that
    is not itself the git top-level. A project registered at a subfolder of
    its repository must have the exclude writer called with the *git root*
    (`core.context.git_root_path`), never the project's own (sub)root."""

    def test_copy_lands_in_the_subfolder_and_exclude_runs_against_the_git_root(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "monorepo")
        project_root = repo / "packages" / "sample"
        project_root.mkdir(parents=True)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=project_root,
            git_root=repo,
        )

        # The file is written where the agent actually works...
        assert (project_root / "AGENTS.md").read_text(
            encoding="utf-8"
        ) == "instructions\n"
        # ...but info/exclude is the repository's own, at the real git root,
        # not something invented under the subfolder.
        assert result.excluded.exclude_path == repo / ".git" / "info" / "exclude"

        status = _run_git("status", "--porcelain", cwd=repo)
        assert status.stdout.strip() == "", (
            f"git status is not clean after the copy: {status.stdout!r}"
        )

    def test_passing_the_subfolder_itself_as_the_exclude_root_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The realistic mutation this guards against: wiring the copy step
        to call the exclude writer with `project_root` (the registered,
        possibly-nested path) instead of the actual git root. DG-440's own
        toplevel cross-check refuses that rather than silently writing a
        wrong or incomplete exclude file."""
        repo = _init_repo(tmp_path / "monorepo")
        project_root = repo / "packages" / "sample"
        project_root.mkdir(parents=True)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=project_root,
                git_root=project_root,
            )
