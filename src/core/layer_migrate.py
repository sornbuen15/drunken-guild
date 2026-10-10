"""``drunken-init --migrate-ai-layer`` moves a project's committed AI layer out of its git — DG-446.

REQ-019: a project under the guild tracks none of its AI layer. A project that already committed
``AGENTS.md``, ``CLAUDE.md`` or ``.claude/`` is the case ``drunken-init`` refuses (DG-442) and
``drunken-doctor`` fails (``layering.tracked``); this is the way out, in one command:

1. **Back up** every tracked AI-layer file to a directory outside the repository — the working-tree
   bytes, so an uncommitted edit is kept, and for a tracked file missing from disk the index copy.
   The backup is read back and compared before anything else happens.
2. **Restore** a tracked file that was missing from disk, from the index, so the agent still finds
   its instructions after the untracking.
3. **Exclude** the layer from then on, through :func:`core.exclude.exclude_ai_layer`. This comes
   *before* the untracking on purpose: a run that stops between the two leaves files that are
   still tracked, so a rerun still finds them, instead of untracked-but-visible files that no
   rerun would ever look at (review of #183).
4. **Untrack** with ``git rm --cached``: the files stay on disk, and the deletion is *staged*. The
   person commits it; this module never commits in somebody's repository.

The list of paths is :mod:`core.ai_layer`'s one list, read through
:func:`core.doctor.tracked_ai_layer_paths` — the same answer the doctor check gives, so "what the
doctor flags" and "what this moves" cannot differ.

**What it does not do, on purpose.** It does not rewrite history: the files stay in every earlier
commit, so a credential that was ever committed there stays readable and must be rotated by the
person (the result says so whenever it finds one). It does not touch this repository's own AI layer
(the caller refuses that case, as ``_target_is_this_repository`` already does for the copy-in). And
it never follows a symlink: a tracked AI-layer path that is a symlink, or sits behind one, is
refused whole, before anything changes.
"""

from __future__ import annotations

import filecmp
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import content_scan, exclude
from .errors import ValidationError

#: ``git rm`` takes the paths on the command line; this many at a time keeps it under any limit.
_CHUNK = 50
_GIT_TIMEOUT = 60.0

HISTORY_NOTE = (
    "The files are untracked, not erased: every earlier commit still holds them. Rewriting history "
    "is not done by this tool. Anything secret that was ever committed there must be rotated."
)


class MigrationError(ValidationError):
    """The migration was refused or failed; the message names why and what is unchanged."""


@dataclass
class MigrationResult:
    git_root: Path
    applied: bool
    backup_dir: Optional[Path] = None
    migrated: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    history_note: str = ""


def _tracked_layer(git_root: Path) -> list[str]:
    # Imported here: ``doctor`` is the heavier module and nothing else in this one needs it.
    from .doctor import tracked_ai_layer_paths

    try:
        exclude.resolve_info_exclude_path(git_root)
    except exclude.GitCommandError as exc:
        raise MigrationError(
            f"{git_root} is not the top level of a git repository: {exc}",
            remediation="Point at the folder that holds .git (the registry's git_root offset).",
        ) from exc

    paths = tracked_ai_layer_paths(git_root)
    if paths is None:
        raise MigrationError(
            f"git could not list the tracked files of {git_root}.",
            remediation="Run `git status` there and fix what it reports; nothing was changed.",
        )
    return paths


def _refuse_symlinks(git_root: Path, rels: list[str]) -> None:
    root = git_root.resolve()
    for rel in rels:
        probe = git_root / rel
        chain = [
            probe,
            *[
                p
                for p in probe.parents
                if p != git_root and root in p.resolve().parents
            ],
        ]
        for part in chain:
            if part.is_symlink():
                raise MigrationError(
                    f"{rel} is, or sits behind, a symlink ({part.relative_to(git_root).as_posix()}).",
                    remediation=(
                        "Replace the link with a real file or move it by hand, then run this "
                        "again. Nothing was changed."
                    ),
                )


