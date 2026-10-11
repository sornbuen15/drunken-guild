# mypy: ignore-errors
"""DG-443: `drunken-doctor` flags a credential-, identity- or path-shaped
value already sitting in a registered project's on-disk AI-layer files —
the second, independent line of defence behind `drunken-init`'s own
pre-write refusal (a file hand-edited after copy, or copied by an older
build, before this ticket existed).

Every "looks like a real secret" literal below is built at test time, same
as `tests/test_content_scan.py` and `tests/test_layer_copy.py` — never a
real-looking literal pasted whole.
"""

import json
import os

import pytest
from test_core_doctor_layering import GIT_IDENTITY, _git, _init_repo, find  # noqa: F401

from core import doctor
from core.registry import ProjectRegistry


def _commit_all(root, message: str) -> None:
    _git("add", "-A", cwd=root)
    _git("commit", "-m", message, "-q", cwd=root)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setenv("DRUNKEN_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DRUNKEN_REGISTRY_PATH", raising=False)


def _registry(tmp_path, project_id: str, path) -> ProjectRegistry:
    target = tmp_path / "projects.json"
    target.write_text(
        json.dumps({"version": 2, "projects": {project_id: {"path": str(path)}}}),
        encoding="utf-8",
    )
    return ProjectRegistry(str(target))


class TestATokenShapedAiLayerFileFails:
    def test_flags_a_token_shaped_value_copied_into_a_project_checkout(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        secret = "ghp_" + "a" * 36
        (root / ".claude").mkdir()
        (root / ".claude" / "settings.json").write_text(
            json.dumps({"token": secret}), encoding="utf-8"
        )
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "content_scan.scratch")
        assert check.status == "fail", check.detail
        assert "settings.json" in check.detail

    def test_does_not_flag_a_clean_project(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("Nothing sensitive here.\n", encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "content_scan.scratch")
        assert check.status == "ok", check.detail

    def test_skips_a_project_with_no_checkout_path(self, tmp_path):
        missing = tmp_path / "does-not-exist"

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", missing), offline=True
        )

        check = find(report, "content_scan.scratch")
        assert check.status == "skip", check.detail

    def test_the_guilds_own_checkout_is_exempt(self, tmp_path):
        repo_root = doctor.source_tree_root()
        assert repo_root is not None

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "guild", repo_root), offline=True
        )

        check = find(report, "content_scan.guild")
        assert check.status == "skip", check.detail


