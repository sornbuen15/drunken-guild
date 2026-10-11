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
import random
import re
import subprocess
import sys

import pytest
import yaml  # dev-only oracle for DG-478; never imported by src/core/doctor.py

from core import doctor, git_hooks
from core.registry import ProjectRegistry

GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]

#: Sentinels for the DG-483 fuzz harness below -- distinguishing "yaml.safe_load
#: itself rejected this line" and "doctor refused this line" from any real
#: parsed value (including ``None`` or an empty list), which an `is` check
#: would otherwise confuse with a genuine result.
_YAML_REJECTED = object()
_READER_REFUSED = object()

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


def _write_native_pre_push_hook(hooks_dir_path) -> None:
    """A stand-in for `drunken-init --install-git-hooks` (DG-479): writes
    the REAL, byte-identical shipped template -- not a fabricated stand-in
    -- so `doctor._native_pre_push_status`'s content check (round 2 fix:
    stale/modified content fails even with the marker present) agrees this
    is a genuine, untouched install. Earlier revisions of this helper wrote
    a fake one-liner carrying only the marker; that stopped being "ok" the
    moment the content check existed, so every fixture needs the real
    bytes now, not just the marker.
    """
    hooks_dir_path.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir_path / git_hooks.HOOK_FILENAME
    hook.write_text(git_hooks._read_template(), encoding="utf-8")  # noqa: SLF001
    if sys.platform != "win32":
        hook.chmod(0o755)


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

    def test_a_nested_occurrence_before_the_top_level_declaration_still_loses(self):
        """Mutation-catching: a scanner that stops at the *first* top-level
        match, or that raises as soon as it sees a nested occurrence
        instead of flagging and continuing, both happen to agree with the
        real implementation whenever the nested line comes *after* the
        top-level one (every other test above puts it there). Reversing
        the order is what actually exercises "keep scanning, top level
        wins whenever it is found"."""
        text = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: some-hook\n"
            "        default_install_hook_types: [post-checkout]\n"
            "default_install_hook_types: [pre-commit, commit-msg]\n"
        )
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_mutation_raising_immediately_on_a_nested_occurrence_is_caught(self):
        """The mutation named in review: raise on the *first* nested
        occurrence seen instead of flagging it and continuing to scan for
        a later top-level one. The assertion is that wrong behaviour's own
        (wrong) outcome, reproduced directly rather than by stubbing the
        real function — it only disagrees with the real implementation
        when the nested line comes before the top-level one."""
        text = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: some-hook\n"
            "        default_install_hook_types: [post-checkout]\n"
            "default_install_hook_types: [pre-commit, commit-msg]\n"
        )

        def _mutated_find_top_level(lines):
            for index, raw_line in enumerate(lines):
                normalized = doctor._normalized_hook_types_declaration(raw_line)
                if normalized is None:
                    continue
                comment_stripped = doctor._strip_inline_comment(raw_line)
                if comment_stripped.lstrip(" \t") != comment_stripped:
                    raise doctor.UnparseableHookTypesError("nested, mutated")
                return index, normalized
            return None

        with pytest.raises(doctor.UnparseableHookTypesError):
            _mutated_find_top_level(text.splitlines())

        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"], (
            "the real implementation must keep scanning past the nested "
            "occurrence and read the later top-level declaration"
        )

    def test_a_duplicate_top_level_key_reads_the_last_one(self):
        """DG-469 review: PyYAML (the `SafeLoader` pre-commit itself loads
        the config with) is last-key-wins for a duplicate mapping key, not
        an error. Reading the first one, as the original scanner did,
        disagrees with what pre-commit itself would actually install."""
        text = (
            "default_install_hook_types: [pre-commit]\n"
            "repos: []\n"
            "default_install_hook_types: [commit-msg]\n"
        )
        assert doctor.declared_hook_types(text) == ["commit-msg"]

    def test_a_quoted_key_is_still_the_top_level_declaration(self):
        """DG-469 review: `"default_install_hook_types": [...]` is valid
        YAML, read by pre-commit identically to the unquoted key."""
        text = '"default_install_hook_types": [pre-commit, commit-msg]\nrepos: []\n'
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_single_quoted_key_is_still_the_top_level_declaration(self):
        text = "'default_install_hook_types': [pre-commit, commit-msg]\nrepos: []\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_space_before_the_colon_is_still_the_top_level_declaration(self):
        """DG-469 review: `default_install_hook_types : [...]` (space
        before the colon) is valid YAML, read by pre-commit identically to
        the unspaced key."""
        text = "default_install_hook_types : [pre-commit, commit-msg]\nrepos: []\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_quoted_key_with_a_space_before_the_colon_also_parses(self):
        text = '"default_install_hook_types" : [pre-commit, commit-msg]\nrepos: []\n'
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_mismatched_quotes_around_the_key_are_not_the_declaration(self):
        """`'default_install_hook_types"` is not a valid YAML plain or
        quoted key at all — the opening and closing quote characters must
        match — so this must not be read as a match either."""
        text = "'default_install_hook_types\": [pre-commit]\nrepos: []\n"
        assert doctor.declared_hook_types(text) == ["pre-commit"]

    def test_a_multiline_double_quoted_scalar_folding_onto_column_zero_fails_loud(
        self,
    ):
        """DG-469 review (HIGH): a double-quoted YAML scalar may continue
        on a following line with *no* indentation at all — unlike a block
        mapping, which always requires more indentation than its parent.
        A continuation line that happens to start with
        `default_install_hook_types:` reads, to this line-based scanner,
        exactly like a clean top-level declaration, even though the parsed
        document has no such key anywhere. PyYAML is only a dev dependency
        here (pre-commit's own), not a runtime one, so this reader cannot
        resolve the ambiguity by actually parsing — it must fail loud
        instead of guessing."""
        text = (
            'description: "foo\n'
            "default_install_hook_types: [pre-push]\n"
            'bar"\n'
            "repos: []\n"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_a_multiline_single_quoted_scalar_folding_onto_column_zero_fails_loud(
        self,
    ):
        text = (
            "description: 'foo\n"
            "default_install_hook_types: [pre-push]\n"
            "bar'\n"
            "repos: []\n"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_a_closed_quoted_value_on_one_line_does_not_trigger_the_ambiguity_guard(
        self,
    ):
        """The ambiguity guard above is about a quote left *open* across a
        line boundary — an ordinary quoted value, fully closed on the same
        line, must still parse normally."""
        text = 'description: "default_install_hook_types: not this"\nrepos: []\n'
        assert doctor.declared_hook_types(text) == ["pre-commit"]

    def test_windows_line_endings_with_a_quoted_key_still_parse(self):
        text = '"default_install_hook_types": [pre-commit, commit-msg]\r\nrepos: []\r\n'
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_a_leading_bom_with_a_quoted_key_still_parses(self):
        text = (
            chr(0xFEFF)
            + '"default_install_hook_types": [pre-commit, commit-msg]\n'
            + "repos: []\n"
        )
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    def test_an_alias_value_fails_loud_rather_than_resolving_it(self):
        """DG-469 review probe: `*name` referencing an anchor defined
        elsewhere is a shape this hand-rolled reader cannot resolve
        without a real YAML parser — it must fail loud, never read as the
        bare default and risk silently narrowing a real declaration."""
        text = (
            "shared: &shared_types [pre-commit, commit-msg]\n"
            "default_install_hook_types: *shared_types\n"
            "repos: []\n"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_a_document_marker_before_the_declaration_still_parses(self):
        """DG-469 review probe: a leading `---` document marker is neither
        the key nor indentation — it must not interfere with an otherwise
        clean, unambiguous top-level declaration after it."""
        text = "---\ndefault_install_hook_types: [pre-commit, commit-msg]\nrepos: []\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]


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
        _write_native_pre_push_hook(root / ".git" / "hooks")
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
        _write_native_pre_push_hook(root / ".git" / "hooks")

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
        _write_native_pre_push_hook(main / ".git" / "hooks")
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
        _write_native_pre_push_hook(root / ".git" / "hooks")
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
        _write_native_pre_push_hook(root / ".git" / "hooks")

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


class TestStripInlineCommentIsEscapeAware:
    """DG-478: ``_strip_inline_comment`` toggled quote state per line with
    no escape awareness at all, unlike ``_quote_state_after`` (DG-469's own
    escape-aware scan). An escaped quote inside a double-quoted flow item
    desynchronised the two: ``_strip_inline_comment`` thought the quote
    had already closed, and either cut the line in the wrong place or left
    a real trailing comment attached to the value.
    """

    def test_an_escaped_double_quote_does_not_desync_the_comment_scan(self):
        line = 'default_install_hook_types: ["a\\"b", "pre-commit"]  # comment'
        assert doctor._strip_inline_comment(line) == (
            'default_install_hook_types: ["a\\"b", "pre-commit"]  '
        )

    def test_a_hash_inside_an_escaped_double_quoted_value_is_not_a_comment(self):
        line = 'key: "a\\"#b"  # real comment'
        assert doctor._strip_inline_comment(line) == 'key: "a\\"#b"  '

    def test_agrees_with_quote_state_after_on_an_open_single_quote(self):
        """Both functions apply the same rule for where a comment starts;
        on a line whose quote never closes, neither sees one."""
        line = "key: 'a#b"
        assert doctor._quote_state_after(line, None) == "'"
        assert doctor._strip_inline_comment(line) == line

    def test_a_doubled_single_quote_does_not_close_it_early(self):
        """``''`` inside a single-quoted scalar is a literal quote, not the
        end of the scalar -- a `#` right after it is still inside the
        scalar, exactly as ``_quote_state_after`` already treats it."""
        line = "key: 'can''t # not a comment'  # real comment"
        assert doctor._strip_inline_comment(line) == ("key: 'can''t # not a comment'  ")


class TestNativePrePushHookCheck:
    """DG-479: pre-push left `default_install_hook_types` entirely (the
    native hook is its sole owner), so `missing_hook_types` alone would now
    report nothing wrong even with no push-time scan installed at all.
    `_native_pre_push_status` closes that gap, and `guard.git_hooks` folds
    it into the same check regardless of what the config declares.
    """

    def test_a_missing_native_hook_fails_even_with_every_declared_type_present(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        # No native pre-push hook written at all.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "pre-push" in check.detail
        assert check.remediation == "drunken-init --install-git-hooks"

    def test_a_foreign_pre_push_hook_with_no_marker_fails(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        hooks_dir_path = root / ".git" / "hooks"
        (hooks_dir_path / "pre-push").write_text(
            "#!/bin/sh\necho someone elses hook\nexit 0\n", encoding="utf-8"
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "marker" in check.detail

    def test_a_legacy_demoted_hook_fails_even_though_a_pre_push_file_exists(
        self, tmp_path
    ):
        """DG-479_DECISION.md: `pre-commit install --hook-type pre-push`
        demotes an existing native hook to `pre-push.legacy` and installs
        its own shim as `pre-push` — which, on this Windows setup, never
        actually chains to the `.legacy` file. A `pre-push` file existing
        is therefore not enough; `.legacy` sitting next to it must fail on
        its own, even if the `pre-push` file itself happens to carry the
        marker (pre-commit's own shim does not, but this must not rely on
        that alone)."""
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        (hooks_dir_path / "pre-push.legacy").write_text(
            "#!/bin/sh\nexit 0\n", encoding="utf-8"
        )

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "legacy" in check.detail.lower()

    def test_a_correctly_installed_native_hook_is_ok(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        _write_native_pre_push_hook(root / ".git" / "hooks")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail

    def test_core_hookspath_is_honoured_for_the_native_hook_too(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        (root / "myhooks").mkdir()
        _git("config", "core.hooksPath", "myhooks", cwd=root)
        _write_hook(root / "myhooks", "pre-commit")
        _write_hook(root / "myhooks", "commit-msg")
        _write_native_pre_push_hook(root / "myhooks")
        # Nothing written under .git/hooks at all -- only `myhooks` counts.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail


class TestNeuteredHookContentIsCaught:
    """Reviewer round 2, gap A: the marker alone proved only "drunken-init
    wrote this file once" -- it says nothing about whether the body still
    matches the shipped template. A human (or anything else) appending
    `exit 0` right after the marker, or truncating the body, leaves the
    marker intact and used to read `native_ok=True` -- the privacy scan
    reports healthy while doing nothing at all.
    """

    def _guarded_project(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        return root

    def test_marker_present_but_exit_0_appended_after_it_fails(self, tmp_path):
        root = self._guarded_project(tmp_path)
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        hook = hooks_dir_path / "pre-push"
        hook.write_text(hook.read_text(encoding="utf-8") + "exit 0\n", encoding="utf-8")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "drunken-init --install-git-hooks" in check.detail or (
            check.remediation
            and "drunken-init --install-git-hooks" in check.remediation
        )

    def test_marker_present_but_body_truncated_fails(self, tmp_path):
        root = self._guarded_project(tmp_path)
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        hook = hooks_dir_path / "pre-push"
        full = hook.read_text(encoding="utf-8")
        hook.write_text(full[: len(full) // 2], encoding="utf-8")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail

    def test_one_changed_character_in_the_template_fails(self, tmp_path):
        root = self._guarded_project(tmp_path)
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        hook = hooks_dir_path / "pre-push"
        full = hook.read_text(encoding="utf-8")
        # Flip exactly one character well past the marker line, so the
        # marker check alone would still pass.
        mutated = full.replace("python3 python py", "python3 pythonX py", 1)
        assert mutated != full, "fixture did not actually change anything"
        hook.write_text(mutated, encoding="utf-8")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail

    def test_crlf_converted_but_otherwise_identical_still_passes(self, tmp_path):
        """Line-ending normalisation alone must never be read as tampering
        -- only real content drift."""
        root = self._guarded_project(tmp_path)
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        hook = hooks_dir_path / "pre-push"
        crlf = hook.read_text(encoding="utf-8").replace("\n", "\r\n")
        hook.write_text(crlf, encoding="utf-8", newline="")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail

    def test_the_real_shipped_template_passes(self, tmp_path):
        """Control: the real installer's own output must read ok -- proves
        the content check isn't simply failing everything."""
        root = self._guarded_project(tmp_path)
        _write_native_pre_push_hook(root / ".git" / "hooks")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail


@pytest.mark.skipif(
    sys.platform == "win32", reason="NTFS has no POSIX execute bit to clear"
)
class TestNativeHookExecutableBitIsChecked:
    """Reviewer round 2, gap B: `missing_hook_types` already treats a
    present-but-non-executable pre-commit/commit-msg hook as missing on
    POSIX (NTFS has no bit to check, so it is skipped there) --
    `_native_pre_push_status` never checked this for the native hook at
    all. git invokes a hook file directly; a `pre-push` with no execute
    bit is never run, the same failure as it not existing.
    """

    def _guarded_project(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".pre-commit-config.yaml").write_text(
            GUARDED_CONFIG_FLOW, encoding="utf-8"
        )
        _commit_all(root, "initial")
        _write_hook(root / ".git" / "hooks", "pre-commit")
        _write_hook(root / ".git" / "hooks", "commit-msg")
        return root

    def test_a_present_but_non_executable_native_hook_fails(self, tmp_path):
        root = self._guarded_project(tmp_path)
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        (hooks_dir_path / "pre-push").chmod(0o644)

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "fail", check.detail
        assert "execut" in check.detail.lower()

    def test_an_executable_native_hook_is_ok(self, tmp_path):
        root = self._guarded_project(tmp_path)
        hooks_dir_path = root / ".git" / "hooks"
        _write_native_pre_push_hook(hooks_dir_path)
        (hooks_dir_path / "pre-push").chmod(0o755)

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status == "ok", check.detail


class TestDeclaredHookTypesMatchesYamlOnQuotedShapes:
    """DG-478 acceptance: results match ``yaml.safe_load`` on a table of
    quoted-value shapes. PyYAML is a dev dependency only (pulled in
    transitively by pre-commit's own extra) -- used here as the oracle,
    never imported by the runtime module under test.
    """

    def test_seen_failing_first_escaped_double_quote_with_a_trailing_comment(self):
        """The DG-469 reviewer's first example: this used to raise
        ``UnparseableHookTypesError`` even though pre-commit itself (and
        PyYAML) parses the line without complaint."""
        text = 'default_install_hook_types: ["a\\"b", "pre-commit"]  # comment\n'
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    def test_seen_failing_first_doubled_single_quotes_unescape(self):
        """The DG-469 reviewer's second example: this used to return the
        literal ``can''t`` instead of unescaping it to ``can't``."""
        text = "default_install_hook_types: ['can''t', 'pre-commit']\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert expected == ["can't", "pre-commit"]
        assert doctor.declared_hook_types(text) == expected

    @pytest.mark.parametrize(
        "flow_value",
        [
            "[pre-commit, commit-msg]",
            "['pre-commit', 'commit-msg']",
            '["pre-commit", "commit-msg"]',
            "['can''t', 'pre-commit']",
            '["a\\"b", "pre-commit"]',
        ],
    )
    def test_flow_style_matches_yaml_safe_load(self, flow_value):
        text = f"default_install_hook_types: {flow_value}\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    @pytest.mark.parametrize(
        "item",
        [
            "pre-commit",
            "'pre-commit'",
            '"pre-commit"',
            "'can''t'",
            '"a\\"b"',
        ],
    )
    def test_block_style_matches_yaml_safe_load(self, item):
        text = f"default_install_hook_types:\n  - {item}\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    def test_dg469_behaviour_is_unchanged_nested_declaration_still_fails_loud(self):
        """DG-469's own guarantee must survive this fix untouched: a
        ``default_install_hook_types`` found only nested is still refused,
        never silently read as the top-level declaration."""
        text = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: x\n"
            "        default_install_hook_types: [pre-commit]\n"
        )
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_a_shape_the_scanner_cannot_prove_still_fails_loud_not_narrower(self):
        """The line scanner stays (DG-478 SCOPE): a shape it cannot resolve
        must keep failing loud, never silently narrow to a default that
        reads as if nothing were declared."""
        text = "default_install_hook_types: &hook_types [pre-commit, commit-msg]\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)


class TestDeclaredHookTypesMatchesYamlOnGluedCommentsAndEscapes:
    """DG-483 (found by the DG-475/478 reviewer, non-blocking -- neither
    shape can occur with a real hook-type name): a ``#`` directly after a
    flow list's closing bracket with no whitespace at all, and
    double-quoted escapes other than ``\\"`` and ``\\\\``. Every case here
    is checked against ``yaml.safe_load`` as the oracle; ``doctor`` must
    either return exactly what it returns or refuse the shape outright --
    never a silently different list.
    """

    def test_seen_failing_first_a_comment_glued_to_the_closing_bracket(self):
        """PyYAML reads a ``#`` immediately after a flow sequence's
        closing ``]`` as a comment even with no preceding whitespace --
        confirmed against ``yaml.safe_load`` below, not assumed."""
        text = "default_install_hook_types: ['pre-commit']#comment\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert expected == ["pre-commit"]
        assert doctor.declared_hook_types(text) == expected

    def test_seen_failing_first_a_newline_escape_is_decoded(self):
        """Before this fix, ``\\n`` inside a double-quoted item was left
        as the two literal characters ``\\`` and ``n`` instead of being
        decoded to an actual newline, the way ``yaml.safe_load`` reads
        it."""
        text = 'default_install_hook_types: ["a\\nb"]\n'
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert expected == ["a\nb"]
        assert doctor.declared_hook_types(text) == expected

    @pytest.mark.parametrize(
        "flow_value",
        [
            "['pre-commit']#comment",
            "['pre-commit']  #comment",
            '["pre-commit"]#comment',
            '["a\\nb"]',
            '["\\b"]',
            '["\\x41"]',
            '["\\u00e9"]',
            '["\\0"]',
            '["\\/"]',
            '["caf\\u00e9"]',
            '["a#b"]',
            "['pre-commit', 'commit-msg']#comment",
        ],
    )
    def test_flow_style_matches_yaml_safe_load(self, flow_value):
        text = f"default_install_hook_types: {flow_value}\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    @pytest.mark.parametrize(
        "item",
        [
            '"a\\nb"',
            '"\\b"',
            '"\\x41"',
            '"\\u00e9"',
            '"\\0"',
            '"\\/"',
        ],
    )
    def test_block_style_matches_yaml_safe_load(self, item):
        text = f"default_install_hook_types:\n  - {item}\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    def test_crlf_line_endings_with_the_glued_comment_still_parse(self):
        text = "default_install_hook_types: ['pre-commit']#comment\r\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    def test_a_block_item_with_a_comment_glued_to_its_closing_quote(self):
        text = 'default_install_hook_types:\n  - "pre-commit"#comment\n  - commit-msg\n'
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert expected == ["pre-commit", "commit-msg"]
        assert doctor.declared_hook_types(text) == expected

    @pytest.mark.parametrize(
        "escape",
        [
            "\\q",
            "\\a",
            "\\v",
            "\\f",
            "\\r",
            "\\e",
            "\\U0001F600",
            "\\x4",
            "\\x4g",
            "\\u00e",
        ],
    )
    def test_an_unimplemented_or_malformed_escape_fails_loud_never_mismatches(
        self, escape
    ):
        """Each of these is either a real YAML escape this hand-rolled
        reader does not implement (``\\a``, ``\\v``, ``\\f``, ``\\r``,
        ``\\e``, ``\\U...``) or malformed (truncated ``\\x``/``\\u``, an
        unknown escape letter) -- ``yaml.safe_load`` either decodes it to
        something this reader must not guess at, or raises itself.
        Either way, ``doctor`` must refuse rather than return a value
        that could silently differ from PyYAML's own."""
        text = f'default_install_hook_types: ["{escape}"]\n'
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)


class TestDeclaredHookTypesRefusesNestedFlowCollections:
    """DG-483 PR follow-up review: the bare-comment-after-closing-bracket
    rule exposed a pre-existing blindness in the flow-list splitter to a
    *nested* flow collection. ``[[a],b]#x`` raised ``UnparseableHookTypesError``
    on ``develop`` (the un-glued comment kept the whole line from matching
    the old ``[...]`` pattern at all), but on top of the comment fix it
    silently returned ``['[a]', 'b']`` -- a different, narrower list than
    ``yaml.safe_load``'s own ``[['a'], 'b']``, exactly the thing this
    module's own contract forbids. The fix must live in the flow-list
    splitter itself (any nested ``[``/``{`` outside a quoted scalar is
    refused), not in a comment special-case, so it holds for both a
    glued and a spaced-out comment.
    """

    @pytest.mark.parametrize(
        "flow_value",
        [
            "[[a],b]#x",
            "[[a],b] # x",
            "[[a],b]",
            "[{a: b}]#x",
            "[{a: b}]",
        ],
    )
    def test_seen_failing_first_a_nested_flow_collection_fails_loud(self, flow_value):
        text = f"default_install_hook_types: {flow_value}\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    @pytest.mark.parametrize(
        "flow_value",
        [
            '["[a]"]',
            "['a]b']",
            "['a,b']",
            '["{a: b}"]',
        ],
    )
    def test_a_literal_bracket_inside_a_quoted_item_is_not_nesting(self, flow_value):
        """A bracket character is only a nested collection when it sits
        outside any quoted scalar -- the same quote-awareness every other
        scan in this module already applies. These must still match
        ``yaml.safe_load`` exactly, never be refused."""
        text = f"default_install_hook_types: {flow_value}\n"
        expected = yaml.safe_load(text)["default_install_hook_types"]
        assert doctor.declared_hook_types(text) == expected

    def test_mutation_special_casing_only_the_glued_comment_is_insufficient(self):
        """A regression guard for the fix's own shape: a *spaced-out*
        comment on a nested flow collection must fail exactly like the
        glued one -- if a fix only taught the comment scanner about
        nesting rather than the flow-list splitter itself, this one
        would keep passing while the glued-comment case above was
        "fixed", silently leaving the splitter still blind to nesting
        whenever no comment is glued to the bracket at all (see the
        third case in the parametrize above, with no comment at all)."""
        text = "default_install_hook_types: [[a],b]\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)


class TestDeclaredHookTypesNeverSilentlyEmpty:
    """DG-487 (found by the DG-483 worker, pre-existing): `declared_hook_types`
    filtered falsy items out of a flow list (`['']` returned `[]` where
    `yaml.safe_load` returns `['']`), so a declared list that is empty
    after parsing could read as "nothing declared" -- and
    `missing_hook_types([], ...)` returns `[]` for an empty list, so
    `guard.git_hooks` reported ok having checked nothing at all, the
    exact failure mode DG-466 exists to rule out. Every shape here must
    either fail loud (`UnparseableHookTypesError`) or return exactly what
    `yaml.safe_load` does -- never a narrower list, and never ok on an
    empty checklist while the key is present.
    """

    @pytest.mark.parametrize(
        "flow_value",
        [
            "['']",
            '[""]',
            "[ ]",
            "[]",
            '[pre-commit, ""]',
        ],
    )
    def test_seen_failing_first_an_empty_item_or_empty_list_fails_loud(
        self, flow_value
    ):
        text = f"default_install_hook_types: {flow_value}\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    @pytest.mark.parametrize(
        "block_text",
        [
            "default_install_hook_types:\n  - ''\n",
            'default_install_hook_types:\n  - ""\n',
            "default_install_hook_types:\n  - pre-commit\n  - ''\n",
        ],
    )
    def test_seen_failing_first_a_block_style_empty_item_fails_loud(self, block_text):
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(block_text)

    @pytest.mark.parametrize(
        "flow_value",
        [
            "[' ']",
            '["\\t"]',  # the decoded single-tab-character escape
        ],
    )
    def test_a_whitespace_only_item_also_fails_loud(self, flow_value):
        """The ticket's own wording covers more than the literal empty
        string: a single-quoted item that is only a space, and a
        double-quoted item that decodes to a single tab character, are
        just as much "no real hook type to check" as `''` -- even though
        `yaml.safe_load` itself reads them as a non-empty string, this
        reader must still refuse rather than pass a whitespace-only
        value on to `missing_hook_types`."""
        text = f"default_install_hook_types: {flow_value}\n"
        with pytest.raises(doctor.UnparseableHookTypesError):
            doctor.declared_hook_types(text)

    def test_the_key_absent_default_is_unaffected(self):
        """The one shape that must still return the bare default -- this
        fix must never touch the key-absent path."""
        assert doctor.declared_hook_types("repos: []\n") == ["pre-commit"]

    def test_a_normal_non_empty_flow_list_is_unaffected(self):
        text = "default_install_hook_types: [pre-commit, commit-msg]\n"
        assert doctor.declared_hook_types(text) == ["pre-commit", "commit-msg"]

    @pytest.mark.parametrize(
        "flow_value",
        [
            "['']",
            '[""]',
            "[ ]",
            "[]",
        ],
    )
    def test_seen_failing_first_the_check_does_not_report_ok_on_an_empty_declaration(
        self, flow_value, tmp_path
    ):
        """The false-ok half of DG-487: before this fix,
        `missing_hook_types([], ...)` returns `[]` for an empty declared
        list, so `guard.git_hooks` reported ok having checked nothing.
        Routed through the real check function and `run_doctor`, not a
        stubbed helper, with no hook files installed at all -- an ok here
        would be the exact false-ok this ticket exists to rule out."""
        root = tmp_path / "proj"
        _init_repo(root)
        config = GUARDED_CONFIG_FLOW.replace(
            "default_install_hook_types: [pre-commit, commit-msg]\n",
            f"default_install_hook_types: {flow_value}\n",
        )
        (root / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
        _commit_all(root, "initial")
        # Deliberately no hooks installed at all.

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "guard.git_hooks.scratch")
        assert check.status != "ok", (
            "an empty declared list must never report ok -- it checked "
            f"nothing. Got {check.status}: {check.detail}"
        )


class TestDeclaredHookTypesFuzzedAgainstYamlSafeLoad:
    """The reviewer's own fuzz idea, run here rather than merely proposed:
    a large number of randomly built flow-list lines, each checked
    against `yaml.safe_load` as the oracle. `doctor.declared_hook_types`
    must, for every one, either match PyYAML's own list exactly or raise
    `UnparseableHookTypesError` -- never a different or narrower list.
    """

    ATOMS = (
        "pre-commit",
        "commit-msg",
        "'single'",
        "'can''t'",
        '"double"',
        '"a\\"b"',
        '"a\\nb"',
        "''",
        '""',
        "a#b",
        "'a]b'",
        "'a,b'",
        "[nested]",
        "{a: b}",
    )

    @staticmethod
    def _random_flow_value(rng) -> str:
        count = rng.randint(0, 4)
        items = [
            rng.choice(TestDeclaredHookTypesFuzzedAgainstYamlSafeLoad.ATOMS)
            for _ in range(count)
        ]
        separator = rng.choice([", ", ",", " , "])
        body = separator.join(items)
        spacing = rng.choice(["", " "])
        return f"[{spacing}{body}{spacing}]"

    def test_two_thousand_random_flow_lines_never_mismatch_or_narrow(self):
        rng = random.Random(0x4DEFACED)
        mismatches = []
        checked = 0
        for _ in range(2000):
            flow_value = self._random_flow_value(rng)
            glue_comment = rng.choice([True, False, False])
            text = f"default_install_hook_types: {flow_value}"
            if glue_comment:
                text += "#x"
            else:
                if rng.choice([True, False]):
                    text += "  # x"
            text += "\n"

            try:
                expected_doc = yaml.safe_load(text)
            except yaml.YAMLError:
                expected_doc = _YAML_REJECTED

            try:
                actual = doctor.declared_hook_types(text)
            except doctor.UnparseableHookTypesError:
                actual = _READER_REFUSED
            except Exception as exc:  # pragma: no cover - a crash is itself a bug
                mismatches.append((text, "CRASH", repr(exc)))
                continue

            checked += 1
            if expected_doc is _YAML_REJECTED:
                # yaml.safe_load itself could not read this line: any
                # outcome from doctor is fine *except* silently returning
                # a value, since there is no "yaml's own list" to match.
                continue
            expected = expected_doc.get("default_install_hook_types")
            if actual is _READER_REFUSED:
                continue
            if actual != expected:
                mismatches.append((text, expected, actual))

        assert checked >= 2000
        assert mismatches == [], (
            f"{len(mismatches)} case(s) where doctor returned a different "
            f"or narrower list than yaml.safe_load instead of refusing. "
            f"First few: {mismatches[:5]!r}"
        )
