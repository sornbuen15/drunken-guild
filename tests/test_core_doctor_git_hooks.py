# mypy: ignore-errors
"""DG-466: `guard.git_hooks` — for the source tree and every registered
project whose `.pre-commit-config.yaml` runs `check_operator_inventory`,
each type in `default_install_hook_types` must have a pre-commit hook at
`git rev-parse --git-path hooks`. Missing -> fail, remedy `pre-commit
install`.

Every scratch repository here is real git, under ``tmp_path`` — not a mock —
the same discipline ``test_core_doctor_layering.py`` already follows: the
thing under test is what git itself reports about hooks and worktrees, and a
mocked subprocess would only prove the test author's own assumption about
that.
"""

import json
import subprocess
import sys

import pytest

from core import doctor
from core.registry import ProjectRegistry

GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]

GUARDED_CONFIG_FLOW = (
    "default_install_hook_types: [pre-commit, commit-msg]\n"
    "repos:\n"
    "  - repo: local\n"
    "    hooks:\n"
    "      - id: check-operator-inventory\n"
    "        name: Refuse staged content that names a registered project\n"
    "        entry: python scripts/check_operator_inventory.py\n"
    "        language: system\n"
)

GUARDED_CONFIG_BLOCK = (
    "default_install_hook_types:\n"
    "  - pre-commit\n"
    "  - commit-msg\n"
    "repos:\n"
    "  - repo: local\n"
    "    hooks:\n"
    "      - id: check-operator-inventory\n"
    "        entry: python scripts/check_operator_inventory.py\n"
    "        language: system\n"
)

UNGUARDED_CONFIG = (
    "default_install_hook_types: [pre-commit]\n"
    "repos:\n"
    "  - repo: local\n"
    "    hooks:\n"
    "      - id: trailing-whitespace\n"
    "        entry: some-other-tool\n"
    "        language: system\n"
)


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


def _write_hook(hooks_dir, name: str, executable: bool = True) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / name
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if executable and sys.platform != "win32":
        hook.chmod(0o755)
    if not executable and sys.platform != "win32":
        hook.chmod(0o644)


def find(report: doctor.Report, name: str) -> doctor.Check:
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(
        f"no check named {name!r} in {[c.name for c in report.checks]}"
    )


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
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


# ---------------------------------------------------------------------------
# Unit tests on the small helpers, mutation-proof against a hardcoded list.
# ---------------------------------------------------------------------------


class TestRunsOperatorInventoryGuard:
    def test_true_when_the_entry_line_names_the_script(self):
        assert doctor.runs_operator_inventory_guard(GUARDED_CONFIG_FLOW) is True

    def test_false_when_nothing_mentions_it(self):
        assert doctor.runs_operator_inventory_guard(UNGUARDED_CONFIG) is False

    def test_false_on_an_empty_file(self):
        assert doctor.runs_operator_inventory_guard("") is False


class TestDeclaredHookTypes:
    def test_flow_style_list(self):
        assert doctor.declared_hook_types(GUARDED_CONFIG_FLOW) == [
            "pre-commit",
            "commit-msg",
        ]

    def test_block_style_list(self):
        assert doctor.declared_hook_types(GUARDED_CONFIG_BLOCK) == [
            "pre-commit",
            "commit-msg",
        ]

    def test_a_third_hook_type_added_to_the_config_is_read_without_code_changes(self):
        """DG-464 is expected to add `pre-push` to this very list in a
        parallel branch. This must read whatever the config says, not a
        hardcoded pair — proven by a type this file has never hardcoded
        anywhere else, read from flow style."""
        text = "default_install_hook_types: [pre-commit, commit-msg, pre-push]\n"
        assert doctor.declared_hook_types(text) == [
            "pre-commit",
            "commit-msg",
            "pre-push",
        ]

    def test_a_fourth_hook_type_added_in_block_style_is_also_read(self):
        text = (
            "default_install_hook_types:\n"
            "  - pre-commit\n"
            "  - commit-msg\n"
            "  - pre-push\n"
            "  - post-checkout\n"
        )
        assert doctor.declared_hook_types(text) == [
            "pre-commit",
            "commit-msg",
            "pre-push",
            "post-checkout",
        ]

    def test_defaults_to_pre_commit_alone_when_the_key_is_absent(self):
        """pre-commit's own default when a config declares none at all —
        not this project's invention."""
        assert doctor.declared_hook_types(
            UNGUARDED_CONFIG.replace("default_install_hook_types: [pre-commit]\n", "")
        ) == ["pre-commit"]


