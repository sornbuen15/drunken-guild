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

import pytest

from core import doctor
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
        """Seen failing first: a stubbed `tracked_ai_layer_paths` that always
        reports nothing would make the two tests above pass for the wrong
        reason. Forcing that stub here is the mutation, and it must fail."""
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

    def test_mutation_a_check_reading_the_worktree_instead_of_the_index_is_caught(
        self, tmp_path
    ):
        """Seen failing first: a check that scanned the filesystem rather than
        `git ls-files` would flag the untracked file above. That scan is the
        mutation."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")
        (root / "AGENTS.md").write_text("instructions", encoding="utf-8")

        from core import ai_layer

        worktree_scan = sorted(
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file() and ai_layer.is_ai_layer_path(p.relative_to(root))
        )
        assert worktree_scan == ["AGENTS.md"], (
            "a filesystem scan (the mutation) finds the untracked file, "
            f"unlike git ls-files. Got {worktree_scan}"
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
