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

``drunken-init``'s copy-in (DG-441, :mod:`core.layer_copy`) runs this after
every copy, from inside a context that can itself run inside a git hook —
where any number of ``GIT_*`` variables can be set in the environment and
point at whichever repository (or whichever index, object store, config or
namespace within one) invoked the hook. Every git subprocess this module
runs strips **every environment variable whose name starts with ``GIT_``**,
compared case-insensitively (:func:`git_subprocess_env`) — not a fixed
list of three. A fixed list was tried first and was wrong: a leaked
``GIT_INDEX_FILE`` pointing at an empty or alternate index made
``git ls-files`` answer "not tracked" for a file that was, in fact,
committed, with neither ``GIT_DIR`` nor ``GIT_WORK_TREE`` involved at all.
``GIT_CONFIG_COUNT``/``GIT_CONFIG_KEY_*``/``GIT_CONFIG_VALUE_*``,
``GIT_OBJECT_DIRECTORY``, ``GIT_ALTERNATE_OBJECT_DIRECTORIES`` and
``GIT_NAMESPACE`` are three more ways an inherited variable changes what
git answers without touching which repository it *resolves*, which is why
a strip list scoped to "variables that redirect repository resolution"
was the wrong shape of guard from the start — the rule is "every ``GIT_``
variable", full stop. ``os.environ`` is case-insensitive on Windows, so
the comparison upper-cases each key before checking the prefix, rather
than assuming the exact-case spelling this module happens to use
elsewhere. :func:`resolve_info_exclude_path` additionally cross-checks
that ``repo_root`` really is the working tree git resolved — not a
different repository reached only through an inherited variable, and not
a parent directory's repository reached by climbing past a `repo_root`
that is not itself a repository. :func:`run_git` (hardened the same way)
is public precisely so :mod:`core.layer_copy`'s own git calls — asking
whether a destination is already tracked, or already in ``HEAD`` — go
through the *same* stripped environment rather than growing a second,
unstripped implementation next to this one.

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
from typing import Any, Final, Optional, Sequence

from .ai_layer import AI_LAYER_BASENAMES, AI_LAYER_ROOT_DIRS, AI_LAYER_ROOT_FILES
from .errors import ValidationError

#: Written around the patterns this module owns, so a second run can tell
#: its own prior block apart from anything else the file holds and leave
#: everything else — including a pre-existing, hand-written block with a
#: different marker — untouched.
MARKER_START = "# >>> drunken-guild AI layer (DG-440) >>>"
MARKER_END = "# <<< drunken-guild AI layer (DG-440) <<<"

#: The prefix every stripped variable's name starts with, compared
#: case-insensitively. See the module docstring for why this is a rule
#: ("every `GIT_*` variable") rather than a fixed list of the three that
#: happen to redirect repository *resolution* — `GIT_INDEX_FILE` redirects
#: what `git ls-files` answers without touching resolution at all, and a
#: fixed list missed it.
_GIT_ENV_VAR_PREFIX = "GIT_"

#: The default per-call limit :func:`run_git` applies when a caller passes
#: no *timeout* of its own (DG-454). Every call site in this module, and
#: both of :mod:`core.layer_copy`'s tracked-file checks, went through
#: ``run_git`` with no timeout at all until DG-454 — a git waiting on a
#: lock, a credential prompt, or a slow network filesystem hung
#: ``drunken-init`` with no message, forever. 30 seconds matches
#: :mod:`core.doctor`'s own git calls (DG-451, a read-only diagnostic
#: against a repository it does not control) rather than inventing a
#: second number: long enough that a merely slow local checkout still
#: finishes, short enough that a caller gets a clear, fail-closed error
#: instead of an indefinite hang. A caller that genuinely needs a
#: different bound (:mod:`core.doctor` already does, for its own read-only
#: checks) still passes its own *timeout* explicitly; this only changes
#: what happens when none is given.
DEFAULT_GIT_TIMEOUT_SECONDS: Final[float] = 30.0

#: Overrides :data:`DEFAULT_GIT_TIMEOUT_SECONDS` when set to a positive
#: number of seconds (DG-454 review) — an operator whose checkout genuinely
#: needs longer than 30s (a large network filesystem, say) can say so
#: without editing source. Read fresh on every call needing the default
#: (:func:`_resolve_default_git_timeout`), not cached at import time, so a
#: test (or a caller) can change it between calls.
GIT_TIMEOUT_ENV_VAR: Final[str] = "DRUNKEN_GIT_TIMEOUT"

