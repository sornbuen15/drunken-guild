# mypy: ignore-errors
"""DG-440 (REQ-019/REQ-020). The .git/info/exclude writer.

Hides a project's copied-in AI layer from its own git, between markers,
idempotently, in a plain clone and in a `git worktree`. The patterns come
from the one AI-layer list (DG-437, `core.ai_layer`) — this module adds no
second list of paths.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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


class TestGitSubprocessEnvStripsEveryGitVariable:
    """Review finding (DG-441 PR #144): a fixed three-name strip list missed
    `GIT_INDEX_FILE` and every other `GIT_*` variable that changes what git
    answers without touching repository *resolution*. The rule is now "every
    name starting with GIT_", not a list — proven directly against
    :func:`git_subprocess_env`, independent of any one caller."""

    @pytest.mark.parametrize(
        "name",
        [
            "GIT_DIR",
            "GIT_COMMON_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_NAMESPACE",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
            "GIT_CEILING_DIRECTORIES",
            "GIT_ATTR_SOURCE",
            "git_index_file",  # lower-case: os.environ is case-insensitive on Windows
        ],
    )
    def test_every_git_prefixed_name_is_stripped(
        self, name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(name, "leaked-value")

        env = exclude.git_subprocess_env()

        # GIT_TERMINAL_PROMPT is the one deliberate exception (DG-454): it
        # is this module's own override, set *after* the strip, never a
        # passthrough of anything inherited — see
        # TestGitSubprocessEnvDisablesTerminalPrompt below for that claim
        # checked on its own.
        survivors = [
            key
            for key in env
            if key.upper().startswith("GIT_") and key.upper() != "GIT_TERMINAL_PROMPT"
        ]
        assert not survivors, (
            f"{name!r} (or another GIT_-prefixed key) survived stripping: {survivors}"
        )

    def test_a_mixed_environment_strips_every_git_key_and_keeps_the_rest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GIT_DIR", "x")
        monkeypatch.setenv("GIT_INDEX_FILE", "y")
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/somewhere/else")
        monkeypatch.setenv("NOT_GIT_RELATED", "kept")
        monkeypatch.setenv("PATH", "/usr/bin")

        env = exclude.git_subprocess_env()

        survivors = [
            key
            for key in env
            if key.upper().startswith("GIT_") and key.upper() != "GIT_TERMINAL_PROMPT"
        ]
        assert not survivors
        assert env.get("NOT_GIT_RELATED") == "kept"
        assert env.get("PATH") == "/usr/bin"


class TestGitSubprocessEnvDisablesTerminalPrompt:
    """DG-454: a credential prompt is one more way a git call can block —
    past *timeout*'s "wait, then fail" into "wait, prompt an unattended
    process's stdin, and fail anyway". ``GIT_TERMINAL_PROMPT=0`` makes git
    refuse to prompt and exit immediately instead."""

    def test_git_terminal_prompt_is_disabled(self) -> None:
        env = exclude.git_subprocess_env()
        assert env.get("GIT_TERMINAL_PROMPT") == "0"

    def test_an_inherited_terminal_prompt_opt_in_is_overridden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A caller's own process could have GIT_TERMINAL_PROMPT=1 set
        # (asking for prompts) — this module's own "never prompt" rule
        # wins regardless of what was inherited.
        monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")

        env = exclude.git_subprocess_env()

        assert env.get("GIT_TERMINAL_PROMPT") == "0"


def _write_sleepy_git(bin_dir: Path, sleep_seconds: float) -> None:
    """A git stand-in that sleeps for *sleep_seconds* then exits 0,
    regardless of what it was called with — for proving a real
    ``subprocess`` timeout fires, not a mocked return value. Bounded: this
    never sleeps forever, so a test exercising it is bounded by
    *sleep_seconds* even if the timeout under test fails to apply at all
    (the mutation this is built to catch).

    On POSIX this is a plain shebang script named ``git`` — the OS finds
    it on ``PATH`` the same way it finds the real binary.

    On Windows, a file merely named ``git.bat``/``git.cmd`` is invisible to
    this lookup: when ``subprocess`` gives Windows' ``CreateProcess`` a bare
    name with no extension, the OS auto-appends **only** ``.exe`` before
    searching ``PATH`` — ``.bat``/``.cmd`` resolution through ``PATHEXT`` is
    a feature of ``cmd.exe`` itself, not of ``CreateProcess`` called this
    way, so a batch file here would silently fall through to the real
    ``git.exe`` found later on ``PATH`` (verified empirically: it did, and
    the test using one passed for the wrong reason — it still used real
    git). This copies the current Python interpreter to ``git.exe`` instead
    (a real, already-valid executable) and drops a ``sitecustomize.py``
    beside it on ``PYTHONPATH``: Python imports ``sitecustomize`` during
    interpreter start-up, *before* it ever tries to open ``sys.argv[1]``
    ("status", "rev-parse", ...) as a script file, so the sleep (and the
    process exit) happens before Python ever notices those arguments do
    not name a real file.
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


def _prepend_to_path(monkeypatch: pytest.MonkeyPatch, bin_dir: Path) -> None:
    """Put *bin_dir* ahead of ``PATH`` (and, on Windows, ``PYTHONPATH`` —
    see :func:`_write_sleepy_git`) using ``monkeypatch.setenv`` specifically
    rather than building a one-off ``env=`` dict for the subprocess call:
    Windows' ``CreateProcess`` resolves *which* executable a bare name like
    ``"git"`` finds using the **calling process's own** environment, not
    whatever is later passed as ``env=`` to ``subprocess.run`` — verified
    empirically, since that is the opposite of the first (reasonable)
    assumption. ``monkeypatch.setenv`` mutates this process's real
    ``os.environ``, which is what that search actually reads.
    """
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    if sys.platform == "win32":
        monkeypatch.setenv(
            "PYTHONPATH", f"{bin_dir}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"
        )


class TestRunGitTimeout:
    """DG-454: ``run_git`` must not be able to hang forever. A real git
    stand-in that sleeps past the timeout — not a mocked ``run_git`` — is
    used here so this actually proves the ``subprocess.run(timeout=...)``
    plumbing fires, not merely that some code path returns an error."""

    def test_an_explicit_timeout_raises_fail_closed_naming_command_and_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_to_path(monkeypatch, bin_dir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        with pytest.raises(exclude.GitTimedOutError) as exc_info:
            exclude.run_git(["status"], repo_root, timeout=0.2)

        message = str(exc_info.value)
        assert "git status" in message, (
            f"the error should name the git command that hung: {message!r}"
        )
        assert "0.2" in message, (
            f"the error should name the timeout that was hit: {message!r}"
        )

    def test_the_default_timeout_applies_when_the_caller_passes_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A tiny timeout for *this test*, not DEFAULT_GIT_TIMEOUT_SECONDS
        # itself — the suite must not wait out the real 30s default. This
        # is exactly the line a mutation deleting "use the default when
        # none is given" would remove: with it gone, the call below falls
        # back to no bound at all, waits out the full sleep below, and
        # this goes red (bounded at the stand-in's own sleep, not forever).
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_to_path(monkeypatch, bin_dir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        with pytest.raises(exclude.GitTimedOutError):
            exclude.run_git(["status"], repo_root)  # no timeout passed at all

    def test_git_timed_out_error_is_not_a_not_a_git_repository_error(self) -> None:
        # The load-bearing property this whole review turn exists for
        # (DG-454 review): a caller written as `except
        # NotAGitRepositoryError` to mean "nothing here to protect" must
        # NOT also, silently, catch a timeout that way.
        assert not issubclass(exclude.GitTimedOutError, exclude.NotAGitRepositoryError)
        assert issubclass(exclude.GitTimedOutError, exclude.GitCommandError)
        assert issubclass(exclude.NotAGitRepositoryError, exclude.GitCommandError)


class TestGitTimeoutEnvVarOverride:
    """DG-454 review (MEDIUM): an operator whose checkout genuinely needs
    longer than the 30s default (a large network filesystem, say) can say
    so without editing source, via DRUNKEN_GIT_TIMEOUT. An invalid value
    is ignored and falls back to the default — never read as "no limit"."""

    def test_a_valid_override_is_used(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(exclude.GIT_TIMEOUT_ENV_VAR, "0.2")
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_to_path(monkeypatch, bin_dir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        with pytest.raises(exclude.GitTimedOutError) as exc_info:
            exclude.run_git(["status"], repo_root)  # no timeout passed at all

        assert "0.2" in str(exc_info.value)

    @pytest.mark.parametrize("raw", ["not-a-number", "", "abc"])
    def test_an_invalid_value_is_ignored_not_treated_as_no_limit(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(exclude.GIT_TIMEOUT_ENV_VAR, raw)
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)

        assert exclude._resolve_default_git_timeout() == 0.2  # noqa: SLF001

    @pytest.mark.parametrize("raw", ["0", "-1", "-0.5"])
    def test_zero_or_negative_is_ignored_not_treated_as_no_limit(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(exclude.GIT_TIMEOUT_ENV_VAR, raw)
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)

        assert exclude._resolve_default_git_timeout() == 0.2  # noqa: SLF001

    @pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "1e100", "99999"])
    def test_non_finite_or_absurd_values_are_ignored_not_treated_as_no_limit(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DG-454 review (MEDIUM): ``float()`` parses ``"nan"``/``"inf"``
        without raising, and a plain ``value <= 0`` check lets both
        ``inf`` and an absurdly large finite value like ``1e100`` straight
        through — observed directly: ``subprocess.run(timeout=float("inf"))``
        raises a bare, uncaught ``OverflowError``; ``nan`` raises
        ``ValueError`` at the same point; and ``1e100`` does not crash but
        fires an almost-immediate spurious ``TimeoutExpired`` instead of
        the longer wait the caller asked for. None of these are "a valid
        override," and must fall back to the default exactly like any
        other invalid value.
        """
        monkeypatch.setenv(exclude.GIT_TIMEOUT_ENV_VAR, raw)
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)

        assert exclude._resolve_default_git_timeout() == 0.2  # noqa: SLF001

    def test_a_valid_override_within_the_ceiling_is_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(exclude.GIT_TIMEOUT_ENV_VAR, "45")
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)

        assert exclude._resolve_default_git_timeout() == 45.0  # noqa: SLF001

    def test_unset_falls_back_to_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(exclude.GIT_TIMEOUT_ENV_VAR, raising=False)
        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 7.0)

        assert exclude._resolve_default_git_timeout() == 7.0  # noqa: SLF001

    def test_the_remediation_names_the_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_to_path(monkeypatch, bin_dir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        with pytest.raises(exclude.GitTimedOutError) as exc_info:
            exclude.run_git(["status"], repo_root, timeout=0.2)

        assert exc_info.value.remediation is not None
        assert exclude.GIT_TIMEOUT_ENV_VAR in exc_info.value.remediation
