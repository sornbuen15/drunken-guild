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
out) a project checkout that depends on it. A config-repo entry that is
itself a symlink (a file, or a whole directory) is never followed while
walking the project's folder (:func:`_layer_files` does its own walk with
``os.DirEntry.is_symlink()`` rather than a recursive glob that might follow
one) — a symlink there could point anywhere on disk, and copying through
it, or recursing into it, would read content this call was never told to
trust. The destination side carries the matching rule: a destination path
that is *itself* already a symlink — dangling or not, inside the project
root or escaping it — is refused outright, never written through.

**Nothing is written until every file has been checked.** A destination
whose path *the project's own git already tracks* aborts the whole call
before a single byte is copied, naming the path — overwriting a committed
file through this path would be a silent, surprising edit to
version-controlled content. "Tracked" means **staged with real content,
or present in ``HEAD``** (:func:`_has_staged_content` and :func:`_in_head`
respectively) — either one alone is enough to refuse, and each closes a
*different* gap the other cannot: deleting either check from
:func:`_is_tracked` and keeping only the other still leaves a test that
exercises nothing but ``git rm --cached`` green, because that one state
happens to be caught by both. The state that is actually unique to each
check is what matters here, not a shared example.
:func:`_has_staged_content` is the only one of the two that catches a
brand-new path a plain ``git add`` staged but never committed — ``HEAD``
has no entry for it at all, so :func:`_in_head` alone would wrongly
answer "not tracked". :func:`_in_head` is the only one of the two that
catches a committed file deleted from the working tree *without* that
deletion ever being staged — the index still matches ``HEAD`` exactly, so
``git diff --cached`` reports nothing staged, and
:func:`_has_staged_content` alone would wrongly answer "not tracked". A
staged ``git rm --cached`` (not yet committed) is caught by *both*: the
staged removal shows up in ``git diff --cached``
(:func:`_has_staged_content`), and the blob is still in ``HEAD`` until the
removal itself is committed (:func:`_in_head`) — so it does not, on its
own, tell a maintainer which check is the one actually needed. This is
also checked by path, not by whether the destination currently exists on
disk: copying over either gap would silently turn a ``git status`` clean
worktree into one reporting a modified file. Only this tracked case is an
absolute refusal, with or without ``overwrite=True``.

**The tracked check is case-insensitive too (DG-453).** git's own index is
case-sensitive; on a case-insensitive filesystem (NTFS, APFS by default) a
project that tracks ``agents.md`` and an AI-layer destination spelled
``AGENTS.md`` are the very same on-disk file, even though an exact-case
``git diff --cached``/``git cat-file`` lookup for ``AGENTS.md`` answers "not
tracked." :func:`_is_tracked` therefore also compares every tracked path
(``HEAD`` and staged-with-content) against the destination case-foldedly,
by listing paths rather than resolving anything on disk — a committed file
already deleted from the working tree has nothing on disk to resolve, and
still must refuse. This is deliberately a plain string comparison, not a
check of what the current filesystem actually does with the two spellings:
refusing a pair of names that would, in fact, have been two distinct files
on a case-sensitive filesystem is the safe direction to be wrong in.

One thing that is deliberately *not* refused: ``git add -N`` (intent to
add) stages a placeholder for a brand-new path with no real content yet —
``git diff --cached`` never lists it, unlike an ordinary staged addition,
because there is nothing committed or staged there to protect. See
:func:`_has_staged_content`.

An existing file that is neither in the index (with real content) nor in
``HEAD`` is a softer case: skipped and reported (with whether its content
already matches the config repo), unless the caller passes
``overwrite=True``.

**Both tracked-file checks fail closed.** Whether a path is tracked is
decided by :func:`core.exclude.run_git` — git with every ``GIT_*``
environment variable stripped, the same hardening DG-440 already applies,
reused rather than duplicated: a second, unstripped implementation here
once answered "not tracked" against an *unrelated* repository reached
through a leaked ``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE``, and
overwrote a committed ``CLAUDE.md``. Each of the two checks (index,
``HEAD``) reports a small, known set of outcomes by exit code; anything
outside that set (git missing, a timeout, a corrupted repository) is
treated as "could not determine," which raises rather than silently
falling through to "not tracked."

