# mypy: ignore-errors
"""DG-441 (REQ-019/REQ-020). ``drunken-init`` copies a project's AI layer in
from the config repo.

Copy, never symlink; files on `core.ai_layer`'s one list only; never
overwrite a file the project's own git already tracks (refused, nothing
written); an existing *untracked* file is skipped and reported, not
clobbered, unless the caller explicitly asks to overwrite; the exclude
writer (DG-440) always runs afterwards so `git status` stays clean.

DG-453: the tracked check also compares case-insensitively, so a project
tracking `agents.md` still refuses an AI-layer destination spelled
`AGENTS.md` on a case-insensitive filesystem (NTFS, APFS by default),
where the two spellings are one on-disk file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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

    def test_git_index_file_leaked_to_a_missing_index_still_refuses_a_tracked_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact bug reproduced in review: a leaked `GIT_INDEX_FILE`
        pointing at a missing (so, empty) index makes git read that empty
        index instead of the real one — none of GIT_DIR/GIT_COMMON_DIR/
        GIT_WORK_TREE are involved at all, which is exactly why the strip
        rule had to widen from "the three that redirect resolution" to
        "every GIT_ name"."""
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

        monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "does-not-exist.index"))

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

    def test_a_lower_case_git_index_file_is_stripped_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`os.environ` is case-insensitive on Windows: a caller's process
        can have `git_index_file` (lower-case) set and git itself still
        honours it there. The strip must too."""
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

        monkeypatch.setenv("git_index_file", str(tmp_path / "does-not-exist.index"))

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

    def test_git_object_directory_leaked_to_an_empty_store_still_refuses_a_tracked_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: the user-facing guarantee holds with a leaked
        `GIT_OBJECT_DIRECTORY`. (For *which* internal check is responsible
        here, see `TestInHeadAloneIgnoresALeakedGitObjectDirectory` below —
        empirically, `git diff --cached` itself already reports a spurious
        difference when the object store is broken, which also refuses,
        but for a different reason than the one this scenario was meant to
        isolate; that class isolates `_in_head` on its own instead.)"""
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "CLAUDE.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked CLAUDE.md", cwd=repo)

        empty_objects = tmp_path / "empty-objects"
        empty_objects.mkdir()

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(empty_objects))

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


class TestInHeadAloneIgnoresALeakedGitObjectDirectory:
    """Isolates `_in_head` from `_has_staged_content`, which otherwise
    masks this: empirically, with `GIT_OBJECT_DIRECTORY` pointed at an
    empty directory, `git diff --cached --name-only` *also* reports a
    spurious difference for an unmodified tracked file (git errs toward
    "different" when it cannot read the objects needed to compare) — so
    the end-to-end test above stays safe regardless of this class's
    result. This class calls `_in_head` directly to prove *its own*
    fail-closed behaviour independently of that masking.

    Empirically confirmed directly in a shell first: with
    `GIT_OBJECT_DIRECTORY` pointed at an empty directory,
    `git cat-file -e HEAD:<path>` answers exit 128, "path '<path>' exists
    on disk, but not in 'HEAD'" — the *same* exit code a genuinely absent
    path gets, for a completely different reason (the object store is
    broken, not the history). Exit-code fail-closing cannot tell these two
    apart by code alone; only stripping the leaked variable, so git reads
    the real object store, answers correctly at all.
    """

    def test_a_committed_unmodified_file_is_still_found_in_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "committed.txt").write_text("x\n", encoding="utf-8")
        _run_git("add", "committed.txt", cwd=repo)
        _run_git("commit", "-q", "-m", "c", cwd=repo)

        empty_objects = tmp_path / "empty-objects"
        empty_objects.mkdir()
        monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(empty_objects))

        assert layer_copy._in_head(repo, "committed.txt") is True  # noqa: SLF001

    def test_an_unborn_head_never_reaches_cat_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing can be "in HEAD" before the first commit — and this
        must answer that from `_has_head` alone, without even trying
        `cat-file`, which would otherwise need its own unborn-HEAD parsing
        of a locale-dependent git message."""
        repo = tmp_path / "project"
        repo.mkdir()
        _run_git("init", "-q", cwd=repo)
        _run_git("config", "user.email", "test@example.com", cwd=repo)
        _run_git("config", "user.name", "Test", cwd=repo)

        assert layer_copy._in_head(repo, "never-committed.txt") is False  # noqa: SLF001


class TestTrackedCheckFailsClosedOnUnexpectedGitExitCodes:
    """Fail closed: each git call behind the tracked check is documented to
    exit with only a small, known set of codes for exactly this call shape.
    Anything else must raise, never be read either way."""

    def test_an_unexpected_diff_cached_exit_code_raises_not_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`git diff --cached --name-only` is only ever asked to exit 0
        here (no `--exit-code`); anything else must raise, not be read as
        "no staged content" and copied over."""
        import subprocess as subprocess_module

        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        def fake_run_git(args, repo_root):
            if args[:1] == ["diff"]:
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

    def test_an_unexpected_rev_parse_verify_head_exit_code_raises_not_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed: `git rev-parse --verify -q HEAD` is documented as
        exit 0 (HEAD resolves) or 1 (unborn) only; anything else must raise
        rather than being read either way."""
        import subprocess as subprocess_module

        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        def fake_run_git(args, repo_root):
            if args[:3] == ["rev-parse", "--verify", "-q"]:
                return subprocess_module.CompletedProcess(
                    args, 129, stdout="", stderr="fatal: something went wrong"
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

    def test_an_unexpected_cat_file_exit_code_raises_not_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail closed: `git cat-file -e HEAD:<path>`, once HEAD is known to
        exist, is only ever asked to exit 0 (present) or 128 (absent);
        anything else must raise rather than being read as "not present."
        """
        import subprocess as subprocess_module

        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        def fake_run_git(args, repo_root):
            if args[:1] == ["cat-file"]:
                return subprocess_module.CompletedProcess(
                    args, 2, stdout="", stderr="fatal: something went wrong"
                )
            # diff --cached and rev-parse --verify both say "nothing staged,
            # HEAD exists" so execution reaches the cat-file call above.
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


