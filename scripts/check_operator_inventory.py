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
what either parent already had. Any failure to resolve the range -- an
unknown ``FROM``/``TO``, running outside a git checkout at all -- refuses the
push; it is never read as "nothing to scan". ``TO`` as the all-zero SHA (a
branch deletion: nothing is being pushed) is the one case that legitimately
needs no scan at all, and is the only one.

An annotated tag's own message (set with ``git tag -a -m``) lives on the tag
object, not on any commit, so walking commits never reads it (DG-468). When
``TO`` is itself a tag object -- what a real push of just a tag sets it to,
since the ref points at the tag object and not at the commit it names -- its
message is read too, following a chain of tags pointing at tags down to the
first non-tag object. A tag already confirmed present on a remote (``git
ls-remote --tags``) is not re-flagged; that confirmation is best-effort and
failing it only means scanning a tag that may already be public, never the
reverse. A lightweight tag has no object of its own -- its ref points
directly at the commit -- so it is simply scanned as that commit, not
specially and not as an error. A tag pointing at a tree or a blob instead of
a commit has no commit range to walk; that refuses rather than reads as
nothing to scan, the same as every other unresolvable range here.

Binary content added by a pushed commit *is* read for ids (DG-468): unlike
``_staged``/``_tracked``, which read a file's current content and skip what
will not decode, ``--push`` reads a unified diff, where a binary file's
changed bytes never appear at all -- git prints only "Binary files ...
differ" -- so without reading the blob directly a binary file would be a
free pass for anything hidden in it. The blob is read as a handful of cheap
decodes of the same bytes (``latin-1``, a NUL-stripped pass, and a UTF-16/32
attempt), because a plain ``latin-1`` decode alone leaves a NUL between every
character of UTF-16 text and an otherwise-plain id never matches. Above
``MAX_BINARY_BYTES``, this refuses by naming the *path*, never the content,
rather than hold an unbounded blob in memory on every push. Reading raw
bytes this way can also coincidentally match an id's text inside unrelated
binary data that was never about the id at all; the only escape, the same as
for every other false positive this file can produce, is fixing the content
or ``DRUNKEN_NO_REGISTERED_PROJECTS=1``.

pre-commit's own pre-push wrapper (``pre_commit.commands.hook_impl``) reports
only the *first* non-delete ref line of the push, whatever else is also being
pushed in the same invocation (confirmed against a real installed pre-push
hook: ``git push origin feature v1`` with an id only in ``v1``'s annotated
tag message passed, and the id reached the remote). ``PRE_COMMIT_FROM_REF``/
``TO_REF`` describe only that one ref, so relying on them alone misses every
other ref a multi-ref push, ``--follow-tags``, or ``--tags`` would also
publish. On top of the ref-specific range, this file therefore always also
scans every commit reachable from any local branch or tag not already on
some remote (``git rev-list --branches --tags --not --remotes``) and the
message of every local annotated tag not already on some remote, regardless
of which single ref ``FROM``/``TO`` happen to describe (DG-468 round 2). This
is deliberately over-inclusive: a local-only branch or tag that merely
*names* an id blocks a push of something else entirely unrelated to it. The
escape is fixing or removing the offending local ref; when there is nothing
registered to check against at all, ``DRUNKEN_NO_REGISTERED_PROJECTS=1``
already covers that separately, as it did before this file read any tag or
local-only ref at all.

**What this covers, stated exactly, so "tags are scanned" is never read as
unconditional:** when this hook runs, it reads every commit unpublished on
every local branch and tag (not just the one ref FROM/TO describe), the
message of every local annotated tag not already on a remote, and binary
content up to ``MAX_BINARY_BYTES``, decoded as plain bytes, NUL-stripped,
and UTF-16/32.

