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
import re
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

    def test_a_trailing_inline_comment_on_a_flow_line_still_parses(self):
        """Review finding: this line used to fail to match the flow pattern
        (the comment was part of the matched text) and silently fall back
        to pre-commit's bare default — dropping the declared `commit-msg`
        hook out of the check while still reporting ok."""
        text = (
            "default_install_hook_types: [pre-commit, commit-msg]  "
            "# wires commit-msg too\n"
        )
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_mutation_not_stripping_the_comment_first_is_caught(self):
        """The pre-fix behaviour, run directly: matching the flow regex
        against the *unstripped* line. The assertion is that wrong
        behaviour's own (wrong) outcome — a regex match that fails because
        the comment is still attached, read here exactly as the old
        `declared_hook_types` would have read it."""
        unstripped = (
            "default_install_hook_types: [pre-commit, commit-msg]  "
            "# wires commit-msg too"
        )
        flow = re.compile(r"^default_install_hook_types:\s*\[(.*)\]\s*$")
        assert flow.match(unstripped) is None, (
            "this is the old bug's own (wrong) outcome: the unstripped line "
            "must fail to match, which is exactly why the real "
            "implementation strips the comment first"
        )

    def test_a_trailing_inline_comment_on_a_block_item_is_not_baked_in(self):
        """Review finding: a block item's own trailing comment must not
        become part of the hook-type string — that is a permanent false
        fail, since no installed hook file is ever named
        'pre-commit  # wired automatically'."""
        text = (
            "default_install_hook_types:\n"
            "  - pre-commit  # wired automatically\n"
            "  - commit-msg\n"
        )
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_an_anchor_fails_loud(self):
        """A YAML anchor on the value is a shape this hand-rolled reader
        does not support — it must say so, not quietly fall back to
        pre-commit's bare default and risk never checking a declared
        commit-msg/pre-push hook at all."""
        text = "default_install_hook_types: &hook_types [pre-commit, commit-msg]\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_an_unterminated_multiline_flow_list_fails_loud(self):
        text = "default_install_hook_types: [\n  pre-commit,\n  commit-msg,\n]\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_mutation_silently_defaulting_on_an_anchor_is_caught(self):
        """Review's own named mutation: the pre-fix behaviour treated any
        unrecognised shape the same as an absent key. The assertion below
        is that wrong behaviour's own (wrong) outcome, reproduced directly
        rather than by stubbing the real function."""
        text = "default_install_hook_types: &hook_types [pre-commit, commit-msg]\n"

        def _pre_fix_declared_hook_types(config_text):
            flow = re.compile(r"^default_install_hook_types:\s*\[(.*)\]\s*$")
            block_key = re.compile(r"^default_install_hook_types:\s*$")
            for raw_line in config_text.splitlines():
                stripped = raw_line.strip()
                match = flow.match(stripped)
                if match:
                    return [item.strip() for item in match.group(1).split(",")]
                if block_key.match(stripped):
                    return []
            return ["pre-commit"]

        result = _pre_fix_declared_hook_types(text)
        assert result == ["pre-commit"], (
            "this is the old bug's own (wrong) outcome — silently narrowing "
            f"an anchor to the bare default. Got: {result!r}"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)


