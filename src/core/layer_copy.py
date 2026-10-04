"""``drunken-init`` copies a project's AI layer in from the config repo —
DG-441 (REQ-019, REQ-020).

REQ-020 says the AI layer of a project under the guild comes from one
private, local config repo clone, never from a packaged template and never
over the network: the Boss clones the config repo by hand; this module only
reads a path it is given. The patterns are read from :mod:`core.ai_layer`
alone, through :func:`core.exclude.exclude_ai_layer`, which this module
calls after every copy so the project's own ``git status`` stays clean —
the same one list DG-437/DG-440 already read, never a second one.

**Copy, never symlink.** :func:`shutil.copy2` always produces a real file,
so a config repo moved or deleted later cannot silently break (or empty
out) a project checkout that depends on it.

**Nothing is written until every file has been checked.** A destination
that already exists *and is tracked by the project's own git* aborts the
whole call before a single byte is copied, naming the path — overwriting a
committed file through this path would be a silent, surprising edit to
version-controlled content. An existing file that git does **not** track is
a softer case: skipped and reported (with whether its content already
matches the config repo), unless the caller passes ``overwrite=True``. Only
the git-tracked case is an absolute refusal; nothing lifts it.

**Never outside the project root, never outside the config repo.** A
project id is validated the same way the registry already validates one
(:func:`core.registry.validate_project_id`) before it is ever joined onto
``config_repo`` and ``project_root``, and the resolved project folder and
every resolved destination are independently checked to still be inside
``config_repo`` and ``project_root`` respectively — defence in depth: the
regex alone rejects a ``project_id`` holding ``/`` or starting with ``.``,
so a working ``validate_project_id`` already stops the realistic attack,
but this does not lean on that alone.

**Pass the git root, not the project root** (comment (a), DG-441). A
project registered at a subfolder of its actual repository needs
``git_root`` (``core.context.git_root_path`` / the registry's ``git_root``
offset) for the exclude call — ``exclude_ai_layer`` itself refuses a
``repo_root`` that is not the git top-level, so handing it the project's
own (possibly nested) root is not merely wrong, it is caught. The caller —
``drunken-init`` — resolves which is which; this module just takes both and
never confuses one for the other.
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .ai_layer import is_ai_layer_path
from .errors import ValidationError
from .exclude import ExcludeResult, exclude_ai_layer, resolve_info_exclude_path
from .registry import validate_project_id


class ConfigRepoProjectNotFoundError(ValidationError):
    """The config repo has no folder for the project id asked for."""

    code = "config_repo_project_not_found"


class ConfigRepoEscapeError(ValidationError):
    """A project id resolved outside the config repo it was joined onto."""

    code = "config_repo_escape"


class ProjectRootEscapeError(ValidationError):
    """A destination resolved outside the project root it was joined onto."""

    code = "project_root_escape"


class TrackedFileConflictError(ValidationError):
    """A destination the project's own git already tracks would be overwritten."""

    code = "tracked_file_conflict"


@dataclass(frozen=True)
class SkippedFile:
    """One file the copy left alone, and why."""

    relative: str
    reason: str


@dataclass(frozen=True)
class LayerCopyResult:
    """What :func:`copy_ai_layer_in` did, for a caller or a test to check."""

    project_root: Path
    git_root: Path
    project_folder: Path
    #: Repo-relative (forward-slashed) paths actually copied this run.
    copied: tuple[str, ...]
    #: Existing files left untouched, each with the reason.
    skipped: tuple[SkippedFile, ...]
    #: What the exclude writer (DG-440) did against ``git_root``.
    excluded: ExcludeResult


def _resolve_project_folder(config_repo: Path, project_id: str) -> Path:
    """*config_repo* / *project_id*, refusing anything that would escape.

    ``validate_project_id`` already rejects a ``project_id`` containing
    ``/`` or starting with ``.`` — which is every realistic ``../`` payload
    — but the containment check after resolving stays, as the same
    defence-in-depth the exclude writer applies to its own git root rather
    than trusting a single upstream check to never regress.
    """
    validate_project_id(project_id)

    config_repo_resolved = config_repo.resolve()
    project_folder = (config_repo_resolved / project_id).resolve()
    try:
        project_folder.relative_to(config_repo_resolved)
    except ValueError:
        raise ConfigRepoEscapeError(
            f"Project id {project_id!r} resolves outside the config repo at "
            f"{config_repo_resolved}.",
            remediation="Use the project's own registered id, not a path.",
        ) from None

    if not project_folder.is_dir():
        raise ConfigRepoProjectNotFoundError(
            f"No folder for project {project_id!r} in the config repo at "
            f"{config_repo_resolved} (looked for {project_folder}).",
            remediation=(
                f"Create {project_folder} in the config repo with this "
                "project's AI layer, or check --config-repo points at the "
                "right local clone."
            ),
        )
    return project_folder