#: Set on every git subprocess this module runs, overriding whatever this
#: process inherited (or had stripped, since it also starts with ``GIT_``)
#: — never ``"1"``, the default a locally spawned git otherwise falls back
#: to in some configurations. A credential prompt is one more way a git
#: call can block past *timeout*'s "wait, then fail" into "wait, prompt an
#: unattended process's stdin, and fail anyway" — every caller of
#: :func:`run_git` already treats a non-zero exit (or a timeout) as
#: fail-closed, so making git refuse to prompt and exit immediately is
#: strictly better than letting it burn the whole timeout window asking a
#: question that no human is there to answer.
_GIT_TERMINAL_PROMPT_KEY = "GIT_TERMINAL_PROMPT"


class GitCommandError(ValidationError):
    """Base for every way :func:`run_git` can fail to answer at all —
    see its two concrete subclasses below.

    **Catch one of the two subclasses, never this base, unless "either
    reason is the same to me" is actually true for the caller.** DG-454
    review: :mod:`core.init`'s tracked-instruction-file refusal caught
    ``NotAGitRepositoryError`` to mean "nothing to protect here" (correct:
    a repository that does not exist cannot track anything) — and a prior
    version of this change made a timeout raise that *same* exception,
    which that catch then read the same way, so a hung git during the
    refusal's own check silently answered "nothing tracked" for a file
    that, in fact, was. A timeout is a question that went unanswered, not
    evidence the repository does not exist, so it is its own subclass
    (:class:`GitTimedOutError`) that a narrow ``except
    NotAGitRepositoryError`` does **not** catch — a caller that wants "ran
    at all, however it failed" opts into that explicitly, in writing, by
    naming both.
    """

    code = "git_command_failed"


class NotAGitRepositoryError(GitCommandError):
    """*repo_root* is not a git repository (or git itself is unavailable)."""

    code = "not_a_git_repository"


class GitTimedOutError(GitCommandError):
    """A git subprocess did not finish within its timeout.

    Deliberately not caught by anything written as ``except
    NotAGitRepositoryError`` — see :class:`GitCommandError` for why that
    matters. A caller that treats "not a repository" and "timed out" the
    same way names both explicitly.
    """

    code = "git_timed_out"


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