**What pre-commit's own pre-push stage never invoked this for, and why that
no longer matters (DG-479, decided 2026-10-09 -- the Boss: option A
narrow + D):** ``pre_commit.commands.hook_impl._pre_push_ns`` returns
"nothing to push" -- and this script was never run, with no output -- when
every pushed ref either deletes something or points at a commit already
reachable from a remote-tracking ref. A solo annotated tag pushed onto an
*already-public* commit (``git tag -a v1 -m "<id>" && git push origin
v1``), a ref deletion pushed alongside a new ref (``git push origin :old
v3``), and any push that is *entirely* deletions or already-public commits
all used to leak an unscanned tag message this way. The fix is a *native*
``pre-push`` hook (``scripts/git_hooks/pre-push``, installed by
``drunken-init --install-git-hooks`` -- see ``src/core/git_hooks.py``) that
git always invokes directly, outside pre-commit entirely, reading the ref
lines off its own stdin and calling this same ``--push`` mode once per
ref with that ref's own ``PRE_COMMIT_FROM_REF``/``PRE_COMMIT_TO_REF``
values -- the identical environment contract pre-commit's own pre-push
stage already set, so every case above now reaches this script with a real
``TO`` to scan. ``pre-commit``'s own pre-push stage is therefore no longer
installed at all (out of ``default_install_hook_types``): the native hook
is the sole owner of the stage, so the two never race for it. The residual,
accepted limits -- ``git push --no-verify``, a ``core.hooksPath`` pointing
elsewhere, or a checkout that never ran the installer at all -- are
``drunken-doctor``'s ``guard.git_hooks`` to report, not this script's to
close; see REQ-023 in ``.ai/PRD.md``. ``refs/notes/*`` and any ref outside
``refs/heads``/``refs/tags`` are likewise not specifically read (they are
not walked by ``--branches --tags``, though a note's own commit content, if
reachable some other way, still is).

DG-480 (a brand-new repository's first push being refused) disappears the
same way: pre-commit's own "all_files" path for a from-scratch push used to
leave both ``PRE_COMMIT_FROM_REF`` and ``PRE_COMMIT_TO_REF`` unset, which
this script correctly refused rather than guess -- but the native hook
never takes that path at all. git always hands it the real local/remote sha
for every ref line it reads off stdin, including a first push (remote sha
all-zero, read as ``FROM`` unset below), so there is always a real ``TO`` to
scan. Run by hand, or by anything else that does not set
``PRE_COMMIT_TO_REF``, this still refuses rather than guess what is being
pushed -- that part of the contract is unchanged.
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

#: git's own all-zero SHA, meaning "no commit here" on either side of a
#: pre-push ref update (a branch deletion when it is TO).
ZERO_SHA = "0" * 40


class ScanFailed(Exception):
    """git could not resolve the push range at all.

    Not a sign that there is nothing to scan: a failure here must refuse the
    push, the same as every other failure mode this file treats as
    fail-closed, never fall through to a silent pass (DG-464 review).
    """


class BinaryTooLarge(ScanFailed):
    """A changed binary file is over ``MAX_BINARY_BYTES``.

    Still a refusal, like every ``ScanFailed``, but one that may safely name
    *where* -- the path is not a secret -- while never naming the content
    (DG-468 round 2, reviewer item 4)."""

    def __init__(self, path: str) -> None:
        super().__init__(f"binary blob too large to scan safely: {path}")
        self.path = path


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


def _ref_specific_commit_hashes(to_ref: str, from_ref: str | None) -> List[str]:
    """Every commit in ``TO --not FROM --remotes``.

    ``--remotes`` excludes anything already reachable from any remote-tracking
    ref, on top of ``FROM``: a commit already public on another branch is not
    re-flagged just because this ref's own tracking has not moved past it.
    """
    log_args = ["git", "log", "--format=%H", to_ref, "--not"]
    if from_ref:
        log_args.append(from_ref)
    log_args.append("--remotes")
    try:
        result = subprocess.run(log_args, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git log could not resolve the push range") from exc
    return [h for h in result.stdout.decode("utf-8", "replace").split("\n") if h]


def _locally_unpublished_commit_hashes() -> List[str]:
    """Every commit reachable from any local branch or tag, not already
    reachable from any remote-tracking ref -- regardless of which single
    ref this invocation's own FROM/TO describe (DG-468 round 2)."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--branches", "--tags", "--not", "--remotes"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git rev-list could not enumerate local refs") from exc
    return [h for h in result.stdout.decode("utf-8", "replace").split("\n") if h]


def _locally_unpublished_tag_shas() -> List[str]:
    """The object id of every local annotated tag (lightweight tags have no
    object of their own and are already covered by the commit scan)."""
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "refs/tags", "--format=%(objectname)"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git for-each-ref could not enumerate tags") from exc
    shas = [
        s.strip()
        for s in result.stdout.decode("utf-8", "replace").split("\n")
        if s.strip()
    ]
    return [s for s in shas if _object_kind(s) == "tag"]


def _verify_tag_resolves_to_commit(ref: str) -> None:
    """Force the peel to a commit: ``git log`` on a tag pointing at a tree
    or a blob silently finds no commits rather than erroring, which would
    read as "nothing to scan"."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ScanFailed(f"tag {ref[:12]} does not resolve to a commit") from exc


#: Read fully into memory, decoded several ways, per changed binary file.
#: Above this, refuse by naming the path rather than hold an unbounded blob
#: in memory on every push (DG-468 round 2, reviewer item 4). A pre-push
#: hook runs on every push; this keeps that bounded and fast.
MAX_BINARY_BYTES = 1_000_000


def _binary_text_variants(data: bytes) -> List[str]:
    """A handful of cheap decodes of the same bytes, so an id surviving in
    any common binary-safe text encoding is still read as a plain string.

    ``latin-1`` never fails and maps byte-for-byte, catching any plain-ASCII
    id verbatim -- but it leaves a NUL between every character of UTF-16
    text, so an otherwise-plain id never matches that way (DG-468 round 2,
    reviewer item 2). Stripping NUL bytes before that same decode recovers
    an all-ASCII id out of UTF-16 *or* UTF-32 content regardless of byte
    order or a leading BOM, since each such encoding pads an ASCII byte with
    one or three zero bytes -- so this single pass covers LE, BE, with and
    without a BOM, without a decode needing to succeed at all. Genuine
    UTF-16/32 decodes are attempted too, best-effort, for non-ASCII content.
    """
    variants = [data.decode("latin-1")]
    stripped = data.replace(b"\x00", b"")
    if stripped != data:
        variants.append(stripped.decode("latin-1"))
    for encoding in (
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
    ):
        try:
            variants.append(data.decode(encoding))
        except (UnicodeDecodeError, UnicodeError):
            continue
    return variants


def _binary_sources(sha: str, short: str, diff: str) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for path in BINARY_DIFF.finditer(diff):
        new_path = path.group("path")
        if not new_path:
            continue  # the binary side removed, nothing added to read
        try:
            size_out = subprocess.run(
                ["git", "cat-file", "-s", f"{sha}:{new_path}"],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ScanFailed(f"git cat-file -s failed for {short}:{new_path}") from exc
        try:
            size = int(size_out.stdout.decode("utf-8", "replace").strip())
        except ValueError as exc:
            raise ScanFailed(
                f"git cat-file -s gave no size for {short}:{new_path}"
            ) from exc
        if size > MAX_BINARY_BYTES:
            raise BinaryTooLarge(f"{short}:{new_path}")
        try:
            blob = subprocess.run(
                ["git", "show", f"{sha}:{new_path}"],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ScanFailed(f"git show failed for {short}:{new_path}") from exc
        for n, text in enumerate(_binary_text_variants(blob.stdout)):
            out.append((f"commit {short} added binary {new_path} (decode {n})", text))
    return out


def _commit_sources(hashes: List[str]) -> List[tuple[str, str]]:
    """Message, added lines, and added binary content of each commit.

    Merge commits are read with ``--cc`` so a conflict resolution written
    directly into the merge -- not present verbatim in either parent's own
    diff -- is still seen.
    """
    out: List[tuple[str, str]] = []
    for sha in hashes:
        try:
            show = subprocess.run(
                # "%x00" is git's own escape for the byte, substituted in the
                # *output*; putting the literal NUL character in argv instead
                # breaks CreateProcess on Windows (DG-464).
                ["git", "show", "--cc", "--format=%B%x00", sha],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ScanFailed(f"git show failed for {sha[:12]}") from exc
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
        out += _binary_sources(sha, short, diff)
    return out


#: A binary file's changed bytes never appear in a unified diff -- only this
#: marker line does. The "to" side names the path with content to read; a
#: deletion's "to" side is /dev/null and has nothing added to read.
BINARY_DIFF = re.compile(
    r"^Binary files (?:a/.+|/dev/null) and (?:b/(?P<path>.+)|/dev/null) differ$",
    re.MULTILINE,
)

#: A tag can point at another tag; object ids are content-addressed so a
#: true cycle cannot occur, but a chain must still be bounded defensively.
MAX_TAG_CHAIN = 50


def _object_kind(ref: str) -> str:
    try:
        return (
            subprocess.run(
                ["git", "cat-file", "-t", ref], capture_output=True, check=True
            )
            .stdout.decode("utf-8", "replace")
            .strip()
        )
    except subprocess.CalledProcessError as exc:
        raise ScanFailed(f"git cat-file -t failed for {ref[:12]}") from exc


#: `git remote`/`git ls-remote` must never be left free to hang this hook
#: waiting on a credential prompt or a slow/unreachable host (DG-468 round
#: 2, reviewer item 3): this is a best-effort convenience lookup, not the
#: detection itself, and a failure here already falls back to over-inclusive
#: (scan it anyway), never the other way.
_REMOTE_QUERY_TIMEOUT = 5  # seconds
_NO_PROMPT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "true",
    "GCM_INTERACTIVE": "Never",
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=5",
}


def _already_public_tag_shas() -> set[str]:
    """Annotated tag object ids confirmed present on some configured remote.

    Best-effort, and deliberately asymmetric with the rest of this file's
    fail-closed rule: failing to confirm a tag is already public only means
    it gets scanned again (over-inclusive, never a missed leak), so a remote
    that cannot be reached -- or does not answer -- does not refuse the
    whole push over an exclusion that is a convenience, not the detection
    itself. Never prints anything from the attempt: a remote URL can carry
    a credential or a token.
    """
    env = {**os.environ, **_NO_PROMPT_ENV}
    try:
        remotes = (
            subprocess.run(
                ["git", "remote"],
                capture_output=True,
                check=True,
                env=env,
                timeout=_REMOTE_QUERY_TIMEOUT,
            )
            .stdout.decode("utf-8", "replace")
            .split()
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return set()
    shas: set[str] = set()
    for remote in remotes:
        try:
            out = subprocess.run(
                ["git", "ls-remote", "--tags", remote],
                capture_output=True,
                check=True,
                env=env,
                timeout=_REMOTE_QUERY_TIMEOUT,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        for line in out.stdout.decode("utf-8", "replace").split("\n"):
            sha, _, _ref = line.partition("\t")
            sha = sha.strip()
            if sha:
                shas.add(sha.lower())
    return shas


def _tag_chain_messages(
    start_sha: str, already_public: set[str]
) -> List[tuple[str, str]]:
    """The message of every annotated tag object from ``start_sha`` down to
    the first non-tag object -- a tag can point at another tag -- skipping
    any tag object already confirmed public."""
    out: List[tuple[str, str]] = []
    sha = start_sha
    for _ in range(MAX_TAG_CHAIN):
        kind = _object_kind(sha)
        if kind != "tag":
            return out
        try:
            body = subprocess.run(
                ["git", "cat-file", "-p", sha], capture_output=True, check=True
            ).stdout.decode("utf-8", "replace")
        except subprocess.CalledProcessError as exc:
            raise ScanFailed(f"git cat-file -p failed for {sha[:12]}") from exc
        header, _, message = body.partition("\n\n")
        if sha.lower() not in already_public:
            out.append((f"tag {sha[:12]} message", message))
        next_sha = ""
        for line in header.split("\n"):
            if line.startswith("object "):
                next_sha = line[len("object ") :].strip()
                break
        if not next_sha:
            raise ScanFailed(f"tag object {sha[:12]} has no object field")
        sha = next_sha
    raise ScanFailed("tag chain too deep to resolve safely")


def _push_sources(to_ref: str, from_ref: str | None) -> List[tuple[str, str]]:
    """Everything this push could make public for the first time.

    Ref-specific (``TO --not FROM --remotes``, plus ``TO``'s own tag chain
    when ``TO`` is a tag object) when there is a specific ref to look at at
    all -- ``TO`` as the all-zero SHA is a pure deletion, with nothing of
    its own to add here. Unioned, always, with every commit reachable from
    any local branch or tag not already on some remote, and every local
    annotated tag message not already on some remote (DG-468 round 2): see
    the module docstring for why FROM/TO alone are not enough.
    """
    commit_hashes: set[str] = set()
    tag_shas: set[str] = set()

    if to_ref != ZERO_SHA:
        commit_hashes.update(_ref_specific_commit_hashes(to_ref, from_ref))
        if _object_kind(to_ref) == "tag":
            tag_shas.add(to_ref)
            _verify_tag_resolves_to_commit(to_ref)

    commit_hashes.update(_locally_unpublished_commit_hashes())
    tag_shas.update(_locally_unpublished_tag_shas())

    already_public = _already_public_tag_shas()
    sources = _commit_sources(sorted(commit_hashes))
    for sha in sorted(tag_shas):
        sources += _tag_chain_messages(sha, already_public)
    return sources


def offenders(sources: List[tuple[str, str]], ids: List[str]) -> List[str]:
    patterns = [pattern(i) for i in ids]
    return [
        f"{name}:{n}"
        for name, text in sources
        for n, line in enumerate(text.split("\n"), 1)
        if any(p.search(line) for p in patterns)
    ]


#: Extracts the short sha and kind out of an `offenders()` place string
#: ("commit abc123def456 message", "tag abc123def456 message", ...) --
#: never the matched line's content, which `offenders()` never carries
#: this far to begin with.
_PLACE_RE = re.compile(r"^(commit|tag) ([0-9a-f]{7,40}) ")


def _refs_containing_commit(short_sha: str) -> List[str]:
    try:
        result = subprocess.run(
            [
                "git",
                "for-each-ref",
                "--contains",
                short_sha,
                "refs/heads",
                "refs/tags",
                "--format=%(refname)",
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [
        r.strip()
        for r in result.stdout.decode("utf-8", "replace").split("\n")
        if r.strip()
    ]


def _refs_pointing_at(short_sha: str) -> List[str]:
    try:
        result = subprocess.run(
            [
                "git",
                "for-each-ref",
                "--points-at",
                short_sha,
                "refs/tags",
                "--format=%(refname)",
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [
        r.strip()
        for r in result.stdout.decode("utf-8", "replace").split("\n")
        if r.strip()
    ]


def _describe_offense(place: str) -> tuple[str, List[str]]:
    """Enrich a `place` string with the local ref name(s) it is reachable
    from (a commit) or pointed at by (a tag object) -- so a refusal caused
    by the over-inclusive global scan (DG-468 round 2) says which ref to
    drop or amend, not just an opaque sha (DG-468 round 3, friction). Never
    the id, never the matched line's content -- `place` never carried
    either. Best-effort: a lookup failure here only means a plainer
    message, never a different refusal decision.
    """
    match = _PLACE_RE.match(place)
    if not match:
        return place, []
    kind, short = match.group(1), match.group(2)
    refs = _refs_pointing_at(short) if kind == "tag" else _refs_containing_commit(short)
    if not refs:
        return place, []
    return f"{place} (on {', '.join(refs)})", refs


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

    to_ref = os.environ.get("PRE_COMMIT_TO_REF")
    if not to_ref:
        # Not set at all: this is meant to run as pre-commit's own pre-push
        # stage, which always sets it when anything is being pushed. Run by
        # hand, or under some other invocation that does not set it, there is
        # no safe guess for what "the push" is -- not HEAD, not a pass.
        print(
            "PRE_COMMIT_TO_REF is not set. This runs as pre-commit's own "
            "pre-push hook, which sets it; refusing rather than guessing "
            "what is being pushed."
        )
        return 1

    # TO as the all-zero SHA is a branch deletion: nothing of its own is
    # being pushed. It is not, on its own, "nothing to scan" any more
    # (DG-468 round 2) -- `_push_sources` below still runs the global scan
    # for anything else locally unpublished; it just has no ref-specific
    # range of its own to add to that.

    from_ref = os.environ.get("PRE_COMMIT_FROM_REF") or None
    if from_ref == ZERO_SHA:
        from_ref = None

    try:
        sources = _push_sources(to_ref, from_ref)
    except BinaryTooLarge as exc:
        print(
            f"A changed binary file is too large to scan safely: {exc.path}. "
            "Refusing rather than reading an unbounded blob into memory."
        )
        return 1
    except ScanFailed:
        print(
            "Could not determine which commits this push would make public "
            "(git could not resolve the range). Refusing rather than passing "
            "an unchecked push."
        )
        return 1

    found = offenders(sources, ids)
    if not found:
        return 0
    described = [_describe_offense(place) for place in found]
    offending_refs = sorted({ref for _, refs in described for ref in refs})
    print(
        "A registered project id is in something this push would make public. "
        "This repository is public. Use alpha/beta, or describe the role "
        "instead of naming it:"
    )
    for line, _ in described:
        print(f"  {line}")
    if offending_refs:
        print(
            "Drop or amend the offending ref(s) to fix this: "
            + ", ".join(offending_refs)
            + ". DRUNKEN_NO_REGISTERED_PROJECTS=1 is the separate escape for "
            "nothing registered to check against at all -- not for this."
        )
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