def _layer_files(project_folder: Path) -> list[Path]:
    """Every regular file under *project_folder* that is on the AI-layer
    list, repo-relative to it. Filtered through
    :func:`core.ai_layer.is_ai_layer_path` — the one list — so a config repo
    folder holding something else (a README, a note-to-self) can never be
    copied in, even by accident.
    """
    files: list[Path] = []
    for path in sorted(project_folder.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(project_folder)
        if is_ai_layer_path(relative.as_posix()):
            files.append(relative)
    return files


def _git_tracks(git_root: Path, relative_to_git_root: str) -> bool:
    """Whether *git_root*'s own git already tracks *relative_to_git_root*."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative_to_git_root],
        cwd=git_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def copy_ai_layer_in(
    config_repo: Path,
    project_id: str,
    project_root: Path,
    git_root: Path,
    overwrite: bool = False,
) -> LayerCopyResult:
    """Copy *project_id*'s AI layer from *config_repo* into *project_root*.

    *git_root* is the repository's real top level — pass
    ``core.context.git_root_path()`` (or the registry's resolved
    equivalent), never *project_root* itself when they differ (see the
    module docstring). *project_root* is where the files actually land —
    where an agent reads them from while working.

    Refuses, writing nothing, when: *git_root* is not a git repository;
    *project_id* has no folder in *config_repo*; or any AI-layer file
    already there is tracked by *git_root*'s own git. An existing untracked
    file is skipped (reported in ``.skipped``) unless *overwrite* is set.
    The exclude writer always runs last, against *git_root*, so a clean
    ``git status`` is never a second manual step.
    """
    config_repo = Path(config_repo)
    project_root = Path(project_root)
    git_root = Path(git_root)

    # Confirms git_root is really a git working tree before anything is
    # written at all — reuses DG-440's own toplevel cross-check (handles a
    # worktree's `.git` file, a leaked GIT_DIR, etc.) rather than growing a
    # second implementation of "is this a git repo" here.
    resolve_info_exclude_path(git_root)
    git_root_resolved = git_root.resolve()
    project_root_resolved = project_root.resolve()

    project_folder = _resolve_project_folder(config_repo, project_id)
    layer_files = _layer_files(project_folder)

    # Phase 1 — validate only, nothing written yet: a destination that
    # already exists *and* is tracked by the project's own git aborts the
    # whole call, naming the path, before any file (including an
    # unrelated, non-conflicting one) is copied.
    for relative in layer_files:
        destination = (project_root_resolved / relative).resolve()
        if not destination.exists():
            continue
        try:
            rel_to_git_root = destination.relative_to(git_root_resolved).as_posix()
        except ValueError:
            raise ProjectRootEscapeError(
                f"{destination} is outside the git root {git_root_resolved}.",
                remediation=(
                    "Check the project's registered path and git_root offset."
                ),
            ) from None
        if _git_tracks(git_root_resolved, rel_to_git_root):
            raise TrackedFileConflictError(
                f"{destination} is already tracked by this project's own "
                "git; refusing to overwrite it.",
                remediation=(
                    f"Untrack it (git rm --cached {rel_to_git_root}) if it "
                    "should come from the config repo instead, or remove it "
                    "from the config repo's project folder if it should "
                    "stay as it is."
                ),
            )

    # Phase 2 — copy what phase 1 did not refuse.
    copied: list[str] = []
    skipped: list[SkippedFile] = []
    for relative in layer_files:
        source = project_folder / relative
        destination = (project_root_resolved / relative).resolve()
        try:
            destination.relative_to(project_root_resolved)
        except ValueError:
            raise ProjectRootEscapeError(
                f"{destination} would land outside the project root "
                f"{project_root_resolved}.",
                remediation="Check the AI-layer path for '..' segments.",
            ) from None

        if destination.exists() and not overwrite:
            identical = filecmp.cmp(source, destination, shallow=False)
            skipped.append(
                SkippedFile(
                    relative.as_posix(),
                    "already exists and matches the config repo"
                    if identical
                    else "already exists and differs from the config repo",
                )
            )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative.as_posix())

    excluded = exclude_ai_layer(git_root)

    return LayerCopyResult(
        project_root=project_root,
        git_root=git_root,
        project_folder=project_folder,
        copied=tuple(copied),
        skipped=tuple(skipped),
        excluded=excluded,
    )


__all__: Sequence[str] = (
    "ConfigRepoEscapeError",
    "ConfigRepoProjectNotFoundError",
    "LayerCopyResult",
    "ProjectRootEscapeError",
    "SkippedFile",
    "TrackedFileConflictError",
    "copy_ai_layer_in",
)
