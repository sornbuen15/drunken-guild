"""Install and recognise the native pre-push hook (DG-479, DG-480).

pre-commit's own pre-push stage never runs for some pushes at all (DG-479,
see the module docstring of ``scripts/check_operator_inventory.py``): a
solo annotated tag pushed onto an already-public commit, or a push that is
only ref deletions, makes ``pre_commit.commands.hook_impl._pre_push_ns``
report "nothing to push", and the hook process is never started -- no
amount of logic inside the scanner script can close that, because it is
never run. The fix decided on (DG-479_DECISION.md, 2026-10-09, the Boss:
option A narrow + D) is a *native* ``pre-push`` hook that git always
invokes directly, reading the ref lines off its own stdin -- never managed
by pre-commit, and the sole owner of the ``pre-push`` stage so the two
never race for it (``pre-push`` comes out of ``default_install_hook_types``
in ``.pre-commit-config.yaml`` in the same change).

This module is the one supported way to put that hook into a checkout. An
agent does not run it (CLAUDE.md: "An agent does not install"); it writes
this code and says the exact command in the PR body for a human to run.

Three things this installer must never do, each with a test:

* **Never overwrite or delete a foreign hook.** A ``pre-push`` file that
  exists and does not carry :data:`MARKER` was put there by something
  else -- a human, another tool -- and this refuses outright rather than
  guess it is safe to replace.
* **Never bake in a worktree-specific path.** `git rev-parse --git-path
  hooks` resolves to the *shared* hooks directory of the common git dir
  even from a linked worktree (reused here via :func:`core.doctor.
  hooks_dir`, the same resolution DG-466's doctor check already relies
  on) -- one install covers every worktree, and the hook template itself
  names no path outside ``$REPO_ROOT`` it discovers at run time.
* **Honour ``core.hooksPath``.** Resolved through the same
  :func:`core.doctor.hooks_dir`, which already follows it -- this
  installer never assumes ``<git_root>/.git/hooks``.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .doctor import hooks_dir
from .errors import ValidationError

#: The one file this installer ever writes.
HOOK_FILENAME = "pre-push"

#: What `pre-commit install --hook-type pre-push` renames an existing
#: native hook to ("migration mode") before installing its own shim --
#: DG-479_DECISION.md verified this silently never runs on Windows (the
#: shim hands `_run_legacy` an MSYS-style path `os.access` reports as not
#: executable), so a `.legacy` file sitting next to a missing or foreign
#: `pre-push` means the privacy scan quietly stopped running.
LEGACY_SUFFIX = ".legacy"

#: The first content line (after the shebang) of every hook this installer
#: writes. The one fact that lets this installer -- and `drunken-doctor`'s
#: guard.git_hooks -- tell "ours, safe to update in place" apart from "a
#: human or another tool put a different pre-push hook here, never touch
#: it". Must stay byte-for-byte identical to line 2 of
#: `scripts/git_hooks/pre-push`.
MARKER = "# drunken-guild native pre-push hook (DG-479/DG-480) -- do not edit by hand."

#: Where the shipped hook script lives, relative to this repository's own
#: root. Read off disk at install time (not embedded as a string constant)
#: so the committed script under version control is the literal thing
#: that gets installed -- nothing to drift between a comment and a copy.
_TEMPLATE_RELATIVE = ("scripts", "git_hooks", "pre-push")


class GitHooksTemplateMissingError(ValidationError):
    """The repository's own hook template could not be read.

    Today's installer reads it straight off this source tree
    (``scripts/git_hooks/pre-push``), the same assumption
    ``_target_is_this_repository``'s neighbours in ``core.init`` already
    make about where a dev checkout's own files live; an installed
    package with no ``scripts/`` directory is not yet a supported target.
    """

    code = "git_hooks_template_missing"


class ForeignPrePushHookError(ValidationError):
    """A ``pre-push`` file exists and was not written by this installer."""

    code = "foreign_pre_push_hook"


def _template_path() -> Path:
    # src/core/git_hooks.py -> parents[2] is the repository root.
    return Path(__file__).resolve().parents[2].joinpath(*_TEMPLATE_RELATIVE)


def _read_template() -> str:
    path = _template_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GitHooksTemplateMissingError(
            f"No pre-push hook template at {path}.",
            remediation=(
                "Run this from a checkout of drunken-guild itself -- the "
                "installer reads the template off its own source tree, "
                "and does not yet ship it for an installed CLI."
            ),
        ) from exc


def is_ours(hook_path: Path) -> bool:
    """Whether *hook_path* is a file this installer wrote (or could safely
    update in place), by the one fact that matters: it carries
    :data:`MARKER`. ``False`` for a missing file too -- "not ours" and
    "absent" are different questions a caller must ask separately."""
    try:
        text = hook_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return MARKER in text


def _make_executable(path: Path) -> None:
    # Windows has no exec bit of its own to set -- `os.access(..., X_OK)`
    # already reports every file executable there regardless (the same
    # reason `core.doctor.missing_hook_types` skips the check), and git
    # for Windows runs a hook through its own shell association rather
    # than requiring one. Nothing to do; nothing to get wrong either.
    if os.name == "nt":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_pre_push_hook(git_root: Path) -> str:
    """Write the native pre-push hook into *git_root*'s real hooks
    directory. Returns a one-line human-readable report of what happened.

    Idempotent: installing over this installer's own, byte-identical hook
    is a no-op report, not a rewrite; installing over this installer's own
    hook with different content (the template changed upstream) updates it
    in place. A ``pre-push`` that exists and is not ours is refused
    outright -- never overwritten, never deleted (``ForeignPrePushHookError``).
    """
    resolved = hooks_dir(git_root)
    if resolved is None:
        raise ValidationError(
            f"Could not resolve the git hooks directory for {git_root}.",
            remediation=(
                "Run this inside a git checkout (`git rev-parse --git-path "
                "hooks` must answer)."
            ),
        )
    resolved.mkdir(parents=True, exist_ok=True)
    target = resolved / HOOK_FILENAME
    template = _read_template()

    if target.exists():
        if not is_ours(target):
            raise ForeignPrePushHookError(
                f"{target} already exists and was not written by this installer.",
                remediation=(
                    f"Remove or rename {target} yourself first, if it is "
                    "safe to replace it, then re-run -- this installer "
                    "never overwrites or deletes a hook it did not write."
                ),
            )
        if target.read_text(encoding="utf-8") == template:
            return f"unchanged: {target} already carries this hook"
        target.write_text(template, encoding="utf-8")
        _make_executable(target)
        return f"updated: {target}"

    target.write_text(template, encoding="utf-8")
    _make_executable(target)
    return f"installed: {target}"
