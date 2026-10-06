#!/usr/bin/env python3
"""Refuse a commit that names one of the operator's registered projects.

DG-317 took the operator's project ids out of this public repository and a test
guards the tree. The test cannot stop a new occurrence: it skips on CI, where
there is no registry, and it reads tracked files only. On 2026-09-23 a real
project key went back in twice that way. This runs where the mistake is made:

    pre-commit stage   the staged content of every added or modified file
    commit-msg stage   the commit message (``--message <file>``)
    pre-push stage     the added lines and the message of every commit this push
                       would make public for the first time (``--push``)
    CI                 every tracked file (``--tree``) and every commit message in
                       the pushed range (``--messages A..B``)

Locally the ids come from this machine's registry; no registry means nothing to
leak, and nothing is blocked -- except at push (DG-464): CI checks after the
push, and by then GitHub already keeps the commit under ``refs/pull/*`` for
good even if the PR closes unmerged, so pre-push is the last point before that
and an unchecked push is refused unless ``DRUNKEN_NO_REGISTERED_PROJECTS=1``.
CI has no registry, so there they come from the OPERATOR_PROJECT_IDS repository
secret, and ``--require-ids`` makes an unset secret a failure rather than a
pass. Output names the place, never the id: it lands in terminals and logs.

``--push`` reads the range from ``PRE_COMMIT_FROM_REF`` / ``PRE_COMMIT_TO_REF``:
pre-commit's own pre-push stage sets these (it reads the hook's stdin itself
and does not forward it), computed per the standard git pre-push protocol --
``TO`` is what is being pushed, ``FROM`` is what the remote ref already has, or
unset for a ref the remote does not have yet. The scan is ``TO --not FROM
--remotes``: every commit reachable from ``TO`` that is not already reachable
from ``FROM`` *or from any remote-tracking ref*, so a commit already public on
some other branch is never re-flagged just because this ref's own remote
tracking has not moved past it. Merge commits are read with ``--cc`` so a
conflict resolution written directly into the merge is seen too, not just
what either parent already had.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

#: This repository's own key is expected everywhere and is not inventory.
OWN_KEY = "drunken-guild"

#: Shorter ids are too generic to match on, and not much of a disclosure.
MIN_ID_LENGTH = 3

#: Separators git is asked to put between fields and between log entries.
NUL = chr(0)
SOH = chr(1)


def registered_ids() -> List[str]:
    from_secret = os.environ.get("OPERATOR_PROJECT_IDS", "")
    if from_secret.strip():
        ids = [i for i in re.split(r"[,\s]+", from_secret) if i]
        return [i for i in ids if i != OWN_KEY and len(i) >= MIN_ID_LENGTH]
    try:
        from core.registry import ProjectRegistry

        ids = list(ProjectRegistry().get_projects())
    except Exception:  # noqa: BLE001 - no readable registry: nothing to compare against
        return []
    return [i for i in ids if i != OWN_KEY and len(i) >= MIN_ID_LENGTH]


def pattern(project_id: str) -> "re.Pattern[str]":
    """The id where it is not part of a longer word (DG-317's boundary rule)."""
    return re.compile(rf"(?<![A-Za-z]){re.escape(project_id)}(?![A-Za-z])", re.I)


def _staged() -> List[tuple[str, str]]:
    names = (
        subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    out = []
    for name in filter(None, names):
        blob = subprocess.run(["git", "show", f":{name}"], capture_output=True)
        try:
            out.append((name, blob.stdout.decode("utf-8")))
        except UnicodeDecodeError:
            continue  # binary: nothing to read a name out of
    return out


def _tracked() -> List[tuple[str, str]]:
    names = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode("utf-8")
    out = []
    for name in filter(None, names.split(NUL)):
        try:
            with open(name, encoding="utf-8") as handle:
                out.append((name, handle.read()))
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: nothing to read a name out of
    return out


def _messages(rev_range: str) -> List[tuple[str, str]]:
    log = subprocess.run(
        ["git", "log", "--format=%h%x00%B%x01", rev_range],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", "replace")
    out = []
    for entry in filter(str.strip, log.split(SOH)):
        sha, _, body = entry.strip().partition(NUL)
        out.append((f"commit {sha} message", body))
    return out


def _unpublished_commit_sources(
    to_ref: str, from_ref: str | None
) -> List[tuple[str, str]]:
    """Message and added lines of every commit in ``TO --not FROM --remotes``.

    ``--remotes`` excludes anything already reachable from any remote-tracking
    ref, on top of ``FROM``: a commit already public on another branch is not
    re-flagged just because this ref's own tracking has not moved past it.
    Merge commits are read with ``--cc`` so a conflict resolution written
    directly into the merge -- not present verbatim in either parent's own
    diff -- is still seen.
    """
    log_args = ["git", "log", "--format=%H", to_ref, "--not"]
    if from_ref:
        log_args.append(from_ref)
    log_args.append("--remotes")
    result = subprocess.run(log_args, capture_output=True)
    if result.returncode != 0:
        return []

    hashes = [h for h in result.stdout.decode("utf-8", "replace").split("\n") if h]
    out: List[tuple[str, str]] = []
    for sha in hashes:
        show = subprocess.run(
            # "%x00" is git's own escape for the byte, substituted in the
            # *output*; putting the literal NUL character in argv instead
            # breaks CreateProcess on Windows (DG-464).
            ["git", "show", "--cc", "--format=%B%x00", sha],
            capture_output=True,
        )
        text = show.stdout.decode("utf-8", "replace")
        message, _, diff = text.partition(NUL)
        short = sha[:12]
        out.append((f"commit {short} message", message))
        added = "\n".join(
            line[1:]
            for line in diff.split("\n")
            if line.startswith("+") and not line.startswith("+++")
        )
        out.append((f"commit {short} added lines", added))
    return out


def offenders(sources: List[tuple[str, str]], ids: List[str]) -> List[str]:
    patterns = [pattern(i) for i in ids]
    return [
        f"{name}:{n}"
        for name, text in sources
        for n, line in enumerate(text.split("\n"), 1)
        if any(p.search(line) for p in patterns)
    ]


def _main_push() -> int:
    """``--push``: refuse unless there are ids to check, or the opt-out is set.

    Unlike the pre-commit and commit-msg stages, no registry here does not
    mean nothing to leak -- a push that nobody checked is not a clean one, so
    it is refused rather than passed, unless DRUNKEN_NO_REGISTERED_PROJECTS=1
    says that is deliberate (an operator with nothing registered yet, or CI's
    own smoke run of this hook).
    """
    ids = registered_ids()
    if not ids:
        if os.environ.get("DRUNKEN_NO_REGISTERED_PROJECTS") == "1":
            return 0
        print(
            "No project ids to check this push against. Set "
            "DRUNKEN_NO_REGISTERED_PROJECTS=1 if that is deliberate; an "
            "unchecked push is not a clean one."
        )
        return 1

    to_ref = os.environ.get("PRE_COMMIT_TO_REF") or "HEAD"
    from_ref = os.environ.get("PRE_COMMIT_FROM_REF") or None
    sources = _unpublished_commit_sources(to_ref, from_ref)

    found = offenders(sources, ids)
    if not found:
        return 0
    print(
        "A registered project id is in a commit this push would make public. "
        "This repository is public. Use alpha/beta, or describe the role "
        "instead of naming it:"
    )
    for place in found:
        print(f"  {place}")
    return 1


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--message", help="commit message file (commit-msg stage)")
    parser.add_argument("--tree", action="store_true", help="every tracked file (CI)")
    parser.add_argument("--messages", default="", help="commit range A..B (CI)")
    parser.add_argument(
        "--push",
        action="store_true",
        help="unpublished commits in PRE_COMMIT_FROM_REF..PRE_COMMIT_TO_REF (pre-push stage)",
    )
    parser.add_argument(
        "--require-ids",
        action="store_true",
        help="fail when there are no ids to check against (CI)",
    )
    args = parser.parse_args(argv)

    if args.push:
        return _main_push()

    ids = registered_ids()
    if not ids:
        if args.require_ids:
            print(
                "No project ids to check against. Set the OPERATOR_PROJECT_IDS "
                "repository secret; an unchecked run is not a clean one."
            )
            return 1
        return 0

    if args.message:
        with open(args.message, encoding="utf-8", errors="replace") as handle:
            sources = [("commit message", handle.read())]
    elif args.tree or args.messages:
        sources = _tracked() if args.tree else []
        if args.messages:
            sources += _messages(args.messages)
    else:
        sources = _staged()

    found = offenders(sources, ids)
    if not found:
        return 0
    print(
        "A registered project id is in what you are committing. This repository is "
        "public. Use alpha/beta, or describe the role instead of naming it:"
    )
    for place in found:
        print(f"  {place}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