**The exclude entries are written before any file is copied, not after.**
A call that copies files first and excludes them afterward can leave
copied, untracked files behind with a dirty ``git status`` if the exclude
write then fails (a corrupted marker block, say) — exactly the state this
whole mechanism exists to prevent. :func:`exclude_ai_layer` already
validates the exclude file and the git root on its own, so running it
*before* the copy loop means a validation failure there still leaves the
project tree byte-identical to before the call, the same guarantee the
tracked-file checks give. If a copy then fails partway through (a real
I/O error — disk full, a permission problem), the files already copied by
that point are reported by name rather than lost in a bare exception, and
re-running after fixing the underlying problem is idempotent: an
already-copied, now-identical file is skipped as "unchanged," not
re-copied from scratch.

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
offset — a plain relative path, ``..`` included, see that field's own
docs) for the exclude call — ``exclude_ai_layer`` itself refuses a
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
from typing import Callable, Sequence

from .ai_layer import is_ai_layer_path
from .content_scan import (
    ALLOWLIST_FILENAME,
    apply_allowlist,
    parse_allowlist,
    scan_allowlist_file,
    scan_file,
)
from .errors import DrunkenError, ValidationError
from .exclude import ExcludeResult, exclude_ai_layer, resolve_info_exclude_path, run_git
from .registry import validate_project_id


class ConfigRepoProjectNotFoundError(ValidationError):
    """The config repo has no folder for the project id asked for."""

    code = "config_repo_project_not_found"


class ConfigRepoEscapeError(ValidationError):
    """A project id resolved outside the config repo it was joined onto."""

    code = "config_repo_escape"


class ProjectRootEscapeError(ValidationError):
    """A destination is unsafe: outside a root it was joined onto, or a
    symlink this refuses to write through."""

    code = "project_root_escape"


class TrackedFileConflictError(ValidationError):
    """A destination the project's own git already tracks would be overwritten."""

    code = "tracked_file_conflict"


class ContentScanRefusedError(ValidationError):
    """A credential-, identity- or path-shaped value sat in the config
    repo's own AI-layer content (DG-443) — refused before a single byte is
    copied. Every finding across every file is named at once; see
    :mod:`core.content_scan`.
    """

    code = "content_scan_refused"


class GitTrackedCheckFailedError(ValidationError):
    """git could not say whether a path is tracked (not: "git said no")."""

    code = "git_tracked_check_failed"


class PartialCopyError(DrunkenError):
    """A real I/O failure stopped the copy partway through.

    Not a :class:`ValidationError`: nothing about the *call* was invalid —
    every check passed — a filesystem operation itself failed (disk full,
    a permission problem) after some files were already written. The files
    copied before the failure are named, both in the message and in
    ``details``, so a caller is never left guessing what state the project
    tree is in.
    """

    code = "partial_copy"


@dataclass(frozen=True)
class SkippedFile:
    """One file the copy left alone, and why.

    ``identical`` is a real field, not left for a caller to re-derive by
    matching substrings in ``reason`` — the wording of ``reason`` is for a
    human to read, and must stay free to change without silently breaking
    something that decided an exit code by parsing it.
    """

    relative: str
    reason: str
    identical: bool


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