def _index_bytes(git_root: Path, rel: str) -> bytes:
    done = exclude.run_git(
        ["show", f":{rel}"], git_root, text=False, timeout=_GIT_TIMEOUT
    )
    if done.returncode != 0:
        raise MigrationError(
            f"git has no index copy of {rel}.",
            remediation="Nothing was changed; run `git status` and resolve the file first.",
        )
    return bytes(done.stdout)


def _prepare_backup_dir(backup_dir: Path, git_root: Path) -> None:
    if git_root.resolve() in [backup_dir.resolve(), *backup_dir.resolve().parents]:
        raise MigrationError(
            f"the backup directory {backup_dir} is inside the repository.",
            remediation="Choose a directory outside the project; a backup inside it would be tracked.",
        )
    if backup_dir.exists() and any(backup_dir.iterdir()):
        raise MigrationError(
            f"the backup directory {backup_dir} already holds files.",
            remediation="Pass an empty or new directory; nothing was changed.",
        )
    backup_dir.mkdir(parents=True, exist_ok=True)
    _private(backup_dir, directory=True)


def _private(path: Path, *, directory: bool) -> None:
    """Owner-only, best effort: the backup holds whatever secret the layer held (review of #183).

    POSIX gets 0700/0600. Windows ignores most of the mode bits, so there the backup is as private
    as its parent directory (under the state directory by default) — this does not claim more.
    """
    try:
        os.chmod(path, 0o700 if directory else 0o600)
    except OSError:
        pass


def _back_up(git_root: Path, rels: list[str], backup_dir: Path) -> list[str]:
    """Copy every file out and read it back. Returns those that were missing from disk."""
    missing: list[str] = []
    for rel in rels:
        source = git_root / rel
        target = backup_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        for parent in target.parents:
            if parent == backup_dir.parent:
                break
            _private(parent, directory=True)
        if source.is_file():
            shutil.copy2(source, target)
            _private(target, directory=False)
            if not filecmp.cmp(source, target, shallow=False):
                raise MigrationError(
                    f"the backup of {rel} does not match the original.",
                    remediation="Nothing was untracked; check the backup disk and run this again.",
                )
        else:
            target.write_bytes(_index_bytes(git_root, rel))
            _private(target, directory=False)
            missing.append(rel)
    return missing


def _scan(backup_dir: Path, rels: list[str]) -> list[str]:
    lines: list[str] = []
    for rel in rels:
        for finding in content_scan.scan_file(backup_dir / rel, rel):
            lines.append(finding.describe())
    return lines


def _untrack(git_root: Path, rels: list[str]) -> None:
    for start in range(0, len(rels), _CHUNK):
        batch = [f":(literal){rel}" for rel in rels[start : start + _CHUNK]]
        done = exclude.run_git(
            ["rm", "--cached", "-q", "--", *batch], git_root, timeout=_GIT_TIMEOUT
        )
        if done.returncode != 0:
            raise MigrationError(
                f"git rm --cached failed after the backup was made: {done.stderr.strip()}",
                remediation=(
                    "The files are still on disk and the backup is intact; run `git status` "
                    "in the project to see how far it got."
                ),
            )


def migrate_ai_layer_out(
    git_root: Path, backup_dir: Path, *, apply: bool
) -> MigrationResult:
    """Plan, or perform, the migration of *git_root*'s tracked AI layer.

    ``apply=False`` writes nothing at all and returns the plan. ``apply=True`` backs up, restores,
    untracks and excludes in that order; the backup is verified before the first ``git`` write.
    """
    git_root = Path(git_root)
    rels = _tracked_layer(git_root)
    result = MigrationResult(git_root=git_root, applied=apply, migrated=list(rels))
    if not rels:
        result.migrated = []
        return result

    _refuse_symlinks(git_root, rels)
    result.history_note = HISTORY_NOTE
    if not apply:
        return result

    _prepare_backup_dir(backup_dir, git_root)
    result.backup_dir = backup_dir
    missing = _back_up(git_root, rels, backup_dir)
    result.findings = _scan(backup_dir, rels)

    for rel in missing:
        target = git_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((backup_dir / rel).read_bytes())
    result.restored = missing

    exclude.exclude_ai_layer(git_root)
    _untrack(git_root, rels)
    return result
