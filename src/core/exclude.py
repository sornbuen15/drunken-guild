"""Hides a project's copied-in AI layer from its own git — DG-440 (REQ-019,
REQ-020).

REQ-019/020 copy a project's AI layer in from the config repo and keep the
project's own git from tracking it, through ``.git/info/exclude`` —
deliberately not ``.gitignore``, which would itself be a tracked file and
recreate the thing it is meant to hide. This module is the writer. It reads
its paths from ``core.ai_layer`` (DG-437) alone: a second list here is
exactly the drift REQ-019's own history (`skills/git-workflow` diverging to
73 lines against 196) exists to warn against.

**Blocked on Spike DG-432** until that spike has a recorded result: whether
an excluded ``CLAUDE.md``/``.claude/settings.json`` still loads in Claude
Code. The recorded result (DG-432) is yes, so building on
``.git/info/exclude`` is allowed.

Nothing here is wired into ``drunken-init`` yet — that wiring is DG-441,
which shares ``src/core/init.py`` with two sibling Tasks and is kept out of
this change on purpose. DG-441 runs this from inside ``drunken-init``, which
can itself run inside a git hook — where ``GIT_DIR``, ``GIT_COMMON_DIR`` and
``GIT_WORK_TREE`` are set in the environment and point at whichever
repository invoked the hook. Every git subprocess this module runs strips
those three first (:func:`_git_subprocess_env`), and
:func:`resolve_info_exclude_path` independently cross-checks that
``repo_root`` really is the working tree git resolved — not a different
repository reached only through an inherited variable, and not a parent
directory's repository reached by climbing past a `repo_root` that is not
itself a repository.

The write itself is a single ``open(..., "a")`` append, not a
read-modify-write replace — there is no temp file and no rename, so a
process killed mid-write can leave a start marker with no matching end
marker. Rather than silently treating that as "nothing to add yet" and
appending a second, complete block next to the broken one,
:func:`exclude_ai_layer` treats a mismatched marker count as corruption and
refuses, naming the file, so a human fixes it by hand once instead of the
file slowly accumulating duplicate blocks.

A pre-existing ``info/exclude`` saved with CRLF line endings keeps its own
line endings; only the appended block is LF-only. git has been observed
(on Windows, by a reviewer, with ``git status`` and ``git check-ignore``) to
tolerate the mix. That has not been observed on Linux — say so rather than
assuming the Windows result travels.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .ai_layer import AI_LAYER_BASENAMES, AI_LAYER_ROOT_DIRS, AI_LAYER_ROOT_FILES
from .errors import ValidationError

#: Written around the patterns this module owns, so a second run can tell
#: its own prior block apart from anything else the file holds and leave
#: everything else — including a pre-existing, hand-written block with a
#: different marker — untouched.
MARKER_START = "# >>> drunken-guild AI layer (DG-440) >>>"
MARKER_END = "# <<< drunken-guild AI layer (DG-440) <<<"

#: Stripped from every git subprocess this module runs. A caller's own
#: process — `drunken-init` running inside a git hook, for instance — may
#: have one of these set, pointing `git rev-parse` at a *different*
#: repository than the `cwd` it is given. `GIT_INDEX_FILE`,
#: `GIT_OBJECT_DIRECTORY` and `GIT_CEILING_DIRECTORIES` are not in this set:
#: none of them redirect which repository `--git-path`/`--show-toplevel`
#: resolve against the way these three do.
_GIT_ENV_VARS_TO_STRIP: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
)


class NotAGitRepositoryError(ValidationError):
    """*repo_root* is not a git repository (or git itself is unavailable)."""

    code = "not_a_git_repository"


class MalformedExcludeBlockError(ValidationError):
    """The exclude file already has an unmatched marker from this module."""

    code = "malformed_exclude_block"


@dataclass(frozen=True)
class ExcludeResult:
    """What :func:`exclude_ai_layer` did, for a caller or a test to check."""

    #: The ``info/exclude`` file actually written — the *repository's* own,
    #: resolved through git itself rather than assumed, so this is correct
    #: for a plain clone and for a `git worktree` alike.
    exclude_path: Path
    #: Patterns appended this run. Empty on a no-op second run.
    added: tuple[str, ...]


def default_ai_layer_patterns() -> tuple[str, ...]:
    """The ``info/exclude`` patterns for ``core.ai_layer``'s one list.

    Built from the three tuples in :mod:`core.ai_layer` alone — this
    function is the *only* place that turns that list into gitignore syntax,
    so the exclude writer cannot drift from what ``is_ai_layer_path`` already
    recognises.

    * ``AI_LAYER_BASENAMES`` matches at any depth, the same way
      ``is_ai_layer_path`` does: a leading ``**/`` in gitignore syntax
      matches a name in every directory, the repository root included.
    * ``AI_LAYER_ROOT_FILES`` and ``AI_LAYER_ROOT_DIRS`` are root-only, so
      each pattern is anchored with a leading ``/``; directories also carry
      a trailing ``/`` so a same-named file at the root is never matched by
      accident.
    """
    patterns: list[str] = []
    for name in AI_LAYER_BASENAMES:
        patterns.append(f"**/{name}")
    for name in AI_LAYER_ROOT_FILES:
        patterns.append(f"/{name}")
    for name in AI_LAYER_ROOT_DIRS:
        patterns.append(f"/{name}/")
    return tuple(patterns)


def _git_subprocess_env() -> dict[str, str]:
    """A copy of the current environment with the git-redirecting vars gone.

    See ``_GIT_ENV_VARS_TO_STRIP`` for which, and the module docstring for
    why: inherited from the calling process rather than passed explicitly,
    so they are exactly the kind of implicit, unnamed configuration this
    codebase's own rules (``.claude/rules/python.md``) warn against trusting.
    """
    env = dict(os.environ)
    for var in _GIT_ENV_VARS_TO_STRIP:
        env.pop(var, None)
    return env


def _run_git(args: Sequence[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            env=_git_subprocess_env(),
        )
    except OSError as exc:
        raise NotAGitRepositoryError(
            f"Could not run git ({' '.join(args)}) for {repo_root}: {exc}",
            remediation="Install git and make sure it is on PATH.",
        ) from exc


def _validate_marker_lines(existing_text: str, exclude_path: Path) -> None:
    """Refuse a marker block that is not well-formed, line by line.

    A marker is recognised only by *exact* line equality after stripping
    surrounding whitespace (``line.strip() == MARKER_START``) — not by
    counting substring occurrences across the whole file. A human comment
    that merely *mentions* the marker text (``# see also <marker>``) is not
    a marker and must never trip this check; counting substrings would have
    treated it as one.

    Equal start/end *counts* are not enough either: an END appearing before
    any open START is just as malformed as a dangling, unclosed START, even
    though the counts match. This walks the file as open/closed state and
    catches all three: an END with no open START, a START while one is
    already open, and an unclosed START at end of file. Two or more
    *complete* pairs are fine and change nothing here.
    """
    open_start_line: int | None = None
    for line_number, raw_line in enumerate(existing_text.splitlines(), start=1):
        line = raw_line.strip()
        if line == MARKER_START:
            if open_start_line is not None:
                raise MalformedExcludeBlockError(
                    f"{exclude_path}:{line_number}: a start marker opens "
                    f"here while the one at line {open_start_line} is "
                    "still unclosed.",
                    remediation=(
                        f"Open {exclude_path} and fix the marker block by "
                        "hand, then run this again."
                    ),
                )
            open_start_line = line_number
        elif line == MARKER_END:
            if open_start_line is None:
                raise MalformedExcludeBlockError(
                    f"{exclude_path}:{line_number}: an end marker appears "
                    "here with no open start marker before it.",
                    remediation=(
                        f"Open {exclude_path} and fix the marker block by "
                        "hand, then run this again."
                    ),
                )
            open_start_line = None

    if open_start_line is not None:
        raise MalformedExcludeBlockError(
            f"{exclude_path}:{open_start_line}: a start marker here is "
            "never closed by a matching end marker — a previous write may "
            "have been interrupted.",
            remediation=(
                f"Open {exclude_path} and fix the marker block by hand, "
                "then run this again."
            ),
        )


def resolve_info_exclude_path(repo_root: Path) -> Path:
    """The ``info/exclude`` file git itself would read for *repo_root*.

    Resolved with ``git rev-parse --git-path info/exclude`` rather than
    assumed as ``<repo_root>/.git/info/exclude``: in a `git worktree`,
    ``.git`` is a *file* pointing at ``<main repo>/.git/worktrees/<name>``,
    and ``info/exclude`` is not even there — it is shared repository state
    that lives in the common dir. ``git rev-parse --git-path`` already knows
    this difference; assuming ``.git`` is a directory does not.

    Run with ``GIT_DIR``/``GIT_COMMON_DIR``/``GIT_WORK_TREE`` stripped from
    the environment (see the module docstring), and cross-checked against
    ``git rev-parse --show-toplevel`` run the same way: if git's own idea of
    *repo_root*'s working-tree root is not ``repo_root`` itself, this refuses
    rather than silently resolving into whatever repository git actually
    found — a parent directory's, if one climbed past a `repo_root` that is
    not a repository root on its own.
    """
    repo_root = Path(repo_root)

    git_path_result = _run_git(["rev-parse", "--git-path", "info/exclude"], repo_root)
    if git_path_result.returncode != 0:
        raise NotAGitRepositoryError(
            f"{repo_root} is not a git repository "
            f"(git rev-parse --git-path failed: {git_path_result.stderr.strip()}).",
            remediation=(
                "Run this inside a git clone or a git worktree, not a plain folder."
            ),
        )

    git_path = git_path_result.stdout.strip()
    if not git_path:
        raise NotAGitRepositoryError(
            f"git reported no path for info/exclude in {repo_root}.",
            remediation="Run this inside a git clone or a git worktree.",
        )

    toplevel_result = _run_git(["rev-parse", "--show-toplevel"], repo_root)
    if toplevel_result.returncode != 0 or not toplevel_result.stdout.strip():
        raise NotAGitRepositoryError(
            f"{repo_root} is not recognised as a git working tree "
            f"(git rev-parse --show-toplevel failed: "
            f"{toplevel_result.stderr.strip()}).",
            remediation=(
                "Run this inside a git clone or a git worktree, not a plain folder."
            ),
        )

    reported_toplevel = Path(toplevel_result.stdout.strip()).resolve()
    if reported_toplevel != repo_root.resolve():
        raise NotAGitRepositoryError(
            f"{repo_root} is not its own git working-tree root — git "
            f"resolved it to {reported_toplevel} instead, which would mean "
            "writing into a different repository's info/exclude.",
            remediation=(
                "Run this inside the actual repository or worktree root, and "
                "check GIT_DIR/GIT_COMMON_DIR/GIT_WORK_TREE are not set to "
                "point somewhere else."
            ),
        )

    return (repo_root / git_path).resolve()


def exclude_ai_layer(
    repo_root: Path, patterns: Sequence[str] | None = None
) -> ExcludeResult:
    """Append missing AI-layer patterns to *repo_root*'s ``info/exclude``.

    Idempotent: a pattern already present anywhere in the file — inside this
    module's own marker block or not — is never appended again, so running
    this twice leaves exactly the one marker block the first run wrote and
    changes nothing else. Existing content is preserved byte for byte, a
    missing trailing newline is added before the new block rather than
    gluing onto the last existing line, and ``info/`` and the file itself
    are created if absent.

    *patterns* defaults to :func:`default_ai_layer_patterns` — the one list
    in :mod:`core.ai_layer` turned into gitignore syntax. A caller passing
    its own sequence is only for a test; nothing in this codebase should
    ever need a second list.

    **Pass the git root, not the project root.** A registered project may
    have its checkout at a subdirectory of the actual repository (see
    ``core.context.git_root_path`` / ``Context.git_root_path`` and the
    ``git_root`` registry field) — a monorepo, for instance. *repo_root*
    here must be that git root, not the project's own subdirectory:
    :func:`resolve_info_exclude_path` refuses a non-root subdirectory
    outright (its ``git rev-parse --show-toplevel`` will not equal it), so a
    caller handing this the project root of a project nested inside a
    larger repository gets a clear error rather than a wrong file.
    """
    resolved_patterns = (
        tuple(patterns) if patterns is not None else default_ai_layer_patterns()
    )
    exclude_path = resolve_info_exclude_path(Path(repo_root))

    exclude_path.parent.mkdir(parents=True, exist_ok=True)

    existing_text = (
        exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    )

    _validate_marker_lines(existing_text, exclude_path)

    existing_lines = set(existing_text.splitlines())

    missing = tuple(p for p in resolved_patterns if p not in existing_lines)
    if not missing:
        return ExcludeResult(exclude_path=exclude_path, added=())

    block = "\n".join((MARKER_START, *missing, MARKER_END))
    needs_leading_newline = bool(existing_text) and not existing_text.endswith("\n")
    addition = ("\n" if needs_leading_newline else "") + block + "\n"

    with exclude_path.open("a", encoding="utf-8") as handle:
        handle.write(addition)

    return ExcludeResult(exclude_path=exclude_path, added=missing)