def ai_layer_files_under(root: Path) -> list[Path]:
    """Every regular file under *root* that is on the AI-layer list,
    relative to *root*.

    A manual stack-based walk, not ``Path.rglob`` — deliberately: this must
    never descend into a symlinked directory (a config repo's ``.claude``
    could be a symlink to anywhere on disk) and never pick up a symlinked
    file, and relying on whichever symlink-following default a given
    Python version's ``glob``/``rglob`` happens to ship with is exactly the
    kind of implicit behaviour this checks for itself instead. Filtered
    through :func:`core.ai_layer.is_ai_layer_path` — the one list — so a
    folder holding something else (a README, a note-to-self) can never be
    picked up, even by accident.

    Public (DG-443): the exact same walk :mod:`core.doctor` needs to scan a
    project's *already-copied*, on-disk AI-layer files read-only — reused
    rather than reimplemented, so "never follow a symlink while walking a
    project's AI layer" has one definition, not two that could drift. This
    also means the walk — and so the content scan — is identical for the
    copy path and doctor's re-scan: neither can be blind to something the
    other would catch.

    **Never descends into a nested repository (DG-443 review).** Every
    subdirectory other than *root* itself that holds its own real git
    marker (see :func:`_is_real_git_marker`) is a separate repository's
    boundary, not more of this one's tree, and is skipped the same way a
    symlink already is. This was found the hard way:
    :data:`core.ai_layer.AI_LAYER_ROOT_DIRS` walks ``.claude`` to any
    depth, and Claude Code's own ``git worktree`` feature keeps every
    active worktree *inside* a project's ``.claude/worktrees/`` — each one
    a full, independent checkout with its own dependency tree. Before this
    guard, calling this against a real, long-lived project (not a config
    repo's small, author-controlled folder, the only caller this walk had
    until doctor's read-only check, DG-443) walked every worktree's entire
    ``node_modules``/``vendor`` tree too, multiplying a few thousand files
    into roughly a million and turning a diagnostic command into a
    multi-minute hang. Nothing about *what counts as AI-layer content*
    changes — only where the walk itself is willing to still be looking.

    **The marker must be a real one, not merely named ``.git`` (DG-443
    review round 2).** An earlier version of this guard skipped *any*
    directory entry named ``.git`` at all — directory or plain file,
    content never inspected. That is exactly backwards for a walk built to
    catch a leaked secret: a plain text file someone happened to name
    ``.git`` (not a repository marker at all) would have hidden everything
    beneath it from both the copy-in scan *and* doctor's re-scan, with no
    error, no finding, nothing. :func:`_is_real_git_marker` instead reads
    the entry — a directory only counts if it holds a ``HEAD`` file (what
    every real ``.git`` directory has), a file only counts if its first
    line starts with ``gitdir:`` (an ordinary git worktree pointer) —
    before this walk trusts it as a boundary.
    """
    files: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_symlink():
                # Never followed, file or directory: see the docstring.
                continue
            if entry.is_dir():
                if _is_real_git_marker(entry / ".git"):
                    # A nested repository (or worktree) boundary: see the
                    # docstring. `entry` is always a descendant discovered
                    # through `iterdir()`, never *root* itself (root is
                    # only ever pushed directly, never rediscovered this
                    # way), so this never mistakes root's own `.git` for a
                    # nested one.
                    continue
                stack.append(entry)
                continue
            if entry.is_file():
                relative = entry.relative_to(root)
                if is_ai_layer_path(relative.as_posix()):
                    files.append(relative)
    return sorted(files)


def _is_real_git_marker(candidate: Path) -> bool:
    """Whether *candidate* (a ``.git`` entry found while walking) is an
    actual git repository marker, not merely a file or directory that
    happens to be named ``.git`` — see :func:`ai_layer_files_under`'s
    docstring for why this distinction matters.

    A directory: real only if it holds a ``HEAD`` file, which every git
    repository's own ``.git`` directory has (the loose or packed object
    store, the index and the rest can legitimately be absent — a fresh
    ``git init`` with nothing committed yet still has ``HEAD``, before a
    single object exists). A file: real only if its first line starts
    with ``gitdir:`` — the one-line pointer format `git worktree` writes,
    and the only shape a real ``.git`` is ever a plain file instead of a
    directory. Anything else — a directory with no ``HEAD``, a file with
    different content, or neither existing at all — is not a marker, and
    this walk keeps going through it.
    """
    if candidate.is_dir():
        return (candidate / "HEAD").is_file()
    if candidate.is_file():
        try:
            with candidate.open("r", encoding="utf-8", errors="replace") as handle:
                first_line = handle.readline()
        except OSError:
            return False
        return first_line.startswith("gitdir:")
    return False


#: Kept as the name every call site in this module already used before
#: DG-443 made the walk reusable from :mod:`core.doctor` too.
_layer_files = ai_layer_files_under


def _read_allowlist(project_folder: Path) -> frozenset[tuple[str, str, str]]:
    """The config repo project folder's own `.drunken-scan-allow`, parsed —
    empty when there is none. Never part of :func:`ai_layer_files_under`'s
    result: it is not on :mod:`core.ai_layer`'s list, so it is never copied
    into a project, by construction, not by a special case here.
    """
    allowlist_path = project_folder / ALLOWLIST_FILENAME
    if not allowlist_path.is_file():
        return frozenset()
    text = allowlist_path.read_text(encoding="utf-8-sig")
    return parse_allowlist(text, source_name=str(allowlist_path))


