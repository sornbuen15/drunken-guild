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