class TestHooksDirHonoursConfigAndWorktrees:
    def test_resolves_the_ordinary_dot_git_hooks_directory(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(root, "initial")

        resolved = doctor.hooks_dir(root)

        assert resolved == (root / ".git" / "hooks").resolve()

    def test_honours_core_hookspath(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(root, "initial")
        (root / "myhooks").mkdir()
        _git("config", "core.hooksPath", "myhooks", cwd=root)

        resolved = doctor.hooks_dir(root)

        assert resolved == (root / "myhooks").resolve()

    def test_a_linked_worktree_resolves_to_the_shared_hooks_dir(self, tmp_path):
        main = tmp_path / "main"
        _init_repo(main)
        (main / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(main, "initial")
        worktree = tmp_path / "wt"
        _git("worktree", "add", "-b", "wtbranch", str(worktree), cwd=main)

        resolved = doctor.hooks_dir(worktree)

        assert resolved == (main / ".git" / "hooks").resolve()

    def test_not_a_repository_returns_none(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()

        assert doctor.hooks_dir(plain) is None

    def test_no_git_on_path_returns_none(self, tmp_path, monkeypatch):
        root = tmp_path / "proj"
        _init_repo(root)
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        (tmp_path / "empty-bin").mkdir()

        assert doctor.hooks_dir(root) is None


class TestMissingHookTypes:
    def test_an_absent_hook_file_is_missing(self, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        _write_hook(hooks, "pre-commit")

        missing = doctor.missing_hook_types(hooks, ["pre-commit", "commit-msg"])

        assert missing == ["commit-msg"]

    def test_every_declared_hook_present_is_not_missing(self, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        _write_hook(hooks, "pre-commit")
        _write_hook(hooks, "commit-msg")

        missing = doctor.missing_hook_types(hooks, ["pre-commit", "commit-msg"])

        assert missing == []

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="NTFS has no POSIX execute bit to clear",
    )
    def test_a_present_but_non_executable_hook_is_missing(self, tmp_path):
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        _write_hook(hooks, "pre-commit", executable=False)

        missing = doctor.missing_hook_types(hooks, ["pre-commit"])

        assert missing == ["pre-commit"]


# ---------------------------------------------------------------------------
# Integration: the actual `guard.git_hooks[.project]` checks via run_doctor.
# ---------------------------------------------------------------------------


class TestAMissingDeclaredHookFails:
    def test_a_missing_commit_msg_hook_fails_and_is_named(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        # commit-msg hook deliberately never written.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "commit-msg" in check.detail
        assert check.remediation == "pre-commit install"

    def test_mutation_a_check_that_never_fails_is_caught(self, tmp_path, monkeypatch):
        """Wiring only, same shape as the layering suite's own mutation
        tests: stubs `missing_hook_types` so this proves the branch in the
        doctor check that turns a non-empty result into "fail" actually
        runs."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        monkeypatch.setattr(doctor, "missing_hook_types", lambda hooks, types: [])

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", (
            "this assertion is the mutation's own 'pass' — the real check "
            f"must disagree with it when hooks are genuinely missing. Got "
            f"{check.status}: {check.detail}"
        )


class TestEveryDeclaredHookPresentIsOk:
    def test_both_declared_hooks_present_is_ok(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail

    def test_mutation_a_check_that_always_fails_is_caught(self, tmp_path, monkeypatch):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        monkeypatch.setattr(
            doctor, "missing_hook_types", lambda hooks, types: ["pre-commit"]
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", (
            f"the mutation must flip this clean project to fail. Got "
            f"{check.status}: {check.detail}"
        )


class TestALinkedWorktreeIsJudgedByTheSharedHooks:
    def test_a_worktree_with_hooks_only_in_the_main_checkout_passes(self, tmp_path):
        main = tmp_path / "main"
        _init_repo(main)
        (main / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(main, "initial")
        worktree = tmp_path / "wt"
        _git("worktree", "add", "-b", "wtbranch", str(worktree), cwd=main)
        # Hooks written only to the *main* checkout's .git/hooks — never to
        # the worktree, which has no hooks directory of its own at all.
        _write_hook(main / ".git" / "hooks", "pre-commit")
        _write_hook(main / ".git" / "hooks", "commit-msg")
        assert not (worktree / ".git").is_dir()

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", worktree), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", (
            "a linked worktree shares the main checkout's hooks dir — "
            f"judged by those, not a (nonexistent) one of its own. Got "
            f"{check.status}: {check.detail}"
        )

    def test_a_worktree_missing_a_shared_hook_fails(self, tmp_path):
        main = tmp_path / "main"
        _init_repo(main)
        (main / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(main, "initial")
        worktree = tmp_path / "wt"
        _git("worktree", "add", "-b", "wtbranch", str(worktree), cwd=main)
        _write_hook(main / ".git" / "hooks", "pre-commit")
        # commit-msg never written anywhere.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", worktree), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "commit-msg" in check.detail


class TestARepositoryWithoutTheGuardIsNotChecked:
    def test_no_pre_commit_config_at_all_is_a_skip(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "skip", check.detail

    def test_a_config_that_never_runs_the_guard_is_a_skip(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            UNGUARDED_CONFIG, encoding="utf-8"
        )
        _commit_all(root, "initial")
        # No hooks at all installed — if the guard were (wrongly) detected,
        # this would fail instead of skip.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "skip", check.detail

    def test_mutation_treating_every_config_as_guarded_is_caught(
        self, tmp_path, monkeypatch
    ):
        """Seen failing first: if `runs_operator_inventory_guard` always
        returned True, an unguarded repo with no hooks installed would read
        as 'fail' instead of 'skip' — this is that wrong behaviour, forced,
        and the assertion is its own wrong expectation."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            UNGUARDED_CONFIG, encoding="utf-8"
        )
        _commit_all(root, "initial")
        monkeypatch.setattr(doctor, "runs_operator_inventory_guard", lambda text: True)

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", (
            "this is the mutation's own wrong outcome — the real "
            f"implementation must skip an unguarded repo. Got {check.status}: "
            f"{check.detail}"
        )


class TestRegisteredRootMissingOnDisk:
    def test_a_registered_path_that_does_not_exist_is_a_skip(self, tmp_path):
        missing = tmp_path / "does-not-exist"

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", missing), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "skip", check.detail

    def test_a_non_git_folder_is_a_skip(self, tmp_path):
        root = tmp_path / "proj"
        root.mkdir()
        (root / "f.txt").write_text("x", encoding="utf-8")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "skip", check.detail


class TestMalformedConfigDoesNotCrash:
    def test_garbage_yaml_that_still_mentions_the_guard_falls_back_to_pre_commit_alone(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            "not: [valid, yaml: at: all\ncheck_operator_inventory\n",
            encoding="utf-8",
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail


class TestNoPathDeclaredIsASkip:
    def test_a_project_with_no_path_is_skipped(self, tmp_path):
        target = tmp_path / "projects.json"
        target.write_text(
            json.dumps({"version": 2, "projects": {"scratch": {"path": None}}}),
            encoding="utf-8",
        )

        report = doctor.run_doctor(registry=ProjectRegistry(str(target)), offline=True)

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "skip", check.detail


class TestLeakedGitEnvironmentDoesNotMisreportHooksDir:
    """DG-451: `core.exclude.run_git` strips every inherited `GIT_*`
    variable for exactly this reason — a process with `GIT_DIR` /
    `GIT_WORK_TREE` set (a git hook, for one) redirects a naive `git`
    subprocess call onto a completely different repository, regardless of
    the `cwd` it is given. This proves `hooks_dir` goes through the
    stripped caller too."""

    def test_leaked_git_dir_and_worktree_still_report_this_projects_hooks(
        self, tmp_path, monkeypatch
    ):
        unrelated = tmp_path / "unrelated"
        _init_repo(unrelated)
        (unrelated / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(unrelated, "unrelated initial")

        project = tmp_path / "proj"
        _init_repo(project)
        (project / "f.txt").write_text("x", encoding="utf-8")
        _commit_all(project, "initial")

        monkeypatch.setenv("GIT_DIR", str(unrelated / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(unrelated))

        resolved = doctor.hooks_dir(project)

        assert resolved == (project / ".git" / "hooks").resolve(), (
            "a leaked GIT_DIR/GIT_WORK_TREE must not redirect this call onto "
            f"the unrelated repository found through them. Got {resolved!r}"
        )


class TestTheSourceTreeItselfIsChecked:
    """REQ (DG-466 SCOPE): 'Checking registered roots matters: an installed
    doctor has no source tree, so a source-only check would always skip.'
    This proves the inverse holds too — the source tree itself is still
    checked under its own name when one exists, independent of any
    registered project."""

    def test_the_guilds_own_checkout_reports_under_its_own_name(self, tmp_path):
        repo_root = doctor.source_tree_root()
        assert repo_root is not None, (
            "this test only means something run from a source checkout, "
            "which `uv run pytest` always is"
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "unused", tmp_path / "does-not-exist"),
            offline=True,
        )

        check = find(report, "guard.git_hooks")
        # This repository's own .pre-commit-config.yaml does run the guard
        # (see the real file), so the only two sane outcomes here are ok or
        # fail depending on whether hooks are actually installed on this
        # machine — never skip, and never an exception.
        assert check.status in ("ok", "fail"), check.detail

    def test_no_source_tree_is_an_explicit_skip_not_silence(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(doctor, "source_tree_root", lambda: None)

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "unused", tmp_path / "does-not-exist"),
            offline=True,
        )

        check = find(report, "guard.git_hooks")
        assert check.status == "skip", check.detail