def _scan_layer_files(project_folder: Path, layer_files: Sequence[Path]) -> None:
    """Scan every AI-layer source file's own content, and the allowlist
    file's own content, raising one :class:`ContentScanRefusedError` naming
    every finding across every file — or nothing, before any write.

    DG-443: run from inside the config-repo validation phase, strictly
    before the exclude write or any copy — the same "nothing written until
    every file has been checked" guarantee the tracked-file check already
    gives, extended to a file's *content* rather than only its path.
    """
    allow = _read_allowlist(project_folder)

    all_findings = []
    for relative in layer_files:
        findings = scan_file(project_folder / relative, relative.as_posix())
        all_findings.extend(apply_allowlist(findings, allow))

    allowlist_path = project_folder / ALLOWLIST_FILENAME
    if allowlist_path.is_file():
        allowlist_findings = scan_allowlist_file(allowlist_path)
        all_findings.extend(apply_allowlist(allowlist_findings, allow))

    if all_findings:
        detail = "; ".join(finding.describe() for finding in all_findings)
        raise ContentScanRefusedError(
            f"{len(all_findings)} finding(s) in the config repo's own "
            f"content, refusing before any write: {detail}",
            remediation=(
                "Replace the value with a reference (env://, file://, "
                "op://, keyring://), remove it, or add an exact-text entry "
                f"to {ALLOWLIST_FILENAME} naming why it is safe."
            ),
        )


def _has_staged_content(git_root: Path, relative_to_git_root: str) -> bool:
    """Whether *relative_to_git_root* has real staged content ahead of
    ``HEAD`` — deliberately **not** ``git ls-files``, which lists an
    intent-to-add placeholder (``git add -N``) exactly as if it were an
    ordinary tracked file even though it has no real content at all.
    ``git diff --cached --name-only`` draws that distinction on its own
    (verified empirically: an intent-to-add path never appears in its
    output, an ordinary staged addition always does), and does so whether
    or not ``HEAD`` exists yet — it diffs against the empty tree for a
    repository with no commits, no special-casing needed here for that.

    Fails closed: this diff is not asked to signal "changed" via its exit
    code (no ``--exit-code``), so exit 0 is the only documented outcome;
    anything else is "git could not say."
    """
    result = run_git(
        ["diff", "--cached", "--name-only", "--", relative_to_git_root], git_root
    )
    if result.returncode != 0:
        raise GitTrackedCheckFailedError(
            f"git could not determine whether {relative_to_git_root!r} has "
            f"staged content in {git_root} (exit {result.returncode}): "
            f"{result.stderr.strip()}",
            remediation=(
                "Check git is installed, on PATH, and that this "
                "repository's index is not corrupted."
            ),
        )
    return bool(result.stdout.strip())


def _has_head(git_root: Path) -> bool:
    """Whether *git_root* has at least one commit — an "unborn" ``HEAD``
    (a fresh ``git init`` with nothing committed yet) answers no, cleanly,
    by design of ``--verify -q``: exit 0 means ``HEAD`` resolves, exit 1
    means it does not. Checked before :func:`_in_head` asks about any one
    path, rather than inferring "no commits yet" from parsing a git error
    message, which is not a stable contract across versions or locales.
    """
    result = run_git(["rev-parse", "--verify", "-q", "HEAD"], git_root)
    if result.returncode in (0, 1):
        return result.returncode == 0
    raise GitTrackedCheckFailedError(
        f"git could not determine whether {git_root} has a commit yet "
        f"(exit {result.returncode}): {result.stderr.strip()}",
        remediation="Check git is installed and the repository is not corrupted.",
    )


