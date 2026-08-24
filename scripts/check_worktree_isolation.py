#!/usr/bin/env python3
"""Pre-commit safety net for DG-288 ("One Working Tree Per Agent"): block a
commit authored as Antigravity from landing in this repository's primary
working tree.

Antigravity is supposed to work from its own `git worktree` -- a sibling
checkout (`git worktree add ../drunken-guild.antigravity <branch>`) or its
runtime's own isolated tree -- never the tree Claude's harness starts in.
DG-298 (commit cdaf00c) showed nothing caught it when that didn't happen:
Antigravity committed straight into the shared primary tree and left it
checked out on a feature branch after the session ended. DG-299 is that
gap; this hook closes it.

Detection relies on the same mechanism DG-293 already requires: an agent
commit passes `--author`, and git exposes that to hooks as
GIT_AUTHOR_NAME/GIT_AUTHOR_EMAIL (verified empirically -- `git var
GIT_AUTHOR_IDENT` reflects the flag, not just committer config). A commit
made as Antigravity without `--author` at all is invisible to this check --
that is a DG-293 violation of its own, not this hook's job to catch.
"""

import subprocess
import sys

ANTIGRAVITY_EMAIL = "antigravity@drunken.local"


def _git_dir() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _is_linked_worktree(git_dir: str) -> bool:
    # A linked worktree's git-dir is always <primary>/.git/worktrees/<name>.
    # The primary tree's own git-dir has no /worktrees/ path component --
    # this is what actually distinguishes "Antigravity's own checkout" from
    # "the tree Claude's harness starts in", not branch name or cwd.
    return "/.git/worktrees/" in git_dir.replace("\\", "/")


def _author_email() -> str:
    out = subprocess.run(
        ["git", "var", "GIT_AUTHOR_IDENT"],
        capture_output=True,
        text=True,
        check=True,
    )
    ident = out.stdout.strip()
    # Format: "Name <email> timestamp tz"
    start = ident.find("<")
    end = ident.find(">", start)
    if start == -1 or end == -1:
        return ""
    return ident[start + 1 : end]


def main() -> int:
    try:
        git_dir = _git_dir()
    except Exception as e:
        print(
            f"[check_worktree_isolation] Could not resolve git dir ({e}) — "
            "allowing (warn-only).",
            file=sys.stderr,
        )
        return 0

    if _is_linked_worktree(git_dir):
        # Exactly what DG-288 asks for: Antigravity (or anything else)
        # committing from its own linked worktree, not the shared one.
        return 0

    try:
        email = _author_email()
    except Exception as e:
        print(
            f"[check_worktree_isolation] Could not resolve commit author "
            f"({e}) — allowing (warn-only).",
            file=sys.stderr,
        )
        return 0

    if email == ANTIGRAVITY_EMAIL:
        print(
            "\nBLOCKED (DG-288): this commit is authored as Antigravity but "
            "is landing in the repository's primary working tree, which is "
            "Claude's checkout. Antigravity must commit from its own "
            "`git worktree` -- see 'One Working Tree Per Agent' in "
            "skills/workflow/git-workflow/SKILL.md, e.g.:\n"
            "  git worktree add ../drunken-guild.antigravity <branch>\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
