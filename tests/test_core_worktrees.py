from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core import doctor, exclude, init, worktrees
from core.registry import ProjectRegistry

GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *GIT_IDENTITY, *args], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture  # type: ignore[misc]
def project_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "--initial-branch=main", "-q")
    (root / "app.py").write_text("print('hello')\n", encoding="utf-8")
    git(root, "add", "app.py")
    git(root, "commit", "-m", "initial", "-q")
    exclude.exclude_ai_layer(root)
    (root / "AGENTS.md").write_text("shared instructions\n", encoding="utf-8")
    claude = root / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}\n", encoding="utf-8")
    target = tmp_path / "target"
    git(root, "worktree", "add", "-b", "target", str(target), "HEAD", "-q")
    return root, target


def test_doctor_inventory_reports_files_missing_from_worktree(
    project_with_worktree: tuple[Path, Path],
) -> None:
    root, _ = project_with_worktree

    inventory = worktrees.inspect(root, root)

    assert len(inventory) == 1
    assert inventory[0].missing == (".claude/settings.json", "AGENTS.md")


def test_sync_plan_does_not_write_until_apply(
    project_with_worktree: tuple[Path, Path],
) -> None:
    root, target = project_with_worktree

    plan = worktrees.sync(root, root, apply=False)

    assert plan[0].would_copy == (".claude/settings.json", "AGENTS.md")
    assert not (target / "AGENTS.md").exists()


def test_sync_apply_is_idempotent_and_excludes_copied_layer(
    project_with_worktree: tuple[Path, Path],
) -> None:
    root, target = project_with_worktree

    first = worktrees.sync(root, root, apply=True)
    second = worktrees.sync(root, root, apply=True)

    assert first[0].copied == (".claude/settings.json", "AGENTS.md")
    assert second[0].copied == ()
    assert second[0].unchanged == (".claude/settings.json", "AGENTS.md")
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == "shared instructions\n"
    assert git(target, "check-ignore", "AGENTS.md") == "AGENTS.md"
    source_excludes = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert source_excludes.count("\n/AGENTS.md\n") == 1
    target_exclude_path = Path(git(target, "rev-parse", "--git-path", "info/exclude"))
    if not target_exclude_path.is_absolute():
        target_exclude_path = target / target_exclude_path
    target_excludes = target_exclude_path.read_text(encoding="utf-8")
    assert target_excludes.count("\n/AGENTS.md\n") == 1


def test_doctor_detects_ai_layer_files_added_after_worktree_creation(
    project_with_worktree: tuple[Path, Path],
) -> None:
    root, _ = project_with_worktree
    (root / "CLAUDE.md").write_text("new guidance\n", encoding="utf-8")

    inventory = worktrees.inspect(root, root)

    assert inventory[0].missing == (".claude/settings.json", "AGENTS.md", "CLAUDE.md")


def test_sync_reports_and_preserves_a_different_instruction_file(
    project_with_worktree: tuple[Path, Path],
) -> None:
    root, target = project_with_worktree
    (target / "AGENTS.md").write_text("local instructions\n", encoding="utf-8")

    result = worktrees.sync(root, root, apply=True)

    assert result[0].copied == (".claude/settings.json",)
    assert result[0].conflicts == ("AGENTS.md",)
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == "local instructions\n"


def test_doctor_warns_for_worktree_missing_project_layer(
    project_with_worktree: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, target = project_with_worktree
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"version": 2, "projects": {"alpha": {"path": str(root)}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DRUNKEN_HOME", str(tmp_path / "home"))

    report = doctor.run_doctor(
        project="alpha", registry=ProjectRegistry(str(registry_path)), offline=True
    )
    check = next(
        item for item in report.checks if item.name == "worktrees.ai_layer.alpha"
    )

    assert check.status == "warn"
    assert str(target) in check.detail
    assert "AGENTS.md" in check.detail


def test_init_sync_worktrees_previews_then_applies(
    project_with_worktree: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, target = project_with_worktree
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"version": 2, "projects": {"alpha": {"path": str(root)}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drunken-init",
            "--project",
            "alpha",
            "--sync-worktrees",
            "--registry",
            str(registry_path),
        ],
    )

    assert init.main() == 0
    assert "would copy" in capsys.readouterr().out
    assert not (target / "AGENTS.md").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drunken-init",
            "--project",
            "alpha",
            "--sync-worktrees",
            "--apply",
            "--registry",
            str(registry_path),
        ],
    )
    assert init.main() == 0
    assert "copied" in capsys.readouterr().out
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == "shared instructions\n"