def _in_head(git_root: Path, relative_to_git_root: str) -> bool:
    """Whether *relative_to_git_root* exists in *git_root*'s ``HEAD`` —
    the only one of these two checks that catches a committed file deleted
    from the working tree *without* that deletion ever being staged: the
    index still matches ``HEAD`` exactly in that state, so ``git diff
    --cached`` reports nothing staged at all, and only asking ``HEAD``
    directly, here, still finds the path tracked. A staged ``git rm
    --cached`` (not yet committed) is caught by *both* this and
    :func:`_has_staged_content` — the staged removal shows up in ``git
    diff --cached``, and the blob is still in ``HEAD`` until the removal
    itself is committed — so that state alone does not tell the two
    checks apart.

    No ``--`` pathspec separator is needed here, unlike
    :func:`_has_staged_content`'s ``git diff`` call: *relative_to_git_root*
    is embedded inside the single ``HEAD:<path>`` object-spec argument,
    never passed as its own positional argument that a leading ``-`` could
    be misread as an option for.

    ``git cat-file -e HEAD:<path>`` exits 128 for *two* different reasons
    with different messages — "path does not exist in 'HEAD'" and (on an
    unborn ``HEAD``) "not a valid object name" — and this never needs to
    tell them apart by parsing either one: :func:`_has_head` answers "no
    commits yet" first, on its own, so cat-file is only ever asked about a
    ``HEAD`` already known to exist. Once that is established, exit 128
    unambiguously means "not in HEAD," and anything other than 0 or 128 is
    "could not determine" — fails closed rather than reading an unexpected
    code as "not present."
    """
    if not _has_head(git_root):
        return False

    result = run_git(["cat-file", "-e", f"HEAD:{relative_to_git_root}"], git_root)
    if result.returncode == 0:
        return True
    if result.returncode == 128:
        return False
    raise GitTrackedCheckFailedError(
        f"git could not determine whether {relative_to_git_root!r} is in "
        f"HEAD at {git_root} (exit {result.returncode}): "
        f"{result.stderr.strip()}",
        remediation="Check git is installed and this repository's HEAD is not corrupted.",
    )


def _decode_or_raise(
    run: Callable[[], subprocess.CompletedProcess[str]],
    *,
    git_root: Path,
    what: str,
) -> subprocess.CompletedProcess[str]:
    """Run *run* (a no-arg call to :func:`core.exclude.run_git`), turning a
    raw ``UnicodeDecodeError`` into this module's own
    :class:`GitTrackedCheckFailedError` instead of letting it escape bare.

    ``run_git`` always runs git with ``text=True`` (no keyword to ask for
    raw bytes instead — the one that would add it, in a sibling PR, is not
    merged), so a path byte sequence ``-z`` kept intact but that the
    platform's default encoding cannot decode under ``errors="strict"``
    raises *inside* ``subprocess.run`` itself, before this module ever sees
    a ``CompletedProcess`` to inspect an exit code on. This cannot decode
    such a name correctly without editing ``core.exclude`` (out of scope
    here — DG-355 owns that module); the best available fix on this side
    is to fail closed with a named, typed error instead of a bare
    ``UnicodeDecodeError`` a caller was never told to expect from this
    module.
    """
    try:
        return run()
    except UnicodeDecodeError as exc:
        raise GitTrackedCheckFailedError(
            f"git listed a path while checking {what} in {git_root} that "
            f"could not be decoded as text ({exc}); core.exclude.run_git "
            "has no raw-bytes mode to fall back to.",
            remediation=(
                "Check git is installed and that the paths in this "
                "repository's index/HEAD are valid text in the system's "
                "default encoding."
            ),
        ) from exc


def _all_head_paths(git_root: Path) -> frozenset[str]:
    """Every path in *git_root*'s own ``HEAD`` tree, repo-relative — the
    same "committed" half of :func:`_is_tracked` as :func:`_in_head`, but
    listing every path at once instead of asking about one. Used only by
    :func:`_tracked_paths_casefold`; the exact-case, single-path checks
    above remain the primary refusal and are tried first.

    An unborn ``HEAD`` has nothing committed at all, checked first via
    :func:`_has_head` the same way :func:`_in_head` does, rather than
    reading ``git ls-tree``'s "fatal: Not a valid object name HEAD" (exit
    128) as "empty" — a locale-dependent message this never needs to
    parse.
    """
    if not _has_head(git_root):
        return frozenset()
    result = _decode_or_raise(
        lambda: run_git(["ls-tree", "-r", "--name-only", "-z", "HEAD"], git_root),
        git_root=git_root,
        what="HEAD's tracked paths",
    )
    if result.returncode != 0:
        raise GitTrackedCheckFailedError(
            f"git could not list HEAD's tracked paths in {git_root} "
            f"(exit {result.returncode}): {result.stderr.strip()}",
            remediation="Check git is installed and this repository's HEAD is not corrupted.",
        )
    return frozenset(path for path in result.stdout.split("\x00") if path)


