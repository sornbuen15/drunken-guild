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


class TestInheritedGitEnvironmentIsIgnored:
    """A caller's own process (e.g. a git hook, or init running inside one)
    may have GIT_DIR / GIT_COMMON_DIR / GIT_WORK_TREE set, pointing at a
    completely different repository. `git rev-parse` honours those over the
    cwd it is given, so a naive subprocess call resolves — and then writes
    into — the *other* repository's info/exclude instead of repo_root's own.
    """

    def test_git_dir_pointing_elsewhere_does_not_redirect_a_real_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = _init_repo(tmp_path / "unrelated")
        repo = _init_repo(tmp_path / "repo")
        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))

        result = exclude.exclude_ai_layer(repo)

        assert result.exclude_path == repo / ".git" / "info" / "exclude"
        unrelated_exclude = unrelated / ".git" / "info" / "exclude"
        unrelated_text = (
            unrelated_exclude.read_text(encoding="utf-8")
            if unrelated_exclude.exists()
            else ""
        )
        assert exclude.MARKER_START not in unrelated_text, (
            "the unrelated repo picked up by a leaked GIT_DIR must not be written to"
        )

    def test_git_common_dir_pointing_elsewhere_does_not_redirect_a_real_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = _init_repo(tmp_path / "unrelated")
        repo = _init_repo(tmp_path / "repo")
        monkeypatch.setenv("GIT_COMMON_DIR", str(unrelated / ".git"))

        result = exclude.exclude_ai_layer(repo)

        assert result.exclude_path == repo / ".git" / "info" / "exclude"

    def test_git_dir_pointing_elsewhere_still_refuses_a_non_repo_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = _init_repo(tmp_path / "unrelated")
        not_a_repo = tmp_path / "not-a-repo"
        not_a_repo.mkdir()
        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))

        with pytest.raises(DrunkenError):
            exclude.exclude_ai_layer(not_a_repo)

        unrelated_exclude = unrelated / ".git" / "info" / "exclude"
        unrelated_text = (
            unrelated_exclude.read_text(encoding="utf-8")
            if unrelated_exclude.exists()
            else ""
        )
        assert exclude.MARKER_START not in unrelated_text, (
            "a non-repo folder must raise, never fall through to a repo "
            "found only via a leaked GIT_DIR"
        )
        assert not (not_a_repo / ".git").exists()

    def test_git_common_dir_pointing_elsewhere_still_refuses_a_non_repo_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        unrelated = _init_repo(tmp_path / "unrelated")
        not_a_repo = tmp_path / "not-a-repo"
        not_a_repo.mkdir()
        monkeypatch.setenv("GIT_COMMON_DIR", str(unrelated / ".git"))

        with pytest.raises(DrunkenError):
            exclude.exclude_ai_layer(not_a_repo)

        unrelated_exclude = unrelated / ".git" / "info" / "exclude"
        unrelated_text = (
            unrelated_exclude.read_text(encoding="utf-8")
            if unrelated_exclude.exists()
            else ""
        )
        assert exclude.MARKER_START not in unrelated_text


