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

import os
import subprocess
from pathlib import Path

import pytest

from core import exclude, layer_copy
from core.errors import DrunkenError


def _symlink_or_skip(
    link: Path, target: Path, *, target_is_directory: bool = False
) -> None:
    """Create a real symlink, or skip the test — never fake a pass.

    Creating a symlink needs a privilege this process may not have
    (notably on Windows without Developer Mode or an elevated prompt). A
    skip here is honest about what was not proven; silently treating the
    file as a plain copy instead would prove nothing about symlink
    handling at all.
    """
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink on this platform/privilege: {exc}")


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


class TestTrackedCheckIgnoresALeakedGitEnvironment:
    """A caller's own process (`drunken-init` running inside a git hook, for
    instance) may have GIT_DIR/GIT_COMMON_DIR/GIT_WORK_TREE set, pointing at
    a completely different repository. The tracked-file check must answer
    for *git_root*'s own git regardless — never for whatever repository a
    leaked env var happens to redirect a naive `git` subprocess to."""

    def test_git_dir_leaked_to_an_unrelated_repo_still_refuses_a_tracked_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = _init_repo(tmp_path / "unrelated")
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "CLAUDE.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked CLAUDE.md", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == (
            "tracked, committed\n"
        )

    def test_git_dir_leaked_still_refuses_even_with_overwrite_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact finding from review: with GIT_DIR pointing at an
        unrelated repo, `overwrite=True` must not change the outcome —
        this is the absolute refusal, not the soft skip."""
        unrelated = _init_repo(tmp_path / "unrelated")
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "CLAUDE.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked CLAUDE.md", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == (
            "tracked, committed\n"
        )

    def test_git_work_tree_leaked_to_an_unrelated_repo_still_refuses_a_tracked_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = _init_repo(tmp_path / "unrelated")
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "CLAUDE.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked CLAUDE.md", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        monkeypatch.setenv("GIT_WORK_TREE", str(unrelated))
        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == (
            "tracked, committed\n"
        )

    def test_a_git_failure_other_than_tracked_or_not_raises_not_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed: an exit code `ls-files --error-unmatch` does not
        document as either "tracked" or "not tracked" must raise, not be
        read as "not tracked" and copied over."""
        import subprocess as subprocess_module

        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        def fake_run_git(args, repo_root):
            if args[:1] == ["ls-files"]:
                return subprocess_module.CompletedProcess(
                    args, 128, stdout="", stderr="fatal: something went wrong"
                )
            return subprocess_module.CompletedProcess(args, 0, stdout="", stderr="")

        monkeypatch.setattr(layer_copy, "run_git", fake_run_git)

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert not (repo / "AGENTS.md").exists()


class TestATrackedFileMissingFromTheWorkingTreeIsStillRefused:
    """A committed file deleted from the working tree is still tracked.
    Copying over the gap it left would turn a clean `git status` into one
    reporting a modified file the moment the project's own git is asked —
    the tracked check must never be conditioned on the destination
    currently existing on disk."""

    def test_a_deleted_but_tracked_file_is_refused_nothing_written(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "CLAUDE.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked CLAUDE.md", cwd=repo)
        (repo / "CLAUDE.md").unlink()  # still tracked, just missing on disk

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        with pytest.raises(DrunkenError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert str((repo / "CLAUDE.md").resolve()) in str(exc_info.value)
        # Nothing at all written, including the unrelated, non-conflicting
        # AGENTS.md.
        assert not (repo / "AGENTS.md").exists()
        assert not (repo / "CLAUDE.md").exists()


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


class TestDestinationSymlinksAreNeverWrittenThrough:
    """ "Copy, never symlink" cuts both ways: an existing destination that
    is itself a symlink is refused outright, whatever it points at and
    whether or not that target exists."""

    def test_a_destination_symlinked_outside_the_project_root_is_refused_target_untouched(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        outside = tmp_path / "outside.md"
        outside.write_text(
            "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n", encoding="utf-8"
        )
        _symlink_or_skip(repo / "CLAUDE.md", outside)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert outside.read_text(encoding="utf-8") == (
            "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n"
        )
        assert (repo / "CLAUDE.md").is_symlink(), "the symlink itself must be untouched"

    def test_a_destination_symlinked_outside_the_project_root_is_refused_even_with_overwrite(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        outside = tmp_path / "outside.md"
        outside.write_text(
            "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n", encoding="utf-8"
        )
        _symlink_or_skip(repo / "CLAUDE.md", outside)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        assert outside.read_text(encoding="utf-8") == (
            "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n"
        )

    def test_a_dangling_destination_symlink_is_refused_nothing_written(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        _symlink_or_skip(repo / "CLAUDE.md", repo / "does-not-exist.md")
        assert not (repo / "does-not-exist.md").exists()

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        assert not (repo / "does-not-exist.md").exists(), (
            "must not have created the dangling symlink's target"
        )

    def test_the_project_root_containment_check_is_exercised_on_its_own(
        self, tmp_path: Path
    ) -> None:
        """The symlink tests above are all caught by the `is_symlink()`
        check *before* the containment check ever runs, so none of them
        prove the containment check itself still does anything — a
        mutation deleting it would pass every one of them unchanged. This
        calls `_checked_destination` directly with a non-symlink
        `relative` ("../escape.md") that only the containment check can
        catch, isolating it from the symlink guard entirely. A real
        `relative` can never actually contain ".." (`_layer_files` only
        ever yields paths from `Path.relative_to`, which cannot produce
        one) — this is deliberately a white-box test of the private helper
        on its own, the same way DG-440's own toplevel cross-check gets an
        isolated test for exactly this reason.
        """
        import core.layer_copy as layer_copy_module

        # git_root is project_root's *parent* here, deliberately: the
        # escape target ("../escape.md" resolves to a sibling of
        # project_root) lands *inside* git_root, so the separate
        # git-root containment check does not fire either — only the
        # project-root check can catch this one.
        git_root = tmp_path
        project_root = tmp_path / "project"
        project_root.mkdir()

        with pytest.raises(layer_copy.ProjectRootEscapeError):
            layer_copy_module._checked_destination(  # noqa: SLF001
                project_root.resolve(),
                git_root.resolve(),
                Path("../escape.md"),
            )


class TestConfigRepoSymlinksAreNeverFollowed:
    """A config repo entry that is itself a symlink — file or directory —
    must never be read through: it could point anywhere on disk, and this
    call was never told to trust whatever is there."""

    def test_a_symlinked_directory_in_the_config_repo_is_never_descended_into(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        secret_dir = tmp_path / "secret"
        secret_dir.mkdir()
        (secret_dir / "settings.json").write_text(
            '{"secret": "do not copy"}\n', encoding="utf-8"
        )

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        _symlink_or_skip(
            project_folder / ".claude", secret_dir, target_is_directory=True
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert not (repo / ".claude").exists()
        assert not any("settings.json" in item for item in result.copied)

    def test_a_symlinked_file_in_the_config_repo_is_never_copied(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        secret_file = tmp_path / "secret-agents.md"
        secret_file.write_text("SECRET CONTENT\n", encoding="utf-8")

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        _symlink_or_skip(project_folder / "AGENTS.md", secret_file)

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert not (repo / "AGENTS.md").exists()
        assert "AGENTS.md" not in result.copied