def _all_staged_content_paths(git_root: Path) -> frozenset[str]:
    """Every path with real staged content ahead of ``HEAD`` — the same
    "staged" half of :func:`_is_tracked` as :func:`_has_staged_content`,
    but listing every path at once instead of asking about one.

    Deliberately the same ``git diff --cached`` call, just without a
    pathspec — **not** ``git ls-files``, which lists an intent-to-add
    placeholder (``git add -N``) exactly as if it had real content (see
    :func:`_has_staged_content`). Using it here would make a brand-new,
    content-free intent-to-add path refuse a case-different AI-layer path
    too, which is not tracked by any definition this module otherwise
    uses.
    """
    result = _decode_or_raise(
        lambda: run_git(["diff", "--cached", "--name-only", "-z"], git_root),
        git_root=git_root,
        what="staged content",
    )
    if result.returncode != 0:
        raise GitTrackedCheckFailedError(
            f"git could not list staged content in {git_root} "
            f"(exit {result.returncode}): {result.stderr.strip()}",
            remediation=(
                "Check git is installed, on PATH, and that this "
                "repository's index is not corrupted."
            ),
        )
    return frozenset(path for path in result.stdout.split("\x00") if path)


def _tracked_paths_casefold(git_root: Path) -> frozenset[str]:
    """Casefolded form of every path :func:`_is_tracked` would otherwise
    call tracked — for comparing against one destination path
    case-insensitively (DG-453).

    ``str.casefold()`` rather than ``.lower()``: the stricter, locale-
    independent fold appropriate for comparing filesystem paths, closer to
    what NTFS and APFS (default) themselves use than a simple lower-case
    would be. Compares *whole* repo-relative paths, so a tracked path that
    differs only in a directory segment's case (a tracked
    ``.Claude/settings.json`` against the layer's
    ``.claude/settings.json``) is caught the same way a basename
    difference is — and, just as importantly, a tracked path that merely
    *shares a basename* with the destination while living in a different
    directory (a tracked ``docs/AGENTS.md`` against a root-level layer
    ``AGENTS.md``) is **not** caught by this at all: the comparison is
    always of the whole path, never the basename alone.

    Two full-repository listings (:func:`_all_head_paths`,
    :func:`_all_staged_content_paths`) — call this at most once per
    :func:`copy_ai_layer_in` call, never once per layer file; see that
    function for why.
    """
    tracked = _all_head_paths(git_root) | _all_staged_content_paths(git_root)
    return frozenset(path.casefold() for path in tracked)


def _is_tracked(
    git_root: Path,
    relative_to_git_root: str,
    tracked_casefold: frozenset[str] | None = None,
) -> bool:
    """Whether *git_root*'s own git already protects *relative_to_git_root*
    — in the index with real content, or present in ``HEAD``, either
    under the exact same name or (DG-453) a name that differs only in
    case. See the module docstring for why both exact-case checks, and why
    an intent-to-add placeholder is deliberately not one of them.

    The exact-case checks run first, and alone decide most calls — the
    case-insensitive comparison only matters when neither of those two
    already answered yes. git's own index is case-sensitive, so a project
    that tracks ``agents.md`` has its own git answer "not tracked" for an
    AI-layer destination spelled ``AGENTS.md`` — exactly the gap that, on
    a case-insensitive filesystem (NTFS, APFS by default), means the two
    spellings are the very same on-disk file: without this,
    ``--overwrite-ai-layer`` would silently overwrite the tracked file's
    content. This refuses on the *string* comparison alone, deliberately
    not on whatever the current platform's filesystem actually does with
    the two spellings — **this also refuses on a genuinely case-sensitive
    filesystem, Linux included, where ``agents.md`` and ``AGENTS.md``
    really are two distinct files.** That is intentional, not an oversight
    this will be tightened later: a false refusal there is the safe
    direction to be wrong in; silently overwriting a tracked file is not,
    and this module has no reliable, inexpensive way to ask "is the
    destination filesystem itself case-insensitive" before anything is
    written.

    *tracked_casefold*, when given, is used as-is instead of calling
    :func:`_tracked_paths_casefold` again — :func:`copy_ai_layer_in`
    computes it once, before its validation loop, and passes the same
    value for every layer file, rather than this function re-running two
    full-repository git listings once per file. Left as ``None`` (the
    default) for a caller — direct test included — that wants this
    function's own fail-closed behaviour in isolation without doing that
    wiring itself.
    """
    if _has_staged_content(git_root, relative_to_git_root) or _in_head(
        git_root, relative_to_git_root
    ):
        return True
    if tracked_casefold is None:
        tracked_casefold = _tracked_paths_casefold(git_root)
    return relative_to_git_root.casefold() in tracked_casefold


