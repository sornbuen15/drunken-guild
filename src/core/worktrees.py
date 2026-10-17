"""Inventory and manually synchronize a project's AI layer across git worktrees."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import ai_layer
from .errors import ValidationError
from .exclude import run_git
from .layer_copy import ai_layer_files_under


@dataclass(frozen=True)
class WorktreeLayer:
    """What one linked worktree has relative to the registered checkout."""

    root: Path
    missing: tuple[str, ...] = ()
    different: tuple[str, ...] = ()
    would_copy: tuple[str, ...] = ()
    copied: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


def list_worktrees(git_root: Path) -> list[Path]:
    """Return git worktree roots, preserving spaces and special path characters."""
    result = run_git(
        ["worktree", "list", "--porcelain", "-z"], git_root, text=False, timeout=30
    )
    if result.returncode != 0:
        raise ValidationError(
            f"Could not list worktrees for {git_root}: {result.stderr!r}",
            remediation="Check that the registered path is a readable git worktree.",
        )
    roots = []
    for field in result.stdout.split(b"\0"):
        if field.startswith(b"worktree "):
            roots.append(
                Path(field[len(b"worktree ") :].decode("utf-8", "surrogateescape"))
            )
    return roots


def _project_relative_to_git_root(project_root: Path, git_root: Path) -> Path:
    try:
        return project_root.resolve().relative_to(git_root.resolve())
    except ValueError as exc:
        raise ValidationError(
            f"Registered project path {project_root} is outside git root {git_root}.",
            remediation="Correct the project's registered path or git_root setting.",
        ) from exc


def _source_files(project_root: Path, tracked: set[str]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if not project_root.is_dir():
        return files
    for relative in ai_layer_files_under(project_root, skip_dependency_dirs=True):
        name = relative.as_posix()
        if ai_layer.is_copied_in_from_config_repo(name):
            files[name] = (project_root / relative).read_bytes()
    return files


def _tracked_ai_layer_paths(worktree_root: Path, project_relative: Path) -> set[str]:
    result = run_git(["ls-files", "-z"], worktree_root, text=False, timeout=30)
    if result.returncode != 0:
        raise ValidationError(
            f"Could not inspect tracked paths in worktree {worktree_root}.",
            remediation="Check that the worktree is readable and its index is valid.",
        )
    tracked = (
        field.decode("utf-8", "surrogateescape")
        for field in result.stdout.split(b"\0")
        if field
    )
    prefix = project_relative.as_posix()
    if prefix == ".":
        candidates = tracked
    else:
        candidates = (
            name[len(prefix) + 1 :] for name in tracked if name.startswith(prefix + "/")
        )
    return {name for name in candidates if ai_layer.is_copied_in_from_config_repo(name)}


def _safe_destination(root: Path, relative: str) -> Path | None:
    destination = root / Path(relative)
    try:
        destination.relative_to(root)
    except ValueError:
        return None
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return None
    return destination


def _inspect_one(
    root: Path,
    project_relative: Path,
    source_files: dict[str, bytes],
    tracked: set[str],
) -> WorktreeLayer:
    missing: list[str] = []
    different: list[str] = []
    for relative, source_bytes in source_files.items():
        destination = _safe_destination(root, (project_relative / relative).as_posix())
        if destination is None or relative in tracked:
            different.append(relative)
        elif not destination.exists():
            missing.append(relative)
        elif not destination.is_file() or destination.read_bytes() != source_bytes:
            different.append(relative)
    return WorktreeLayer(
        root=root,
        missing=tuple(missing),
        different=tuple(different),
    )


def inspect(project_root: Path, git_root: Path) -> list[WorktreeLayer]:
    """List linked worktrees missing or differing from the registered checkout's AI layer."""
    project_root = Path(project_root).resolve()
    git_root = Path(git_root).resolve()
    project_relative = _project_relative_to_git_root(project_root, git_root)
    source_files = _source_files(project_root, set())
    results = []
    for root in list_worktrees(git_root):
        root = root.resolve()
        if root == git_root:
            continue
        results.append(
            _inspect_one(
                root,
                project_relative,
                source_files,
                _tracked_ai_layer_paths(root, project_relative),
            )
        )
    return results


def _exclude_copied_files(
    root: Path, project_relative: Path, candidates: list[str]
) -> None:
    result = run_git(["rev-parse", "--git-path", "info/exclude"], root, timeout=30)
    if result.returncode != 0:
        raise ValidationError(
            f"Could not locate this worktree's info/exclude file: {result.stderr.strip()}",
            remediation="Check that the linked worktree is readable and its Git metadata is valid.",
        )
    exclude_path = Path(result.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = root / exclude_path
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    with exclude_path.open("a", encoding="utf-8") as handle:
        for relative in candidates:
            handle.write(f"\n/{(project_relative / relative).as_posix()}\n")


def _sync_one(
    root: Path,
    project_root: Path,
    project_relative: Path,
    source_files: dict[str, bytes],
    *,
    apply: bool,
) -> WorktreeLayer:
    tracked = _tracked_ai_layer_paths(root, project_relative)
    target_root = root / project_relative
    copied: list[str] = []
    unchanged: list[str] = []
    conflicts: list[str] = []
    candidates: list[str] = []

    for relative, source_bytes in source_files.items():
        destination = _safe_destination(root, (project_relative / relative).as_posix())
        if destination is None or relative in tracked:
            conflicts.append(relative)
        elif not destination.exists():
            candidates.append(relative)
        elif destination.is_file() and destination.read_bytes() == source_bytes:
            unchanged.append(relative)
        else:
            conflicts.append(relative)

    if apply and candidates:
        for relative in candidates:
            destination = target_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project_root / relative, destination)
        _exclude_copied_files(root, project_relative, candidates)
        copied.extend(candidates)

    return WorktreeLayer(
        root=root,
        would_copy=tuple(candidates),
        copied=tuple(copied),
        unchanged=tuple(unchanged),
        conflicts=tuple(conflicts),
    )


def sync(project_root: Path, git_root: Path, *, apply: bool) -> list[WorktreeLayer]:
    """Preview or copy missing AI-layer files without replacing existing files."""
    project_root = Path(project_root).resolve()
    git_root = Path(git_root).resolve()
    project_relative = _project_relative_to_git_root(project_root, git_root)
    source_files = _source_files(project_root, set())
    results = []

    for root in list_worktrees(git_root):
        root = root.resolve()
        if root == git_root:
            continue
        results.append(
            _sync_one(root, project_root, project_relative, source_files, apply=apply)
        )

    return results