def git_subprocess_env() -> dict[str, str]:
    """A copy of the current environment with every ``GIT_*`` variable gone.

    Every key is compared upper-cased against ``_GIT_ENV_VAR_PREFIX`` — not
    exact-case — because ``os.environ`` is case-insensitive on Windows: a
    caller's process can have ``git_index_file`` (lower-case) set and git
    itself would still honour it there. See the module docstring for why
    this is a rule over every ``GIT_`` name rather than a fixed list of the
    few that redirect which *repository* resolution finds: that list missed
    ``GIT_INDEX_FILE``, which redirects what ``git ls-files`` reports about
    a repository without ever touching resolution.

    Everything else — ``PATH``, ``HOME``, ``SYSTEMROOT`` and so on — passes
    through unchanged: git (and the OS loader that finds it) still needs
    those, and this is not a general "run with nothing inherited" sandbox.

    Public so :func:`run_git` is the *only* way anything in this codebase
    invokes git for a repository-resolving command — never a second,
    unstripped ``subprocess.run(["git", ...])`` elsewhere that a leaked
    ``GIT_*`` variable could silently redirect.

    One ``GIT_*`` name is put back deliberately, after every other one is
    gone: ``GIT_TERMINAL_PROMPT=0`` (DG-454), so git fails fast instead of
    blocking on a credential prompt an unattended process can never answer.
    It is this module's own, not a passthrough of anything inherited —
    whatever this process had set (if anything) was already stripped by
    the comprehension above, the same as every other ``GIT_*`` name.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(_GIT_ENV_VAR_PREFIX)
    }
    env[_GIT_TERMINAL_PROMPT_KEY] = "0"
    return env


def _resolve_default_git_timeout() -> float:
    """:data:`DEFAULT_GIT_TIMEOUT_SECONDS`, unless :data:`GIT_TIMEOUT_ENV_VAR`
    names a valid override (DG-454 review): a positive number of seconds.

    Anything else — unset, not a number, zero, or negative — is ignored and
    falls back to the module default. An invalid override must never be
    read as "disable the bound entirely"; it means only "this particular
    value could not be used," the same safe direction :func:`run_git`'s own
    ``timeout=None`` already resolves in.

    Read fresh on every call that needs it (never cached at import time),
    so a caller — or a test — can change the environment between calls.
    """
    raw = os.environ.get(GIT_TIMEOUT_ENV_VAR)
    if raw is None:
        return DEFAULT_GIT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_GIT_TIMEOUT_SECONDS
    if value <= 0:
        return DEFAULT_GIT_TIMEOUT_SECONDS
    return value


def run_git(
    args: Sequence[str],
    repo_root: Path,
    *,
    text: bool = True,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess[Any]:
    """Run ``git`` with *args* in *repo_root*, env stripped (see above).

    Public — and the one hardened git caller every module in this
    codebase that needs to ask something of a project's own git should
    import, rather than opening a second ``subprocess.run(["git", ...])``
    that forgets the strip. :mod:`core.layer_copy` is the first such caller
    (DG-441): a tracked-file check that ran unstripped silently answered
    "not tracked" against an *unrelated* repository reached through a
    leaked ``GIT_DIR``/``GIT_WORK_TREE``, and overwrote a committed file.
    :mod:`core.doctor` (DG-451) is the second: its ``git ls-files -z`` read-
    only layering check made the same unstripped call.

    *text* defaults to ``True`` (``stdout``/``stderr`` as ``str``, matching
    every caller before DG-451) but can be set ``False`` for a caller that
    needs the raw bytes — ``git ls-files -z`` NUL-separates, and decoding
    that with ``text=True``'s universal-newline translation would mangle a
    path holding a literal ``\\r``, which plain ``str`` decoding with
    ``surrogateescape`` does not.

    *timeout* is the per-call limit in seconds. ``None`` (the default) does
    **not** mean "no limit" — it means "use
    :func:`_resolve_default_git_timeout`" (:data:`DEFAULT_GIT_TIMEOUT_SECONDS`,
    or the :data:`GIT_TIMEOUT_ENV_VAR` override) (DG-454): a caller that
    passes nothing at all still gets a bound, so a git waiting on a lock, a
    credential prompt, or a slow network filesystem cannot hang whatever
    called this forever. A caller that genuinely wants a different bound
    (:mod:`core.doctor` already does) passes its own *timeout* explicitly;
    nothing in this codebase currently needs an unbounded wait.

    A git failure (a non-zero exit) is *not* raised here — every existing
    caller reads ``returncode``/``stdout`` itself and decides what that
    means. An inability to run the process at all (no binary, no
    permission) raises :class:`NotAGitRepositoryError`; a timeout raises
    the *separate* :class:`GitTimedOutError` instead (DG-454 review) —
    deliberately not the same exception, so a caller written as ``except
    NotAGitRepositoryError`` to mean "there is nothing here to protect"
    cannot also, silently, read "git never got the chance to answer" the
    same way. Either way, a caller cannot forget that git never answered.
    """
    effective_timeout = _resolve_default_git_timeout() if timeout is None else timeout
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=text,
            check=False,
            env=git_subprocess_env(),
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitTimedOutError(
            f"git {' '.join(args)} in {repo_root} did not finish within "
            f"{effective_timeout}s and was killed rather than left to hang "
            "(a lock wait, a credential prompt, or a slow filesystem can "
            f"all cause this): {exc}",
            remediation=(
                "Check whether another git process holds a lock on "
                f"{repo_root}, whether a credential prompt is waiting, or "
                "whether the filesystem is unusually slow. If this "
                f"environment genuinely needs longer than {effective_timeout}s, "
                f"set {GIT_TIMEOUT_ENV_VAR} to a larger number of seconds; "
                "otherwise run this again."
            ),
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
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

    git_path_result = run_git(["rev-parse", "--git-path", "info/exclude"], repo_root)
    if git_path_result.returncode != 0:
        raise NotAGitRepositoryError(
            f"{repo_root} is not a git repository "
            f"(git rev-parse --git-path failed: {git_path_result.stderr.strip()}).",
            remediation=(
                "Run this inside a git clone or a git worktree, not a plain folder."
            ),
        )

    git_path: str = git_path_result.stdout.strip()
    if not git_path:
        raise NotAGitRepositoryError(
            f"git reported no path for info/exclude in {repo_root}.",
            remediation="Run this inside a git clone or a git worktree.",
        )

    toplevel_result = run_git(["rev-parse", "--show-toplevel"], repo_root)
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