class TestGitRmCachedStillLeavesAFileRefused:
    """HIGH review finding: `git rm --cached` takes a path out of the
    index while leaving it in `HEAD` untouched — the index-only check this
    module used to run answered "not tracked" for exactly this state. The
    combined check (index OR HEAD) must still refuse."""

    def test_rm_cached_state_is_refused_nothing_written(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "CLAUDE.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked CLAUDE.md", cwd=repo)
        _run_git("rm", "--cached", "CLAUDE.md", cwd=repo)
        # The file is still on disk (git rm --cached only removes it from
        # the index) — the realistic shape of this state.
        assert (repo / "CLAUDE.md").exists()

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        assert str((repo / "CLAUDE.md").resolve()) in str(exc_info.value)
        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == (
            "tracked, committed\n"
        )


class TestARepoWithNoCommitsYet:
    """A fresh `git init` with nothing committed yet has no HEAD at all —
    nothing can be "in HEAD" there, and an untracked file is simply fine."""

    def test_an_untracked_file_in_a_repo_with_no_commits_is_not_refused(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "project"
        repo.mkdir()
        _run_git("init", "-q", cwd=repo)
        _run_git("config", "user.email", "test@example.com", cwd=repo)
        _run_git("config", "user.name", "Test", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "instructions\n"
        assert "AGENTS.md" in result.copied


class TestIntentToAddIsNotRefused:
    """`git add -N` (intent to add) stages a placeholder for a brand-new
    path with no real content yet. There is nothing committed or staged
    to protect, so — deliberately, confirmed with the reviewer — this is
    *not* refused, unlike an ordinary staged addition."""

    def test_an_intent_to_add_never_committed_file_is_not_refused(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text("local, never committed\n", encoding="utf-8")
        _run_git("add", "-N", "CLAUDE.md", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
            overwrite=True,
        )

        assert (repo / "CLAUDE.md").read_text(
            encoding="utf-8"
        ) == "from the config repo\n"
        assert "CLAUDE.md" in result.copied


class TestAPlainStagedNewFileIsRefused:
    """DG-452. A plain ``git add`` of a brand-new path (never committed)
    stages real content — unlike ``git add -N`` (intent-to-add, see
    ``TestIntentToAddIsNotRefused`` below), ``git diff --cached`` lists it.
    Nothing exercised this exact state through the public
    ``copy_ai_layer_in`` entry point before this test: a mutation deleting
    ``_has_staged_content`` entirely from ``_is_tracked`` left the whole
    suite green, because every other test's "staged" fixture was either
    already committed too, or used ``git add -N``."""

    def test_a_plain_staged_new_file_is_refused_nothing_written(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "CLAUDE.md").write_text(
            "local, staged, never committed\n", encoding="utf-8"
        )
        _run_git("add", "CLAUDE.md", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "CLAUDE.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        with pytest.raises(layer_copy.TrackedFileConflictError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                # overwrite=True to prove this is the absolute refusal, not
                # the soft "existing untracked file" skip.
                overwrite=True,
            )

        assert str((repo / "CLAUDE.md").resolve()) in str(exc_info.value)
        # Nothing at all written, including the unrelated, non-conflicting
        # AGENTS.md.
        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == (
            "local, staged, never committed\n"
        )
        assert not (repo / "AGENTS.md").exists()


def _create_or_skip(path: Path, content: str) -> None:
    """Write *content* to *path*, or skip — honestly, not by faking a
    pass. A name NTFS refuses to represent at all (a literal ``*``, ``?``,
    or a leading ``:``) proves nothing about literal pathspec handling if
    it was never actually created; the same names are ordinary, creatable
    filenames on Linux, where the capability probe lets the test run for
    real (see DG-452)."""
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        pytest.skip(f"cannot create {path.name!r} on this filesystem: {exc}")


#: Adversarial basenames that are ordinary, legal filenames on every
#: platform this suite runs on (including NTFS) — a leading dash (which
#: `--` protects from being read as a git option), and pathspec glob/
#: exclude-magic characters (`[...]`, `!`).
_ADVERSARIAL_NAMES: tuple[str, ...] = (
    "[x].md",
    "!bang.md",
    "-dash.md",
)

#: Adversarial basenames NTFS cannot create at all (DG-452) — skipped by
#: `_create_or_skip`'s capability probe on Windows, run for real on Linux
#: CI, where they are ordinary filenames.
#:
#: A leading colon (``:colon.md``) is deliberately *not* here: Linux can
#: create that file, but git's own pathspec parser reads a leading ``:`` as
#: the start of pathspec *magic* syntax (``:(...)``) regardless of ``--``,
#: so `git add -- ":colon.md"` itself fails with "did not match any
#: files" — a pre-existing limit of git's CLI, not something either
#: `_has_staged_content` or `_in_head` could fix, and not what this test is
#: pinning (confirmed empirically on Linux CI before being removed here).
_UNCREATABLE_ON_NTFS_NAMES: tuple[str, ...] = (
    "*star.md",
    "?quest.md",
)


class TestAdversarialFilenamesAreNeverReadAsPathspecMagic:
    """DG-452. Both git calls behind ``_is_tracked`` take the destination's
    path as a literal argument, never shell- or pathspec-expanded magic.
    A crafted name — a leading dash, a pathspec glob/exclude-magic
    character, a shell glob character only creatable on Linux — must still
    be detected as staged or committed, exactly like any ordinary name.

    The realistic mutation this is written to catch: removing the ``--``
    pathspec separator from ``_has_staged_content``'s git invocation.
    Without it, ``-dash.md`` is read by git as an unrecognised *option*
    rather than a path, and the call exits unexpectedly instead of
    reporting whether the path is staged — raising
    ``GitTrackedCheckFailedError`` instead of returning ``True``, which
    turns the ``-dash.md`` case of
    ``test_a_staged_new_file_is_detected_by_the_staged_content_check`` red.
    """

    @pytest.mark.parametrize("name", _ADVERSARIAL_NAMES)
    def test_a_staged_new_file_is_detected_by_the_staged_content_check(
        self, tmp_path: Path, name: str
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        _create_or_skip(repo / name, "staged, never committed\n")
        _run_git("add", "--", name, cwd=repo)

        assert layer_copy._has_staged_content(repo, name) is True  # noqa: SLF001

    @pytest.mark.parametrize("name", _ADVERSARIAL_NAMES)
    def test_a_committed_file_is_detected_by_the_head_check(
        self, tmp_path: Path, name: str
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        _create_or_skip(repo / name, "committed\n")
        _run_git("add", "--", name, cwd=repo)
        _run_git("commit", "-q", "-m", "adversarial name", cwd=repo)

        assert layer_copy._in_head(repo, name) is True  # noqa: SLF001

    @pytest.mark.parametrize("name", _UNCREATABLE_ON_NTFS_NAMES)
    def test_a_staged_new_file_with_a_shell_glob_character_name_is_detected(
        self, tmp_path: Path, name: str
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        _create_or_skip(repo / name, "staged, never committed\n")
        _run_git("add", "--", name, cwd=repo)

        assert layer_copy._has_staged_content(repo, name) is True  # noqa: SLF001

    @pytest.mark.parametrize("name", _UNCREATABLE_ON_NTFS_NAMES)
    def test_a_committed_file_with_a_shell_glob_character_name_is_detected(
        self, tmp_path: Path, name: str
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        _create_or_skip(repo / name, "committed\n")
        _run_git("add", "--", name, cwd=repo)
        _run_git("commit", "-q", "-m", "adversarial name", cwd=repo)

        assert layer_copy._in_head(repo, name) is True  # noqa: SLF001


class TestATrackedPathNestedUnderATrackedDirectory:
    """Review note: "treat a path under a tracked directory correctly."
    Only the *exact* file is checked, never a whole-directory shortcut —
    a sibling under the same tracked directory being tracked must not
    make an untracked file next to it look tracked, or vice versa."""

    def test_only_the_exact_nested_path_is_treated_as_tracked(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        claude_dir = repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "tracked.json").write_text("{}\n", encoding="utf-8")
        _run_git("add", ".claude/tracked.json", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked nested file", cwd=repo)

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        nested = project_folder / ".claude"
        nested.mkdir()
        (nested / "tracked.json").write_text(
            '{"from": "config repo"}\n', encoding="utf-8"
        )
        (nested / "settings.json").write_text("{}\n", encoding="utf-8")

        with pytest.raises(DrunkenError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        # Refused for the tracked sibling, naming it specifically...
        assert str((repo / ".claude" / "tracked.json").resolve()) in str(exc_info.value)
        # ...and nothing written at all, including the untracked sibling
        # that shares its directory.
        assert not (repo / ".claude" / "settings.json").exists()


def _case_insensitive_fs_or_skip(probe_dir: Path) -> None:
    """Skip, honestly, on a filesystem where two names differing only in
    case are two distinct files — the scenario this guards against cannot
    occur there at all. Never fakes a pass: this writes a real probe file
    and reads it back under the other case, the same style as
    ``_symlink_or_skip`` above."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    lower = probe_dir / "dg453-case-probe.tmp"
    upper = probe_dir / "DG453-CASE-PROBE.TMP"
    lower.write_text("probe\n", encoding="utf-8")
    try:
        same_file = upper.exists() and upper.read_text(encoding="utf-8") == "probe\n"
    finally:
        lower.unlink(missing_ok=True)
    if not same_file:
        pytest.skip(
            "this filesystem is case-sensitive; AGENTS.md and agents.md "
            "are two distinct files here, so this scenario cannot occur"
        )


class TestCaseInsensitiveTrackedFileIsRefused:
    """DG-453. git's own index is case-sensitive: a project that tracks
    ``agents.md`` gets "not tracked" from an exact-case lookup for the
    AI-layer's ``AGENTS.md``. On a case-insensitive filesystem (NTFS,
    APFS by default) the two spellings are the very same on-disk file, so
    without a case-insensitive comparison, ``--overwrite-ai-layer``
    silently overwrites the tracked file's content.

    The tracked file is deleted from the working tree first (still
    tracked — see ``TestATrackedFileMissingFromTheWorkingTreeIsStillRefused``
    above) because, empirically, ``pathlib.Path.resolve()`` on a
    case-insensitive filesystem corrects a differently-cased *existing*
    path to the real on-disk spelling before this module's exact-case
    check ever runs — which happens to catch the bug by accident when the
    file is still physically present. Deleting it (still tracked, not
    staged for removal) removes that accidental cover and reproduces the
    actual gap: nothing on disk for ``resolve()`` to correct to, so the
    nominal, differently-cased path is what the tracked check receives.
    """

    def test_a_case_different_tracked_file_is_refused_under_overwrite_nothing_written(
        self, tmp_path: Path
    ) -> None:
        _case_insensitive_fs_or_skip(tmp_path / "probe")

        repo = _init_repo(tmp_path / "project")
        (repo / "agents.md").write_text(
            "tracked, committed, lower-case\n", encoding="utf-8"
        )
        _run_git("add", "agents.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked agents.md (lower-case)", cwd=repo)
        (repo / "agents.md").unlink()  # still tracked, just missing on disk

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        with pytest.raises(layer_copy.TrackedFileConflictError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        # Nothing written at all, under either spelling — the realistic
        # mutation this guards against: writing "AGENTS.md" would, on this
        # filesystem, be writing into the very same on-disk entry the
        # tracked, now-deleted "agents.md" occupies.
        assert not (repo / "AGENTS.md").exists()
        assert not (repo / "agents.md").exists()

    def test_a_case_different_tracked_directory_segment_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The review's own example: a tracked directory differing only in
        case (``.Claude`` vs the layer's ``.claude``) must refuse the same
        way a basename difference does — the comparison is of the whole
        path, not the basename alone."""
        _case_insensitive_fs_or_skip(tmp_path / "probe")

        repo = _init_repo(tmp_path / "project")
        tracked_dir = repo / ".Claude"
        tracked_dir.mkdir()
        (tracked_dir / "settings.json").write_text("{}\n", encoding="utf-8")
        _run_git("add", ".Claude/settings.json", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked .Claude/settings.json", cwd=repo)
        (tracked_dir / "settings.json").unlink()
        # The whole directory too, not just the file inside it: a
        # differently-cased *directory* that still exists on disk would
        # itself get case-corrected by `Path.resolve()`, the same
        # accidental cover the class docstring above describes for a
        # bare file — this must prove the comparison catches the
        # directory-case difference on its own, with nothing left on disk
        # for `resolve()` to correct.
        tracked_dir.rmdir()

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        nested = project_folder / ".claude"
        nested.mkdir()
        (nested / "settings.json").write_text(
            '{"from": "config repo"}\n', encoding="utf-8"
        )

        with pytest.raises(layer_copy.TrackedFileConflictError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
                overwrite=True,
            )

        assert not (repo / ".claude" / "settings.json").exists()
        assert not (repo / ".Claude" / "settings.json").exists()


class TestCaseInsensitiveComparisonItself:
    """Linux-runnable unit tests of the comparison :func:`_is_tracked`
    makes, independent of what the CI host's own filesystem does with two
    differently-cased names — these exercise the git-side logic and the
    ``str.casefold()`` comparison directly, never by creating two
    differently-cased files on disk."""

    def test_a_committed_lower_case_file_is_tracked_under_a_differently_cased_name(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "agents.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "agents.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked agents.md", cwd=repo)

        assert layer_copy._is_tracked(repo, "AGENTS.md") is True  # noqa: SLF001
        # The exact-case spelling, and an unrelated name, are unaffected.
        assert layer_copy._is_tracked(repo, "agents.md") is True  # noqa: SLF001
        assert layer_copy._is_tracked(repo, "CLAUDE.md") is False  # noqa: SLF001

    def test_a_plain_staged_new_file_is_tracked_under_a_differently_cased_name(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "claude.md").write_text("staged, never committed\n", encoding="utf-8")
        _run_git("add", "claude.md", cwd=repo)

        assert layer_copy._is_tracked(repo, "CLAUDE.md") is True  # noqa: SLF001

    def test_an_intent_to_add_differently_cased_name_is_still_not_tracked(
        self, tmp_path: Path
    ) -> None:
        """``git add -N`` stages a placeholder with no real content — not
        refused under its own exact-case name (see
        ``TestIntentToAddIsNotRefused`` above), and this must hold for a
        differently-cased comparison too: ``git ls-files`` would list an
        intent-to-add path exactly as if it had real content, which is
        exactly why the full-listing helpers deliberately use
        ``git diff --cached``/``git ls-tree`` instead."""
        repo = _init_repo(tmp_path / "project")
        (repo / "claude.md").write_text("local, never committed\n", encoding="utf-8")
        _run_git("add", "-N", "claude.md", cwd=repo)

        assert layer_copy._is_tracked(repo, "CLAUDE.md") is False  # noqa: SLF001

    def test_a_tracked_directory_segment_differing_only_in_case_is_tracked(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        tracked_dir = repo / ".Claude"
        tracked_dir.mkdir()
        (tracked_dir / "settings.json").write_text("{}\n", encoding="utf-8")
        _run_git("add", ".Claude/settings.json", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked", cwd=repo)

        assert layer_copy._is_tracked(repo, ".claude/settings.json") is True  # noqa: SLF001

    def test_a_deleted_but_tracked_file_is_still_tracked_under_a_differently_cased_name(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "agents.md").write_text("tracked, committed\n", encoding="utf-8")
        _run_git("add", "agents.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked agents.md", cwd=repo)
        (repo / "agents.md").unlink()

        assert layer_copy._is_tracked(repo, "AGENTS.md") is True  # noqa: SLF001


class TestCaseInsensitiveComparisonIsWholePathNotBasenameOnly:
    """DG-453 review (MEDIUM): a mutation narrowing the comparison to the
    *basename* alone (rather than the whole repo-relative path) passed
    every existing test unnoticed, because none of them had a tracked
    path sharing a basename with the destination while living in a
    different directory. These pin the opposite cases: a shared basename
    in a different directory must never be enough, in either direction."""

    def test_a_tracked_file_with_the_same_basename_in_a_different_directory_is_not_tracked(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        docs_dir = repo / "docs"
        docs_dir.mkdir()
        (docs_dir / "AGENTS.md").write_text(
            "tracked, but a different directory\n", encoding="utf-8"
        )
        _run_git("add", "docs/AGENTS.md", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked docs/AGENTS.md", cwd=repo)

        # A root-level AGENTS.md, same basename, must not be considered
        # tracked just because *some* file with that basename is tracked
        # elsewhere in the repository.
        assert layer_copy._is_tracked(repo, "AGENTS.md") is False  # noqa: SLF001

    def test_a_tracked_nested_file_with_the_same_basename_in_a_different_directory_is_not_tracked(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        nested = repo / ".claude" / "x"
        nested.mkdir(parents=True)
        (nested / "settings.json").write_text("{}\n", encoding="utf-8")
        _run_git("add", ".claude/x/settings.json", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked .claude/x/settings.json", cwd=repo)

        # The layer's own `.claude/settings.json` (one directory level up
        # from the tracked file) must not be considered tracked either —
        # same basename, different directory, the other way round from
        # the test above.
        assert layer_copy._is_tracked(repo, ".claude/settings.json") is False  # noqa: SLF001

    def test_the_reverse_direction_a_tracked_shallower_path_does_not_cover_a_deeper_one(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        claude_dir = repo / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")
        _run_git("add", ".claude/settings.json", cwd=repo)
        _run_git("commit", "-q", "-m", "tracked .claude/settings.json", cwd=repo)

        assert layer_copy._is_tracked(repo, ".claude/x/settings.json") is False  # noqa: SLF001


class TestAnUndecodableTrackedPathFailsClosedWithATypedError:
    """DG-453 review (LOW): ``core.exclude.run_git`` always runs git with
    ``text=True`` and has no keyword yet to ask for raw bytes instead (the
    sibling change that would add one is not merged) — so a path byte
    sequence the platform's default encoding cannot decode under
    ``errors="strict"`` raises a bare ``UnicodeDecodeError`` *inside*
    ``subprocess.run`` itself, before this module ever sees a
    ``CompletedProcess``. Without editing ``core.exclude`` (out of scope:
    DG-355 owns it), the best available fix on this side is to catch that
    and fail closed with this module's own typed error instead of letting
    an undocumented ``UnicodeDecodeError`` escape."""

    def test_an_undecodable_head_listing_raises_the_typed_error_not_a_bare_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        (repo / "committed.txt").write_text("x\n", encoding="utf-8")
        _run_git("add", "committed.txt", cwd=repo)
        _run_git("commit", "-q", "-m", "c", cwd=repo)

        real_run_git = layer_copy.run_git

        def raising_run_git(args, repo_root):
            if args[:1] == ["ls-tree"]:
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "simulated")
            return real_run_git(args, repo_root)

        monkeypatch.setattr(layer_copy, "run_git", raising_run_git)

        with pytest.raises(layer_copy.GitTrackedCheckFailedError):
            layer_copy._all_head_paths(repo)  # noqa: SLF001

    def test_an_undecodable_staged_listing_raises_the_typed_error_not_a_bare_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "project")

        def raising_run_git(args, repo_root):
            if args[:1] == ["diff"]:
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "simulated")
            return layer_copy.run_git(args, repo_root)

        monkeypatch.setattr(layer_copy, "run_git", raising_run_git)

        with pytest.raises(layer_copy.GitTrackedCheckFailedError):
            layer_copy._all_staged_content_paths(repo)  # noqa: SLF001


class TestTheCasefoldedTrackedSetIsComputedOnceNotPerFile:
    """DG-453 review (LOW): :func:`_tracked_paths_casefold` is two
    full-repository git listings — expensive compared with the single-path
    checks :func:`_is_tracked` tries first. :func:`copy_ai_layer_in` must
    compute it once per call, never once per layer file."""

    def test_the_two_full_listings_each_run_exactly_once_for_several_layer_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("a\n", encoding="utf-8")
        (project_folder / "CLAUDE.md").write_text("b\n", encoding="utf-8")
        claude_dir = project_folder / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")

        counts = {"ls_tree": 0, "diff_full_listing": 0}
        real_run_git = layer_copy.run_git

        def counting_run_git(args, repo_root):
            if args[:1] == ["ls-tree"]:
                counts["ls_tree"] += 1
            # The full listing is `diff --cached --name-only -z` with no
            # pathspec — distinct from the per-path exact-case check
            # (`diff --cached --name-only -- <path>`, no `-z`), which must
            # not be counted here.
            elif args[:1] == ["diff"] and "-z" in args:
                counts["diff_full_listing"] += 1
            return real_run_git(args, repo_root)

        monkeypatch.setattr(layer_copy, "run_git", counting_run_git)

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert len(result.copied) == 3
        # The realistic mutation this guards against: calling
        # `_tracked_paths_casefold` (or `_is_tracked` without a cached
        # value) from inside the per-file loop, which would make both
        # counts scale with the number of layer files instead of staying
        # at exactly one each.
        assert counts == {"ls_tree": 1, "diff_full_listing": 1}


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


class TestExcludeRunsBeforeAnyFileIsCopied:
    """MEDIUM review finding: copying first and excluding afterward can
    leave copied, untracked files behind — with a dirty `git status` — if
    the exclude write then fails. The exclude step must run first, so a
    failure there leaves the project tree exactly as it was."""

    def test_a_corrupted_info_exclude_raises_and_nothing_is_copied(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        # An unclosed start marker — exclude.MalformedExcludeBlockError.
        (info_dir / "exclude").write_text(
            f"{exclude.MARKER_START}\n/CLAUDE.md\n", encoding="utf-8"
        )

        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        (project_folder / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        # The realistic mutation this guards against: copying first and
        # excluding last, which would leave these two files sitting on
        # disk, untracked, even though the whole call raised.
        assert not (repo / "AGENTS.md").exists()
        assert not (repo / "CLAUDE.md").exists()

    def test_a_copy_failure_after_exclude_succeeded_reports_what_copied_and_a_rerun_completes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        (project_folder / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

        real_copy2 = layer_copy.shutil.copy2
        calls: list[str] = []

        def flaky_copy2(source, destination):
            calls.append(str(destination))
            if str(destination).endswith("CLAUDE.md"):
                raise OSError("disk full (simulated)")
            return real_copy2(source, destination)

        monkeypatch.setattr(layer_copy.shutil, "copy2", flaky_copy2)

        with pytest.raises(layer_copy.PartialCopyError) as exc_info:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        # Exactly which file was copied before the failure is named, both
        # in the message and in `details`.
        assert "AGENTS.md" in str(exc_info.value)
        assert exc_info.value.details["copied"] == ["AGENTS.md"]
        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "instructions\n"
        assert not (repo / "CLAUDE.md").exists()

        # Fix the underlying problem and re-run: idempotent, completes.
        monkeypatch.setattr(layer_copy.shutil, "copy2", real_copy2)
        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
        # AGENTS.md, already copied and identical, is "unchanged" this
        # time, not re-copied from scratch.
        assert any(
            skip.relative == "AGENTS.md" and skip.identical for skip in result.skipped
        )
        assert "CLAUDE.md" in result.copied


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


class TestContentScanRefusesBeforeAnyWrite:
    """DG-443: a credential-, identity- or path-shaped value in the config
    repo's own AI-layer content is refused, before any copy or exclude
    write — not just a file this project's own git already tracks."""

    def test_a_literal_token_in_the_config_repo_is_refused_before_any_write(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        secret = "ghp_" + "a" * 36
        (project_folder / "AGENTS.md").write_text(
            f"token = {secret}\n", encoding="utf-8"
        )

        before = _run_git("status", "--porcelain", cwd=repo).stdout
        exclude_path = exclude.resolve_info_exclude_path(repo)
        exclude_existed_before = exclude_path.exists()

        with pytest.raises(DrunkenError, match="token"):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert not (repo / "AGENTS.md").exists()
        assert _run_git("status", "--porcelain", cwd=repo).stdout == before
        assert exclude_path.exists() == exclude_existed_before

    def test_two_bad_files_are_named_together_not_one_at_a_time(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "contact jane.doe@realcorp.test\n", encoding="utf-8"
        )
        (project_folder / "CONVENTIONS.md").write_text(
            r"C:\Users\argig\.drunken\secrets.json" + "\n", encoding="utf-8"
        )

        try:
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )
            pytest.fail("expected a refusal")
        except DrunkenError as exc:
            message = str(exc)
            assert "AGENTS.md" in message
            assert "CONVENTIONS.md" in message

    def test_an_example_com_email_in_agents_md_is_not_refused(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "reach us at support@example.com\n", encoding="utf-8"
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert (repo / "AGENTS.md").exists()
        assert "AGENTS.md" in result.copied

    def test_an_undecodable_file_is_refused_as_unscannable(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_bytes("hello".encode("utf-16"))

        with pytest.raises(DrunkenError, match="not UTF-8 text"):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert not (repo / "AGENTS.md").exists()


class TestContentScanAllowlist:
    """DG-443: `.drunken-scan-allow` excuses one exact finding, named, never
    a whole file — and is itself scanned, and is never copied in."""

    def test_an_allowlisted_token_is_copied_not_refused(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        secret = "ghp_" + "a" * 36
        (project_folder / "AGENTS.md").write_text(f"{secret}\n", encoding="utf-8")
        (project_folder / ".drunken-scan-allow").write_text(
            f"AGENTS.md\ttoken\t{secret}\tdocumentation example, not a real token\n",
            encoding="utf-8",
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert "AGENTS.md" in result.copied
        assert not (repo / ".drunken-scan-allow").exists()

    def test_the_allowlist_file_itself_is_not_copied_into_the_project(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("clean\n", encoding="utf-8")
        (project_folder / ".drunken-scan-allow").write_text(
            "AGENTS.md\ttoken\tirrelevant\treason\n", encoding="utf-8"
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert ".drunken-scan-allow" not in result.copied
        assert not (repo / ".drunken-scan-allow").exists()

    def test_an_unlisted_token_in_the_allowlist_file_is_still_refused(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("clean\n", encoding="utf-8")
        stray_secret = "ATATT" + "z" * 24
        (project_folder / ".drunken-scan-allow").write_text(
            f"AGENTS.md\ttoken\tsome-other-value\treason\nstray note: {stray_secret}\n",
            encoding="utf-8",
        )

        with pytest.raises(DrunkenError, match="token"):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

    def test_a_malformed_allowlist_is_refused_before_any_write(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("clean\n", encoding="utf-8")
        (project_folder / ".drunken-scan-allow").write_text(
            "only-two\tfields\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert not (repo / "AGENTS.md").exists()


class TestValidateAiLayerCopyIsWriteFree:
    """DG-443: the validation phase `drunken-init` calls before touching the
    registry must itself write nothing — re-running the real copy
    afterwards is still the only thing that writes."""

    def test_validate_only_leaves_the_project_tree_untouched(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("clean\n", encoding="utf-8")

        before = _run_git("status", "--porcelain", cwd=repo).stdout
        layer_copy.validate_ai_layer_copy(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )
        assert not (repo / "AGENTS.md").exists()
        assert _run_git("status", "--porcelain", cwd=repo).stdout == before

    def test_validate_only_still_raises_on_a_bad_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        secret = "ghp_" + "a" * 36
        (project_folder / "AGENTS.md").write_text(secret, encoding="utf-8")

        with pytest.raises(DrunkenError, match="token"):
            layer_copy.validate_ai_layer_copy(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )


class TestAiLayerFilesUnderNeverDescendsIntoANestedRepository:
    """DG-443 review (comment 11482, decision 7): `ai_layer_files_under` is
    now also walked, read-only, against a *real* project's own checkout by
    `drunken-doctor` — not only a config repo's small, author-controlled
    folder. `.claude` is walked to any depth, and a real project's
    `.claude/worktrees/<agent>/` (Claude Code's own `git worktree` feature)
    is a full, independent checkout each, with its own dependency tree —
    without this guard, walking one real project with a handful of active
    worktrees turned a few thousand files into roughly a million and a
    diagnostic command into a multi-minute hang (seen directly against a
    real registered project on the machine this was found on)."""

    def test_a_nested_worktree_directory_is_not_descended_into(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "proj"
        root.mkdir()
        claude_dir = root / ".claude" / "worktrees" / "agent-x"
        claude_dir.mkdir(parents=True)
        # A `git worktree`'s own `.git` is a *file*, not a directory —
        # pointing back at the main repository's `.git/worktrees/<name>`.
        (claude_dir / ".git").write_text(
            "gitdir: /somewhere/else/.git/worktrees/agent-x\n", encoding="utf-8"
        )
        (claude_dir / "AGENTS.md").write_text(
            "from inside the nested worktree\n", encoding="utf-8"
        )

        found = layer_copy.ai_layer_files_under(root)

        assert not any("agent-x" in f.as_posix() for f in found), (
            f"must never descend into a nested worktree. Found: {found}"
        )

    def test_a_nested_ordinary_clone_is_not_descended_into(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "proj"
        root.mkdir()
        nested = root / "vendor" / "some-package"
        nested.mkdir(parents=True)
        (nested / ".git").mkdir()
        # A real git directory always has HEAD — see
        # test_a_fake_dot_git_directory_with_no_head_is_not_a_boundary for
        # the case where it does not.
        (nested / ".git" / "HEAD").write_text(
            "ref: refs/heads/main\n", encoding="utf-8"
        )
        (nested / "AGENTS.md").write_text(
            "from inside a nested clone\n", encoding="utf-8"
        )

        found = layer_copy.ai_layer_files_under(root)

        assert not any("some-package" in f.as_posix() for f in found), (
            f"must never descend into a nested repository. Found: {found}"
        )

    def test_a_fake_dot_git_directory_with_no_head_is_not_a_boundary(
        self, tmp_path: Path
    ) -> None:
        """DG-443 review round 2: a directory merely *named* `.git`, with
        no `HEAD` inside it, is not a real git marker — the walk must keep
        going through it (and so must the content scan, since both share
        this same walk), not silently hide whatever is under it."""
        root = tmp_path / "proj"
        root.mkdir()
        fake_git_dir = root / "hooks" / ".git"
        fake_git_dir.mkdir(parents=True)
        (fake_git_dir / "not-a-head-file.txt").write_text("decoy\n", encoding="utf-8")
        secret_holder = root / "hooks" / "AGENTS.md"
        secret_holder.write_text(
            "token = " + "ghp_" + "a" * 36 + "\n", encoding="utf-8"
        )

        found = layer_copy.ai_layer_files_under(root)

        assert Path("hooks/AGENTS.md") in found, (
            f"a fake .git directory (no HEAD) must not hide what is under "
            f"it. Found: {found}"
        )

    def test_a_fake_dot_git_file_with_unrelated_content_is_not_a_boundary(
        self, tmp_path: Path
    ) -> None:
        """The file-shaped twin of the test above: a plain file named
        `.git` whose content does not start with `gitdir:` is not a
        worktree pointer, and must not hide a sibling AI-layer file."""
        root = tmp_path / "proj"
        root.mkdir()
        decoy_dir = root / "notes"
        decoy_dir.mkdir()
        (decoy_dir / ".git").write_text(
            "just some notes, not a pointer\n", encoding="utf-8"
        )
        (decoy_dir / "AGENTS.md").write_text("plain instructions\n", encoding="utf-8")

        found = layer_copy.ai_layer_files_under(root)

        assert Path("notes/AGENTS.md") in found, (
            f"a file merely named .git, with unrelated content, must not "
            f"hide a sibling file. Found: {found}"
        )

    def test_a_secret_under_a_fake_git_marker_is_found_by_both_copy_and_the_walk(
        self, tmp_path: Path
    ) -> None:
        """Decision 7's explicit ask: prove the copy path and doctor's
        read-only re-scan cannot disagree, because both go through this
        one walk. A fake `.git` directory (no HEAD) must not make a
        secret file underneath invisible to either."""
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        fake_git_dir = project_folder / "hooks" / ".git"
        fake_git_dir.mkdir(parents=True)
        secret = "ghp_" + "b" * 36
        (project_folder / "hooks" / "AGENTS.md").write_text(
            f"token = {secret}\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError, match="token"):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        # The walk itself (what doctor's read-only re-scan also calls)
        # must report the file too — not just the refusal above.
        found = layer_copy.ai_layer_files_under(project_folder)
        assert Path("hooks/AGENTS.md") in found

    def test_the_root_itself_having_a_dot_git_is_still_walked(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        (root / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        found = layer_copy.ai_layer_files_under(root)

        assert Path("AGENTS.md") in found, (
            "root's own .git must not make this mistake root for a nested "
            f"repository and skip it entirely. Found: {found}"
        )

    def test_mutation_a_naive_walk_with_no_guard_would_have_found_it(
        self, tmp_path: Path
    ) -> None:
        """Not a monkeypatch of production code — a small, honest replica
        of the *pre-fix* walk (no nested-repository check at all), run
        against the exact same fixture the real test above uses, to prove
        that fixture really does exercise the guard rather than being
        vacuously true for some unrelated reason (e.g. `AGENTS.md` not
        being on the AI-layer list at all)."""
        root = tmp_path / "proj"
        root.mkdir()
        claude_dir = root / ".claude" / "worktrees" / "agent-x"
        claude_dir.mkdir(parents=True)
        (claude_dir / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (claude_dir / "AGENTS.md").write_text("nested\n", encoding="utf-8")

        from core.ai_layer import is_ai_layer_path

        naive_found = [
            p.relative_to(root)
            for p in root.rglob("*")
            if p.is_file() and is_ai_layer_path(p.relative_to(root).as_posix())
        ]

        assert any("agent-x" in p.as_posix() for p in naive_found), (
            "the fixture itself must be reachable by a guard-less walk, or "
            "the real test above proves nothing about the guard"
        )


def _write_sleepy_git(bin_dir: Path, sleep_seconds: float) -> None:
    """A git stand-in that sleeps for *sleep_seconds* then exits 0, for
    proving a real ``subprocess`` timeout fires rather than a mocked
    return value. Bounded: this never sleeps forever, so a test exercising
    it is bounded by *sleep_seconds* even if the timeout under test fails
    to apply at all.

    Duplicated from ``tests/test_exclude.py``'s identical helper rather
    than imported across test modules — see that copy's docstring for why
    Windows needs a copy of the current interpreter plus a
    ``sitecustomize.py`` rather than a ``.bat``/``.cmd`` file: a bare name
    with no extension only gets ``.exe`` auto-appended by Windows'
    ``CreateProcess``, so a batch file here would be invisible to the
    lookup and silently fall through to the real ``git.exe`` elsewhere on
    ``PATH``.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        git_path = bin_dir / "git.exe"
        shutil.copy2(sys.executable, git_path)
        (bin_dir / "sitecustomize.py").write_text(
            f"import time, os\ntime.sleep({sleep_seconds})\nos._exit(0)\n",
            encoding="utf-8",
        )
    else:
        git_path = bin_dir / "git"
        git_path.write_text(
            f"#!/bin/sh\nsleep {sleep_seconds}\nexit 0\n", encoding="utf-8"
        )
        git_path.chmod(0o755)


def _prepend_sleepy_git_to_path(monkeypatch: pytest.MonkeyPatch, bin_dir: Path) -> None:
    """``monkeypatch.setenv`` specifically, not a one-off ``env=`` dict
    built for a single subprocess call: Windows' ``CreateProcess``
    resolves which executable a bare name like ``"git"`` finds using the
    *calling* process's own environment, not whatever is later passed as
    ``env=`` — ``monkeypatch.setenv`` mutates this process's real
    ``os.environ``, which is what that lookup actually reads."""
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    if sys.platform == "win32":
        monkeypatch.setenv(
            "PYTHONPATH", f"{bin_dir}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"
        )


class TestCopyInRefusesWhenGitHangs:
    """DG-454: copy-in must never proceed as though a path were untracked
    just because git could not answer within the timeout. A real git
    stand-in that sleeps past the timeout — not a mocked ``run_git`` — is
    used here so this proves the ``subprocess.run(timeout=...)`` plumbing
    actually fires; see ``tests/test_exclude.py::TestRunGitTimeout`` for
    the same mechanism proven in isolation, against ``run_git`` directly."""

    def test_copy_in_refuses_and_writes_nothing_when_git_hangs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        # A tiny timeout for *this test*, not the real
        # DEFAULT_GIT_TIMEOUT_SECONDS — the suite must not wait out the
        # real 30s default. copy_ai_layer_in passes no timeout of its own
        # to any of its run_git calls, so it is this default that must
        # bound it.
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_sleepy_git_to_path(monkeypatch, bin_dir)

        with pytest.raises(exclude.GitTimedOutError):
            layer_copy.copy_ai_layer_in(
                config_repo=config_repo,
                project_id="sample",
                project_root=repo,
                git_root=repo,
            )

        assert not (repo / "AGENTS.md").exists(), (
            "a hung git must refuse before a single byte is copied, not "
            'silently treat the timeout as "not tracked" and proceed'
        )

    def test_a_tracked_check_timeout_raises_rather_than_answering_not_tracked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Targets the tracked-check layer directly, bypassing
        # resolve_info_exclude_path's own earlier git calls (which would
        # otherwise be the first thing to hit the hung stand-in) — this is
        # the specific claim the SCOPE names: a timeout inside a
        # tracked-file check must never fall through to "not tracked".
        repo = _init_repo(tmp_path / "project")

        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_sleepy_git_to_path(monkeypatch, bin_dir)

        with pytest.raises(exclude.GitTimedOutError):
            layer_copy._has_staged_content(repo, "AGENTS.md")  # noqa: SLF001


class TestAMcpJsonIsNeverCopiedIn:
    """DG-457 review: ``.mcp.json`` is on the AI-layer list so the doctor flags a tracked one and
    the exclude file hides a stray one — but a project carries none (REQ-019 Decided 2026-10-10),
    so the copy-in must not be the thing that puts one there."""

    def test_a_mcp_json_in_the_config_repo_is_not_copied_into_the_project(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "project")
        config_repo = _config_repo(tmp_path)
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        (project_folder / ".mcp.json").write_text(
            '{"mcpServers": {"drunken-jira-mcp": {"command": "drunken-jira-mcp"}}}\n',
            encoding="utf-8",
        )

        result = layer_copy.copy_ai_layer_in(
            config_repo=config_repo,
            project_id="sample",
            project_root=repo,
            git_root=repo,
        )

        assert not (repo / ".mcp.json").exists(), (
            "the copy-in recreated the file DG-457 removes from a project"
        )
        assert result.copied == ("AGENTS.md",)

    def test_the_file_list_never_offers_it(self, tmp_path: Path) -> None:
        folder = tmp_path / "folder"
        folder.mkdir()
        (folder / ".mcp.json").write_text("{}\n", encoding="utf-8")
        (folder / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")

        assert [p.as_posix() for p in layer_copy.ai_layer_files_under(folder)] == [
            "CLAUDE.md"
        ]
