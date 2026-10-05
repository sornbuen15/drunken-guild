# mypy: ignore-errors
"""DG-438: a registered project whose own git tracks any AI-layer path fails
`drunken-doctor`'s ``layering.tracked`` check — REQ-019 says that stays out of
a project's repository, and nothing noticed until now.

Every scratch repository here is real git, under ``tmp_path`` — not a mock —
because the thing under test is what ``git ls-files`` actually reports, and a
mocked git would only prove the test author's own assumption about that.
"""

import json
import subprocess
import sys

import pytest

from core import ai_layer, doctor
from core.registry import ProjectRegistry

GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]


def _git(*args: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *GIT_IDENTITY, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(root) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def _commit_all(root, message: str) -> None:
    _git("add", "-A", cwd=root)
    _git("commit", "-m", message, "-q", cwd=root)


def find(report: doctor.Report, name: str) -> doctor.Check:
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(
        f"no check named {name!r} in {[c.name for c in report.checks]}"
    )


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    # Redirect everything away from the real machine, the same way the rest
    # of the doctor suite does: a stray write or read of the real home or
    # registry here would be the DG-291 failure mode all over again.
    monkeypatch.setenv("DRUNKEN_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DRUNKEN_REGISTRY_PATH", raising=False)


def _registry(tmp_path, project_id: str, path) -> ProjectRegistry:
    target = tmp_path / "projects.json"
    target.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {project_id: {"path": str(path)}},
            }
        ),
        encoding="utf-8",
    )
    return ProjectRegistry(str(target))