def _checked_destination(
    project_root_resolved: Path, git_root_resolved: Path, relative: Path
) -> tuple[Path, str]:
    """The nominal destination for *relative*, and its path relative to
    *git_root_resolved* — or raise, before a single byte moves.

    Three things are refused here, regardless of whether the destination
    currently exists on disk: the nominal path being *itself* a symlink
    (dangling or not — copying through one is never attempted, matching
    "copy, never symlink" on the destination side too); its resolved target
    landing outside *project_root_resolved*; and its resolved target
    landing outside *git_root_resolved* (which would make "the path
    relative to the git root" meaningless for the tracked-file check that
    follows).
    """
    nominal = project_root_resolved / relative
    if nominal.is_symlink():
        raise ProjectRootEscapeError(
            f"{nominal} is already a symlink; refusing to copy through it.",
            remediation=(
                "Remove the symlink by hand (or replace it with a real "
                "file) and run this again."
            ),
        )

    resolved = nominal.resolve()
    try:
        resolved.relative_to(project_root_resolved)
    except ValueError:
        raise ProjectRootEscapeError(
            f"{resolved} would land outside the project root {project_root_resolved}.",
            remediation="Check the AI-layer path for '..' segments.",
        ) from None

    try:
        rel_to_git_root = resolved.relative_to(git_root_resolved).as_posix()
    except ValueError:
        raise ProjectRootEscapeError(
            f"{resolved} is outside the git root {git_root_resolved}.",
            remediation=("Check the project's registered path and git_root offset."),
        ) from None

    return resolved, rel_to_git_root


@dataclass(frozen=True)
class ValidatedLayer:
    """What :func:`validate_ai_layer_copy` found, nothing written yet —
    handed to :func:`copy_ai_layer_in` so it never re-walks the config repo
    or re-reads every file's content a second time just to copy it.
    """

    project_folder: Path
    layer_files: tuple[Path, ...]
    destinations: dict[Path, tuple[Path, str]]