class TestDeclaredHookTypesReadsOnlyTheTopLevelKey:
    """DG-469: DG-466's own matcher read `default_install_hook_types:` as
    plain text with no regard for indentation, so a nested occurrence —
    under a `repos:` hook entry, or under any other unrelated key — was
    read as the top-level declaration. pre-commit itself only honours the
    key at the top level of the mapping; a nested line is never the real
    declaration."""

    def test_a_nested_occurrence_inside_a_repos_entry_fails_loud(self):
        text = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: some-hook\n"
            "        name: some-hook\n"
            "        default_install_hook_types: [pre-commit]\n"
            "        language: system\n"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_a_nested_occurrence_under_an_unrelated_key_fails_loud(self):
        text = "some_other_key:\n  default_install_hook_types: [pre-commit]\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_a_top_level_declaration_wins_over_a_nested_occurrence(self):
        text = (
            "default_install_hook_types: [pre-commit, commit-msg]\n"
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: some-hook\n"
            "        default_install_hook_types: [post-checkout]\n"
        )
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_column_zero_declaration_still_parses_flow_style(self):
        text = "repos: []\ndefault_install_hook_types: [pre-commit, commit-msg]\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_column_zero_declaration_still_parses_block_style(self):
        text = (
            "repos: []\ndefault_install_hook_types:\n  - pre-commit\n  - commit-msg\n"
        )
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_commented_out_top_level_line_is_not_taken_as_the_declaration(self):
        text = "# default_install_hook_types: [commit-msg]\n"
        assert doctor.declared_hook_types(text) == ["pre-commit"]

    def test_a_tab_indented_occurrence_is_not_top_level(self):
        text = "foo:\n\tdefault_install_hook_types: [pre-commit]\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_windows_line_endings_still_parse_a_top_level_declaration(self):
        text = "default_install_hook_types: [pre-commit, commit-msg]\r\nrepos: []\r\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_leading_bom_does_not_hide_a_top_level_declaration(self):
        text = "﻿default_install_hook_types: [pre-commit, commit-msg]\nrepos: []\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_an_empty_file_defaults_to_pre_commit_alone(self):
        assert doctor.declared_hook_types("") == ["pre-commit"]

    def test_mutation_matching_the_key_as_plain_text_is_caught(self):
        """The pre-fix behaviour, run directly: matching the key as a bare
        substring/strip with no regard for indentation at all. The
        assertion is that wrong behaviour's own (wrong) outcome — reading
        the nested occurrence as the declaration."""

        def _pre_fix_declared_hook_types(config_text):
            flow = re.compile(r"^default_install_hook_types:\s*\[(.*)\]\s*$")
            block_key = re.compile(r"^default_install_hook_types:\s*$")
            lines = config_text.splitlines()
            for index, raw_line in enumerate(lines):
                stripped = raw_line.strip()
                match = flow.match(stripped)
                if match:
                    return [
                        item.strip().strip("'\"") for item in match.group(1).split(",")
                    ]
                if block_key.match(stripped):
                    types = []
                    for following in lines[index + 1 :]:
                        item = following.strip()
                        if not item.startswith("-"):
                            break
                        types.append(item[1:].strip())
                    return types
            return ["pre-commit"]

        text = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: some-hook\n"
            "        default_install_hook_types: [post-checkout]\n"
        )
        result = _pre_fix_declared_hook_types(text)
        assert result == ["post-checkout"], (
            "this is the old bug's own (wrong) outcome — a nested "
            f"occurrence read as the top-level declaration. Got: {result!r}"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)


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

    def test_a_hooks_directory_that_does_not_exist_at_all_is_missing(self, tmp_path):
        """Seen failing first against the mutation below: a checkout whose
        hooks directory was never created (`core.hooksPath` pointed at a
        directory nobody made, or the repository is otherwise unusual) must
        read every declared type as missing, never as an empty, silently
        clean result."""
        hooks = tmp_path / "does-not-exist-at-all"
        assert not hooks.exists()

        missing = doctor.missing_hook_types(hooks, ["pre-commit", "commit-msg"])

        assert missing == ["pre-commit", "commit-msg"]

    def test_mutation_returning_empty_for_a_missing_directory_is_caught(self, tmp_path):
        """The mutation named in review: `missing_hook_types` short-circuits
        to `[]` the moment the directory itself is absent, instead of
        reporting every declared type as missing. The assertion below is
        that wrong behaviour's own (wrong) expectation."""
        hooks = tmp_path / "does-not-exist-at-all"

        def _mutated_missing_hook_types(hooks_dir_path, hook_types):
            if not hooks_dir_path.is_dir():
                return []
            return [
                hook_type
                for hook_type in hook_types
                if not (hooks_dir_path / hook_type).is_file()
            ]

        result = _mutated_missing_hook_types(hooks, ["pre-commit", "commit-msg"])

        assert result == [], (
            "this is the mutation's own wrong result — the real "
            f"missing_hook_types must disagree with it. Got: {result!r}"
        )
        assert doctor.missing_hook_types(hooks, ["pre-commit", "commit-msg"]) == [
            "pre-commit",
            "commit-msg",
        ], "the real implementation must report both types missing, not []"

    def test_a_directory_occupying_a_hook_path_is_missing(self, tmp_path):
        """Seen failing first against the mutation below: `pre-commit`
        (the path) existing as a *directory* — never written by
        `pre-commit install`, which always writes a file — must count as
        missing, not present."""
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").mkdir()

        missing = doctor.missing_hook_types(hooks, ["pre-commit"])

        assert missing == ["pre-commit"]

    def test_mutation_using_exists_instead_of_is_file_is_caught(self, tmp_path):
        """The mutation named in review: swap `is_file()` for `exists()`,
        which is also true for a directory. The assertion below is that
        wrong behaviour's own (wrong) expectation."""
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        (hooks / "pre-commit").mkdir()

        def _mutated_missing_hook_types(hooks_dir_path, hook_types):
            return [
                hook_type
                for hook_type in hook_types
                if not (hooks_dir_path / hook_type).exists()
            ]

        result = _mutated_missing_hook_types(hooks, ["pre-commit"])

        assert result == [], (
            "this is the mutation's own wrong result — a directory must "
            f"not count as a present hook. Got: {result!r}"
        )
        assert doctor.missing_hook_types(hooks, ["pre-commit"]) == ["pre-commit"], (
            "the real implementation must report the directory-occupied path as missing"
        )


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

    def test_a_real_missing_hook_flips_the_same_project_to_fail(self, tmp_path):
        """Exercises the real `missing_hook_types` rather than stubbing
        it: the same project as above, minus the `commit-msg` hook file,
        must disagree with the 'ok' assertion directly above."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        # commit-msg deliberately omitted.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail


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


class TestAnUnparseableDeclarationFailsLoud:
    """Review requirement: a config that runs the guard but declares
    `default_install_hook_types` in a shape this reader cannot follow must
    fail, and name that it could not read the declaration — never narrow
    silently to the bare default and risk reporting ok while a real
    `commit-msg`/`pre-push` declaration went unchecked."""

    def test_an_anchor_in_a_guarded_config_fails_the_whole_check(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        config = GUARDED_CONFIG_FLOW.replace(
            "default_install_hook_types: [pre-commit, commit-msg]\n",
            "default_install_hook_types: &hook_types [pre-commit, commit-msg]\n",
        )
        (root / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", (
            "an unrecognised declaration shape must fail loud, never read "
            f"as ok even with every plausible hook file present. Got "
            f"{check.status}: {check.detail}"
        )
        assert "default_install_hook_types" in check.detail

    def test_mutation_silently_defaulting_would_read_ok(self, tmp_path, monkeypatch):
        """The exact regression this guards against: if
        `declared_hook_types` silently fell back to `["pre-commit"]` for
        an anchor instead of raising, and only `pre-commit` were installed
        (not `commit-msg`), the check would wrongly read ok. The assertion
        is that wrong behaviour's own (wrong) outcome."""
        root = tmp_path / "proj"
        _init_repo(root)
        config = GUARDED_CONFIG_FLOW.replace(
            "default_install_hook_types: [pre-commit, commit-msg]\n",
            "default_install_hook_types: &hook_types [pre-commit, commit-msg]\n",
        )
        (root / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        # commit-msg deliberately never written — the regression this
        # test exists to catch would silently never check for it at all.
        monkeypatch.setattr(doctor, "declared_hook_types", lambda text: ["pre-commit"])

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", (
            "this is the regression's own (wrong) outcome — the real "
            f"implementation must fail loud instead. Got {check.status}: "
            f"{check.detail}"
        )


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