class TestATrackedAiLayerPathFails:
    def test_a_tracked_agents_md_fails_with_the_path_named(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", check.detail
        assert "AGENTS.md" in check.detail

    def test_a_tracked_nested_claude_md_fails_with_the_path_named(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "x"
        nested.mkdir(parents=True)
        (nested / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", check.detail
        assert "packages/x/CLAUDE.md" in check.detail

    def test_mutation_a_check_that_never_fails_is_caught(self, tmp_path, monkeypatch):
        """Wiring only: stubs `tracked_ai_layer_paths` itself, so this proves
        the branch in `_check_project_layering` that turns a tracked path into
        a "fail" actually runs. It says nothing about git or quoting — that is
        `TestNonAsciiAndSpecialCharacterPaths` and the real-repo tests above,
        which exercise the real subprocess call."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        _commit_all(root, "initial")
        monkeypatch.setattr(doctor, "tracked_ai_layer_paths", lambda git_root: [])

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "ok", (
            "this assertion is the mutation's own 'pass' — the real check "
            f"must disagree with it. Got {check.status}: {check.detail}"
        )


class TestACleanProjectPasses:
    def test_a_project_tracking_only_prd_and_source_passes(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".ai").mkdir()
        (root / ".ai" / "PRD.md").write_text("# PRD", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "ok", check.detail

    def test_mutation_a_check_that_always_fails_is_caught(self, tmp_path, monkeypatch):
        """Wiring only: stubs `tracked_ai_layer_paths` itself, so this proves
        the branch that turns an empty result into "ok" actually runs. It
        says nothing about git or quoting — see the note on the sibling
        mutation test above."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")
        monkeypatch.setattr(
            doctor, "tracked_ai_layer_paths", lambda git_root: ["AGENTS.md"]
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", (
            f"the mutation must flip this clean project to fail. Got "
            f"{check.status}: {check.detail}"
        )


class TestUntrackedAiLayerFilesPass:
    def test_ai_layer_files_present_but_untracked_pass(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")
        # AGENTS.md exists on disk, after the commit, and is never staged.
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "ok", check.detail


class TestNonAsciiAndSpecialCharacterPaths:
    """DG-438 review: plain `git ls-files` C-quotes a path holding a
    non-ASCII byte or a special character, and the quoted text never equals
    the real path — a silent false negative on exactly the files this check
    exists to catch. `tracked_ai_layer_paths` must use `-z` and decode the
    NUL-separated bytes instead.
    """

    def test_a_non_ascii_nested_directory_fails_with_the_real_path_named(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "café"
        nested.mkdir(parents=True)
        (nested / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", check.detail
        assert "packages/café/CLAUDE.md" in check.detail, check.detail

    def test_mutation_plain_ls_files_quotes_the_non_ascii_path_away(self, tmp_path):
        """Seen failing first, against the pre-fix shape of the code: plain
        `git ls-files` (no `-z`) quotes the non-ASCII path as the literal
        text `"packages/caf\\303\\251/CLAUDE.md"` — quote marks and octal
        escapes included — which never equals the real path, so
        `core.ai_layer.is_ai_layer_path` never matches it. This is that call,
        made directly, asserting the old behaviour is still exactly this bad.
        """
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "café"
        nested.mkdir(parents=True)
        (nested / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        quoted = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        matched = [path for path in quoted if ai_layer.is_ai_layer_path(path)]

        assert matched == [], (
            "plain `git ls-files` must still quote the non-ASCII path so it "
            f"no longer matches — that is the bug `-z` fixes. ls-files said "
            f"{quoted!r}, none of which matched"
        )

    def test_a_directory_name_with_a_space_still_matches(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "with space"
        nested.mkdir(parents=True)
        (nested / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", check.detail
        assert "packages/with space/CLAUDE.md" in check.detail, check.detail

    def test_a_directory_name_with_a_double_quote_still_matches(self, tmp_path):
        """A literal `"` is always quoted by git, regardless of
        `core.quotepath`, whatever bytes it sits beside — the same class of
        bug as the non-ASCII case above, triggered without a non-ASCII byte
        at all. Not every filesystem under CI can hold one: NTFS rejects it
        outright. Skip there, naming why; **never skip on Linux**, where the
        real file is created and the real check must still catch it.
        """
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / 'quo"te'
        try:
            nested.mkdir(parents=True)
        except OSError as exc:
            if sys.platform.startswith("linux"):
                raise
            pytest.skip(f"this filesystem cannot create a '\"' in a name: {exc}")
        (nested / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", check.detail
        assert 'packages/quo"te/CLAUDE.md' in check.detail, check.detail

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="NTFS filenames reject control characters such as tab and newline",
    )
    def test_a_directory_name_with_a_tab_and_a_newline_still_matches(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "weird\tname\nhere"
        nested.mkdir(parents=True)
        (nested / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        tracked = doctor.tracked_ai_layer_paths(root)
        expected = "packages/weird\tname\nhere/CLAUDE.md"
        assert tracked == [expected], tracked

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )
        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", check.detail


class TestARegisteredTildePathIsInspectedNotSkipped:
    """DG-445: ``_check_project_layering`` built the checkout path with
    ``Path(config.path)`` directly, so a project registered with
    ``"~/checkout"`` read as a literal, nonexistent ``~`` directory and was
    skipped — "there is no checkout to inspect" — even with a real,
    trackable git repository sitting right there under the real home."""

    def test_a_tracked_path_under_a_registered_tilde_still_fails(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("HOMEDRIVE", raising=False)
        monkeypatch.delenv("HOMEPATH", raising=False)
        root = tmp_path / "checkout"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        registry_path = tmp_path / "projects.json"
        registry_path.write_text(
            json.dumps({"version": 2, "projects": {"tilde": {"path": "~/checkout"}}}),
            encoding="utf-8",
        )

        report = doctor.run_doctor(
            registry=ProjectRegistry(str(registry_path)), offline=True
        )

        check = find(report, "layering.tracked.tilde")
        assert check.status == "fail", (
            "a registered '~/checkout' that actually tracks AGENTS.md must "
            f"be inspected, not skipped as having no checkout. Got "
            f"{check.status}: {check.detail}"
        )
        assert "AGENTS.md" in check.detail, check.detail

    def test_mutation_reintroducing_the_unexpanded_path_is_a_false_skip(
        self, tmp_path, monkeypatch
    ) -> None:
        """Mutation: patch ``ProjectConfig.resolved_path`` back to the
        pre-fix shape with no ``expanduser()``, and confirm the same
        registered project — tracked AGENTS.md and all — regresses to a
        skip. The assertion below is the mutation's own wrong outcome."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("HOMEDRIVE", raising=False)
        monkeypatch.delenv("HOMEPATH", raising=False)
        root = tmp_path / "checkout"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        _commit_all(root, "initial")

        registry_path = tmp_path / "projects.json"
        registry_path.write_text(
            json.dumps({"version": 2, "projects": {"tilde": {"path": "~/checkout"}}}),
            encoding="utf-8",
        )

        from core.registry import ProjectConfig

        def _unexpanded(self, reason: str):
            from pathlib import Path

            return Path(self.require_path(reason))

        monkeypatch.setattr(ProjectConfig, "resolved_path", _unexpanded)

        report = doctor.run_doctor(
            registry=ProjectRegistry(str(registry_path)), offline=True
        )

        check = find(report, "layering.tracked.tilde")
        assert check.status == "skip", (
            "this is the mutation's own (wrong) outcome — the real fix must "
            f"disagree with it. Got {check.status}: {check.detail}"
        )


class TestNoCheckoutIsSkipNeverPass:
    def test_a_registered_path_that_does_not_exist_is_a_skip(self, tmp_path):
        missing = tmp_path / "does-not-exist"

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", missing), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "skip", check.detail

    def test_a_non_git_folder_is_a_skip(self, tmp_path):
        root = tmp_path / "proj"
        root.mkdir()
        (root / "main.py").write_text("print('hi')", encoding="utf-8")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "skip", check.detail

    def test_mutation_a_missing_checkout_reported_ok_is_caught(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", missing), offline=True
        )
        check = find(report, "layering.tracked.scratch")
        assert check.status != "ok", (
            "a project with no checkout must never read as a clean pass — "
            "that is the whole point of 'skip, not a pass'."
        )


class TestGitFailingInsideARealCheckoutIsASkipNeverOkOrFail:
    """DG-438 review: a project git could not actually be asked about must
    never read the same as one that was asked and found clean."""

    def test_a_corrupted_git_directory_is_a_skip(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        _commit_all(root, "initial")
        # Corrupt the repository rather than mock subprocess: `.git` still
        # exists (so the earlier "not a git repo" skip does not fire first),
        # but `git ls-files` itself now exits non-zero.
        (root / ".git" / "HEAD").unlink()
        broken = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True
        )
        assert broken.returncode != 0, (
            "the corruption must actually break git, or this test proves "
            f"nothing. git said: {broken.stderr!r}"
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "skip", (
            "git failing inside a real checkout must read as 'could not "
            f"ask', never a pass or a failure. Got {check.status}: "
            f"{check.detail}"
        )

    def test_mutation_treating_a_git_failure_as_a_clean_project_is_caught(
        self, tmp_path, monkeypatch
    ):
        """Seen failing first: if `tracked_ai_layer_paths` reported `[]`
        ("ran, found nothing") instead of `None` ("could not run") when git
        itself fails, this same corrupted checkout would read as a clean
        "ok" pass — indistinguishable from one that was actually inspected.
        Forcing that wrong return value here is the mutation, and the
        assertion below is its own (wrong) expectation, which the real
        implementation must disagree with.
        """
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        _commit_all(root, "initial")
        (root / ".git" / "HEAD").unlink()
        monkeypatch.setattr(doctor, "tracked_ai_layer_paths", lambda git_root: [])

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "ok", (
            "this is the mutation's own wrong outcome — the real "
            f"implementation must skip, never pass, when git fails. Got "
            f"{check.status}: {check.detail}"
        )


class TestNoGitInstalledIsASkip:
    def test_no_git_on_path_is_one_skip_for_the_whole_check(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")
        _commit_all(root, "initial")
        monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "layering.tracked")
        assert check.status == "skip", check.detail


class TestThisRepositoryIsExempt:
    def test_the_guilds_own_checkout_is_not_flagged(self, tmp_path):
        repo_root = doctor.source_tree_root()
        assert repo_root is not None, (
            "this test only means something run from a source checkout, "
            "which `uv run pytest` always is"
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "guild", repo_root), offline=True
        )

        check = find(report, "layering.tracked.guild")
        assert check.status == "skip", check.detail

    def test_mutation_without_the_exemption_the_guilds_own_tree_would_fail(self):
        """This repository tracks AGENTS.md, CLAUDE.md and .claude/ itself —
        deliberately, per CLAUDE.md's own 'AI layer stays in git'. The
        exemption is the only thing standing between that fact and a
        permanent false failure, so prove the fact is real."""
        repo_root = doctor.source_tree_root()
        assert repo_root is not None

        tracked = doctor.tracked_ai_layer_paths(repo_root)

        assert tracked, (
            "if this repository tracked nothing AI-layer-shaped, the "
            "exemption above would be untested by every other case here"
        )


class TestLeakedGitEnvironmentDoesNotMisreportTrackedPaths:
    """DG-451. ``tracked_ai_layer_paths`` ran plain ``git ls-files -z`` with
    the caller's inherited environment. ``core.exclude.run_git`` /
    ``git_subprocess_env`` (DG-440/441) already strip every ``GIT_*``
    variable for exactly this reason: a process with ``GIT_DIR`` /
    ``GIT_WORK_TREE`` / ``GIT_INDEX_FILE`` set — a git hook, for one —
    redirects a naive ``git`` subprocess call onto a completely different
    repository's index, regardless of the ``cwd`` it is given. This proves
    ``tracked_ai_layer_paths`` now goes through the stripped caller too, by
    pointing all three at a real, unrelated repository and checking the
    *project's own* tracked AI-layer paths are still what comes back.
    """

    def test_leaked_git_dir_index_and_worktree_still_report_this_projects_paths(
        self, tmp_path, monkeypatch
    ):
        unrelated = tmp_path / "unrelated"
        _init_repo(unrelated)
        (unrelated / "main.py").write_text("print('unrelated')", encoding="utf-8")
        _commit_all(unrelated, "unrelated initial")

        project = tmp_path / "proj"
        _init_repo(project)
        (project / "AGENTS.md").write_text("instructions", encoding="utf-8")
        (project / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(project, "initial")

        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(unrelated))
        monkeypatch.setenv("GIT_INDEX_FILE", str(unrelated / ".git" / "index"))

        tracked = doctor.tracked_ai_layer_paths(project)

        assert tracked == ["AGENTS.md"], (
            "a leaked GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE must not redirect "
            "this call onto the unrelated repository found through them — it "
            f"must still report {project}'s own tracked AI-layer paths. Got "
            f"{tracked!r}"
        )

    def test_leaked_git_dir_index_and_worktree_do_not_break_the_full_check(
        self, tmp_path, monkeypatch
    ):
        unrelated = tmp_path / "unrelated"
        _init_repo(unrelated)
        (unrelated / "main.py").write_text("print('unrelated')", encoding="utf-8")
        _commit_all(unrelated, "unrelated initial")

        project = tmp_path / "proj"
        _init_repo(project)
        (project / "AGENTS.md").write_text("instructions", encoding="utf-8")
        (project / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(project, "initial")

        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(unrelated))
        monkeypatch.setenv("GIT_INDEX_FILE", str(unrelated / ".git" / "index"))

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", project), offline=True
        )

        check = find(report, "layering.tracked.scratch")
        assert check.status == "fail", (
            "the leaked environment must not turn a real, tracked AGENTS.md "
            f"into a false pass or skip. Got {check.status}: {check.detail}"
        )
        assert "AGENTS.md" in check.detail, check.detail