class TestMalformedExcludeBlockIsRefused:
    """A marker block interrupted mid-write (process killed between the
    start marker and the end marker) must never be silently appended a
    second time — that is how a non-atomic writer accumulates duplicate
    blocks. It must be named and refused instead.
    """

    def test_start_marker_without_end_marker_raises(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_path = info_dir / "exclude"
        exclude_path.write_text(
            f"*.pyc\n{exclude.MARKER_START}\n/CLAUDE.md\n", encoding="utf-8"
        )

        with pytest.raises(DrunkenError):
            exclude.exclude_ai_layer(repo)

        # The realistic mutation this guards against: an implementation
        # that only counts missing *patterns* (not markers) would treat
        # /CLAUDE.md as already present and the file as fine, then append
        # a second start marker the next time a new pattern was added —
        # proving the file was never actually validated.
        text = exclude_path.read_text(encoding="utf-8")
        assert text.count(exclude.MARKER_START) == 1, (
            "a failed call must not have appended anything at all"
        )

    def test_end_marker_without_start_marker_raises(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_path = info_dir / "exclude"
        exclude_path.write_text(f"/CLAUDE.md\n{exclude.MARKER_END}\n", encoding="utf-8")

        with pytest.raises(DrunkenError):
            exclude.exclude_ai_layer(repo)

    def test_reversed_markers_with_equal_counts_raises(self, tmp_path: Path) -> None:
        # The realistic mutation this guards against: counting START and
        # END occurrences (equal, 1 and 1) and calling that well-formed. An
        # END that appears *before* any open START is not a valid block
        # even though the counts match.
        repo = _init_repo(tmp_path / "repo")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_path = info_dir / "exclude"
        exclude_path.write_text(
            f"{exclude.MARKER_END}\n/CLAUDE.md\n{exclude.MARKER_START}\n",
            encoding="utf-8",
        )

        with pytest.raises(DrunkenError) as exc_info:
            exclude.exclude_ai_layer(repo)
        # Names the file and the line number, not just "malformed".
        assert str(exclude_path) in str(exc_info.value)
        assert "1" in str(exc_info.value), (
            "the end-before-start marker is on line 1 — the message should name it"
        )

    def test_two_complete_blocks_are_accepted(self, tmp_path: Path) -> None:
        # Nothing breaks an existing file that already has two complete,
        # well-formed pairs — only a *mismatched* or *reversed* block is
        # malformed.
        repo = _init_repo(tmp_path / "repo")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_path = info_dir / "exclude"
        exclude_path.write_text(
            f"{exclude.MARKER_START}\n/CLAUDE.md\n{exclude.MARKER_END}\n"
            f"{exclude.MARKER_START}\n/AGENTS.md\n{exclude.MARKER_END}\n",
            encoding="utf-8",
        )

        result = exclude.exclude_ai_layer(repo)

        assert result.exclude_path == exclude_path

    def test_substring_mention_of_the_marker_is_not_treated_as_a_marker(
        self, tmp_path: Path
    ) -> None:
        # A human comment that merely *mentions* the marker text — e.g.
        # documenting it — must not trip the check. The realistic mutation
        # this guards against: counting substring occurrences
        # (`text.count(MARKER_START)`) instead of exact, stripped line
        # equality; that mutation sees this single line as "one start, zero
        # end" and wrongly raises on a file that has no real block at all.
        repo = _init_repo(tmp_path / "repo")
        info_dir = repo / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude_path = info_dir / "exclude"
        exclude_path.write_text(
            f"# example: {exclude.MARKER_START}\n", encoding="utf-8"
        )

        # Must not raise: there is no real marker line here, only a comment
        # that contains the marker text as a substring.
        result = exclude.exclude_ai_layer(repo)

        assert result.added, "the real patterns should still have been added"


class TestToplevelCrossCheckIsActuallyExercised:
    """The env-leak tests prove the toplevel cross-check catches a leaked
    GIT_DIR/GIT_COMMON_DIR. Neither proves the check itself does anything —
    a mutation that always treats `reported_toplevel` as equal to
    `repo_root` would pass every one of them unchanged (no env var is
    involved in either path). These exercise the check with no environment
    variable set at all.
    """

    def test_non_root_subdirectory_of_a_real_repo_raises_naming_the_toplevel(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        subdir = repo / "sub"
        subdir.mkdir()

        with pytest.raises(DrunkenError) as exc_info:
            exclude.exclude_ai_layer(subdir)

        assert str(repo.resolve()) in str(exc_info.value), (
            "the error should name the toplevel git actually resolved "
            f"({repo.resolve()}), not just say 'not a git repository'"
        )

    def test_monkeypatched_run_git_reporting_a_different_toplevel_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No real git worktree/env trickery at all — just the two calls
        # resolve_info_exclude_path() makes, with the second one reporting
        # a toplevel that is not repo_root. This isolates the cross-check
        # itself from everything else in the function.
        repo_root = tmp_path / "repo_root"
        repo_root.mkdir()
        different_toplevel = tmp_path / "elsewhere"
        different_toplevel.mkdir()

        def fake_run_git(
            args: list[str], repo_root_arg: Path
        ) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["rev-parse", "--git-path"]:
                return subprocess.CompletedProcess(
                    args, 0, stdout="info/exclude\n", stderr=""
                )
            if args[:2] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(
                    args, 0, stdout=f"{different_toplevel}\n", stderr=""
                )
            raise AssertionError(f"unexpected git args in test double: {args}")

        monkeypatch.setattr(exclude, "run_git", fake_run_git)

        with pytest.raises(DrunkenError) as exc_info:
            exclude.resolve_info_exclude_path(repo_root)

        assert str(different_toplevel.resolve()) in str(exc_info.value)