def validate_ai_layer_copy(
    config_repo: Path,
    project_id: str,
    project_root: Path,
    git_root: Path,
) -> ValidatedLayer:
    """Everything :func:`copy_ai_layer_in` checks **before** writing
    anything — the tracked-file check and (DG-443) the content scan of
    every AI-layer source file's own text — with nothing written as a side
    effect, so a caller (``drunken-init``) can run this *before* the
    registry write too, and refuse the whole run, registry included,
    rather than discovering a bad file only after the registry already
    named a path to it.

    Raises exactly what :func:`copy_ai_layer_in` raises for the same bad
    input; the difference is this never reaches the exclude write or the
    copy loop at all.
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
    layer_files = ai_layer_files_under(project_folder)

    # DG-443: every AI-layer file's own content, checked before a single
    # byte is copied — see _scan_layer_files for why this also reads the
    # allowlist file's own content.
    _scan_layer_files(project_folder, layer_files)

    # Computed once here, never once per layer file below: each of
    # `_tracked_paths_casefold`'s two listings is a full-repository git
    # call (`ls-tree`, `diff --cached` with no pathspec), unlike the
    # exact-case checks `_is_tracked` tries first, which name one path
    # each. Re-running both listings for every layer file would scale
    # with the number of files for no benefit — the tracked set they
    # describe does not change partway through this call. Skipped
    # entirely when there is nothing to copy.
    tracked_casefold = (
        _tracked_paths_casefold(git_root_resolved) if layer_files else frozenset()
    )

    # Checked for *every* AI-layer path, regardless of whether a
    # destination currently exists on disk: a committed file deleted from
    # the working tree is still tracked, and must still refuse.
    destinations: dict[Path, tuple[Path, str]] = {}
    for relative in layer_files:
        resolved, rel_to_git_root = _checked_destination(
            project_root_resolved, git_root_resolved, relative
        )
        destinations[relative] = (resolved, rel_to_git_root)
        if _is_tracked(git_root_resolved, rel_to_git_root, tracked_casefold):
            raise TrackedFileConflictError(
                f"{resolved} is already tracked by this project's own git; "
                "refusing to overwrite it.",
                remediation=(
                    f"Untrack it (git rm --cached {rel_to_git_root}) if it "
                    "should come from the config repo instead, or remove it "
                    "from the config repo's project folder if it should "
                    "stay as it is."
                ),
            )

    return ValidatedLayer(
        project_folder=project_folder,
        layer_files=tuple(layer_files),
        destinations=destinations,
    )


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
    *project_id* has no folder in *config_repo*; any AI-layer path is
    already tracked by *git_root*'s own git, whether or not it currently
    exists on disk; a destination is unsafe (a symlink, or outside either
    root); or (DG-443) any AI-layer file's own content looks like a
    credential, an identity or a real machine path — see
    :func:`validate_ai_layer_copy` and :mod:`core.content_scan`. An
    existing, untracked, on-disk file is skipped (reported in
    ``.skipped``) unless *overwrite* is set.

    The exclude writer runs against *git_root* **before** any file is
    copied — so a clean ``git status`` is never a second manual step, and
    a failure there (a corrupted marker block) leaves the project tree
    exactly as it was, the same guarantee the tracked-file checks give. A
    real I/O failure partway through the copy itself raises
    :class:`PartialCopyError`, naming every file copied before it —
    re-running after fixing the underlying problem is idempotent.
    """
    config_repo = Path(config_repo)
    project_root = Path(project_root)
    git_root = Path(git_root)

    project_root_resolved = project_root.resolve()

    validated = validate_ai_layer_copy(config_repo, project_id, project_root, git_root)
    project_folder = validated.project_folder
    layer_files = validated.layer_files
    destinations = validated.destinations

    # Phase 2 — the exclude entries, *before* any file is copied: a
    # malformed marker block (or any other reason this refuses) must leave
    # the project tree exactly as it was, not copied-but-untracked.
    excluded = exclude_ai_layer(git_root)

    # Phase 3 — copy what validation did not refuse.
    copied: list[str] = []
    skipped: list[SkippedFile] = []
    for relative in layer_files:
        source = project_folder / relative
        destination, _ = destinations[relative]

        if destination.exists() and not overwrite:
            identical = filecmp.cmp(source, destination, shallow=False)
            skipped.append(
                SkippedFile(
                    relative.as_posix(),
                    "already exists and matches the config repo"
                    if identical
                    else "already exists and differs from the config repo",
                    identical=identical,
                )
            )
            continue

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        except OSError as exc:
            raise PartialCopyError(
                f"Copying {relative.as_posix()} into {project_root_resolved} "
                f"failed: {exc}. {len(copied)} file(s) were already copied "
                "before this one: "
                f"{', '.join(copied) if copied else '(none)'}.",
                remediation=(
                    "Fix the underlying problem (disk space, permissions) "
                    "and run this again — the files already copied are left "
                    "as is and will be skipped or compared, not re-copied "
                    "from scratch."
                ),
                details={
                    "copied": list(copied),
                    "failed_relative": relative.as_posix(),
                },
            ) from exc
        copied.append(relative.as_posix())

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
    "ContentScanRefusedError",
    "GitTrackedCheckFailedError",
    "LayerCopyResult",
    "PartialCopyError",
    "ProjectRootEscapeError",
    "SkippedFile",
    "TrackedFileConflictError",
    "ValidatedLayer",
    "ai_layer_files_under",
    "copy_ai_layer_in",
    "validate_ai_layer_copy",
)