class TestNestedAndDifferentlyCasedAiLayerFilesAreScanned:
    """DG-508: content_scan did not read a token-shaped value in a nested
    `packages/x/.claude/settings.json`, in a root `.Claude/settings.json` (different case from
    `.claude/`), or a nested `.mcp.json` — all three on `core.ai_layer.is_content_scan_path`'s
    wider list now, even though `layering.tracked`'s narrower `is_ai_layer_path` still does not
    claim any of them (no change to what the config-repo copy-in provides)."""

    def _token(self):
        return "ghp_" + "d" * 36

    def _report(self, tmp_path, root):
        return doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

    def test_nested_claude_settings_json_in_a_subpackage_is_flagged(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "x" / ".claude"
        nested.mkdir(parents=True)
        (nested / "settings.json").write_text(
            json.dumps({"token": self._token()}), encoding="utf-8"
        )
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
        assert "packages/x/.claude/settings.json" in check.detail

    def test_a_differently_cased_root_claude_dir_is_flagged(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        cased = root / ".Claude"
        cased.mkdir()
        (cased / "settings.json").write_text(
            json.dumps({"token": self._token()}), encoding="utf-8"
        )
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
        assert ".Claude/settings.json" in check.detail

    def test_a_nested_mcp_json_is_flagged(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        nested = root / "packages" / "x"
        nested.mkdir(parents=True)
        (nested / ".mcp.json").write_text(
            json.dumps({"token": self._token()}), encoding="utf-8"
        )
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
        assert "packages/x/.mcp.json" in check.detail

    def test_a_nested_claude_dir_inside_a_real_dependency_install_is_still_skipped(
        self, tmp_path
    ):
        # DG-505's guarantee must still hold: the wider content-scan predicate decides which
        # *files* are read inside a directory the walk already chose to descend into — it must
        # never override the directory-level decision to skip a real dependency install.
        root = tmp_path / "proj"
        _init_repo(root)
        venv_pkg = root / ".venv" / "Lib" / "site-packages" / "pkg" / ".claude"
        venv_pkg.mkdir(parents=True)
        (root / ".venv" / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
        (venv_pkg / "settings.json").write_text(self._token(), encoding="utf-8")
        (root / ".gitignore").write_text(".venv/" + chr(10), encoding="utf-8")
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "ok", check.detail


class TestSymlinkedAiLayerDirectoryIsNeverFollowed:
    def test_a_symlinked_claude_dir_is_not_walked_into(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "main.py").write_text("print('hi')", encoding="utf-8")
        _commit_all(root, "initial")

        secret_dir = tmp_path / "outside-secret"
        secret_dir.mkdir()
        secret = "ghp_" + "b" * 36
        (secret_dir / "settings.json").write_text(secret, encoding="utf-8")

        try:
            os.symlink(secret_dir, root / ".claude", target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"cannot create a symlink on this platform/privilege: {exc}")

        report = doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

        check = find(report, "content_scan.scratch")
        assert check.status == "ok", (
            "a symlinked .claude must never be followed, so the secret "
            f"outside the project root must never be reached. Got "
            f"{check.status}: {check.detail}"
        )


class TestInstalledDependenciesAreNotTheProjectsAiLayer:
    """DG-505: the walk read a third-party package's CLAUDE.md inside .venv as the project's own,
    and failed a Python project whose git ignores and tracks none of it."""

    def _token(self):
        return "ghp_" + "b" * 36

    def _report(self, tmp_path, root):
        return doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

    def test_a_real_virtualenv_is_not_scanned(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        venv_pkg = root / ".venv" / "Lib" / "site-packages" / "pkg"
        venv_pkg.mkdir(parents=True)
        (root / ".venv" / "pyvenv.cfg").write_text(
            "home = x" + chr(10), encoding="utf-8"
        )
        (venv_pkg / "CLAUDE.md").write_text(self._token(), encoding="utf-8")
        (root / ".gitignore").write_text(".venv/" + chr(10), encoding="utf-8")
        (root / "main.py").write_text("print(1)", encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "ok", check.detail

    def test_a_virtualenv_under_any_name_is_recognised_by_its_marker(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        env = root / "tooling-env" / "lib" / "pkg"
        env.mkdir(parents=True)
        (root / "tooling-env" / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
        (env / "AGENTS.md").write_text(self._token(), encoding="utf-8")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "ok", check.detail

    def test_node_modules_with_its_lockfile_marker_is_not_scanned(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        pkg = root / "node_modules" / "left-pad"
        pkg.mkdir(parents=True)
        (root / "node_modules" / ".package-lock.json").write_text(
            "{}", encoding="utf-8"
        )
        (pkg / "CLAUDE.md").write_text(self._token(), encoding="utf-8")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "ok", check.detail

    def test_composer_vendor_with_its_installed_json_is_not_scanned(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "vendor" / "composer").mkdir(parents=True)
        (root / "vendor" / "composer" / "installed.json").write_text(
            "{}", encoding="utf-8"
        )
        (root / "vendor" / "acme").mkdir()
        (root / "vendor" / "acme" / "CLAUDE.md").write_text(
            self._token(), encoding="utf-8"
        )

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "ok", check.detail

    def test_a_folder_merely_NAMED_like_a_dependency_directory_is_still_scanned(
        self, tmp_path
    ):
        # The walk's own rule (DG-443 review): a marker must be real, never just a name. A folder
        # called .venv, node_modules or vendor with no marker could be hiding a leak.
        root = tmp_path / "proj"
        _init_repo(root)
        for name in (".venv", "node_modules", "vendor"):
            (root / name).mkdir()
        (root / "vendor" / "AGENTS.md").write_text(self._token(), encoding="utf-8")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
        assert "vendor/AGENTS.md" in check.detail

    def test_the_projects_own_instruction_file_is_still_scanned_beside_a_venv(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".venv").mkdir()
        (root / ".venv" / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
        (root / "AGENTS.md").write_text(self._token(), encoding="utf-8")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
        assert "AGENTS.md" in check.detail


class TestAMarkerCannotHideTheProjectsOwnAiLayer:
    """Review of #192 (BLOCK): a one-line marker file planted where the AI layer lives made the walk
    skip it, hiding a real secret from the one check that exists to find it."""

    def _token(self):
        return "ghp_" + "c" * 36

    def _report(self, tmp_path, root):
        return doctor.run_doctor(
            registry=_registry(tmp_path, "scratch", root), offline=True
        )

    def test_a_marker_inside_the_claude_directory_does_not_hide_its_settings(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".claude").mkdir()
        (root / ".claude" / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
        (root / ".claude" / "settings.json").write_text(
            json.dumps({"token": self._token()}), encoding="utf-8"
        )

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail

    def test_a_marker_inside_the_gemini_directory_does_not_hide_it_either(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / ".gemini").mkdir()
        (root / ".gemini" / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
        (root / ".gemini" / "settings.json").write_text(
            json.dumps({"token": self._token()}), encoding="utf-8"
        )

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail

    def test_a_marker_beside_a_committed_agents_md_does_not_hide_it(self, tmp_path):
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "packages" / "x").mkdir(parents=True)
        (root / "packages" / "x" / "pyvenv.cfg").write_text(
            "home = x", encoding="utf-8"
        )
        (root / "packages" / "x" / "AGENTS.md").write_text(
            self._token(), encoding="utf-8"
        )
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
        assert "packages/x/AGENTS.md" in check.detail

    def test_a_marker_above_a_deeper_committed_instruction_file_does_not_hide_it(
        self, tmp_path
    ):
        root = tmp_path / "proj"
        _init_repo(root)
        deep = root / "packages" / "x" / "sub"
        deep.mkdir(parents=True)
        (root / "packages" / "x" / "pyvenv.cfg").write_text(
            "home = x", encoding="utf-8"
        )
        (deep / "CLAUDE.md").write_text(self._token(), encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail

    def test_an_untracked_real_venv_is_still_skipped_beside_tracked_files(
        self, tmp_path
    ):
        # The point of the PR still holds: a venv no commit touches is not the project's AI layer.
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "AGENTS.md").write_text("rules", encoding="utf-8")
        venv = root / ".venv" / "lib" / "pkg"
        venv.mkdir(parents=True)
        (root / ".venv" / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
        (venv / "CLAUDE.md").write_text(self._token(), encoding="utf-8")
        (root / ".gitignore").write_text(".venv/" + chr(10), encoding="utf-8")
        _commit_all(root, "initial")

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "ok", check.detail

    def test_a_marker_beside_an_untracked_excluded_instruction_file_does_not_hide_it(
        self, tmp_path
    ):
        # A layered project's AI layer is untracked and excluded: git cannot vouch for it, so the
        # directory holding it must not be skippable on a marker alone.
        root = tmp_path / "proj"
        _init_repo(root)
        (root / "packages" / "x").mkdir(parents=True)
        (root / "packages" / "x" / "pyvenv.cfg").write_text(
            "home = x", encoding="utf-8"
        )
        (root / "packages" / "x" / "AGENTS.md").write_text(
            self._token(), encoding="utf-8"
        )
        (root / ".git" / "info" / "exclude").write_text(
            "AGENTS.md" + chr(10), encoding="utf-8"
        )

        check = find(self._report(tmp_path, root), "content_scan.scratch")

        assert check.status == "fail", check.detail
