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
<what the push target itself advertises right now>``: every commit reachable
from ``TO`` that is not already reachable from ``FROM`` *or from something the
remote already has* (DG-479 round 4 -- see below for what decides that), so a
commit already public on some other branch is never re-flagged just because
this ref's own remote tracking has not moved past it. Merge commits are read
with ``--cc`` so a conflict resolution written directly into the merge is
seen too, not just what either parent already had. Any failure to resolve the
range -- an unknown ``FROM``/``TO``, running outside a git checkout at all --
refuses the push; it is never read as "nothing to scan". ``TO`` as the
all-zero SHA (a branch deletion: nothing is being pushed) is the one case
that legitimately needs no scan at all, and is the only one.

An annotated tag's own message (set with ``git tag -a -m``) lives on the tag
object, not on any commit, so walking commits never reads it (DG-468). When
``TO`` is itself a tag object -- what a real push of just a tag sets it to,
since the ref points at the tag object and not at the commit it names -- its
message is read too, following a chain of tags pointing at tags down to the
first non-tag object. A tag already advertised by the push target itself is
not re-flagged (DG-479 round 4). A lightweight tag has no object of its own
-- its ref points directly at the commit -- so it is simply scanned as that
commit, not specially and not as an error. A tag pointing at a tree or a blob
instead of a commit has no commit range to walk; that refuses rather than
reads as nothing to scan, the same as every other unresolvable range here.

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
scans every commit reachable from any local branch or tag not already
advertised by the push target (``git rev-list --branches --tags --not
<advertised tips>``, DG-479 round 4) and the message of every local annotated
tag not already advertised, regardless of which single ref ``FROM``/``TO``
happen to describe (DG-468 round 2). This is deliberately over-inclusive: a
local-only branch or tag that merely *names* an id blocks a push of something
else entirely unrelated to it. The escape is fixing or removing the
offending local ref; when there is nothing registered to check against at
all, ``DRUNKEN_NO_REGISTERED_PROJECTS=1`` already covers that separately, as
it did before this file read any tag or local-only ref at all.

**What this covers, stated exactly, so "tags are scanned" is never read as
unconditional:** when this hook runs, it reads every commit unpublished on
every local branch and tag (not just the one ref FROM/TO describe), the
message of every local annotated tag not already advertised by the push
target, and binary content up to ``MAX_BINARY_BYTES``, decoded as plain
bytes, NUL-stripped, and UTF-16/32.

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
git always invokes directly, outside pre-commit entirely. ``pre-commit``'s
own pre-push stage is therefore no longer installed at all (out of
``default_install_hook_types``): the native hook is the sole owner of the
stage, so the two never race for it.

**``--push-multi``, how the native hook actually calls this (DG-479 round
3):** the hook forwards git's own stdin to this process completely
untouched, one ref line per update -- ``<local ref> <local sha> <remote
ref> <remote sha>``. Every non-deletion line's ``local_sha`` is read, not
just the first: a round 2 design that only looked at one ref line and
leaned on the always-on global scan for the rest missed a commit reachable
from *nothing* under ``refs/heads``/``refs/tags`` -- a detached sha pushed
directly, a branch whose only local ref was deleted after the dirty commit
was made, ``refs/stash``, ``refs/original/*`` -- because the global scan,
by construction, only ever walks local branches and tags. ``_push_sources_
multi`` instead unions every pushed ``local_sha`` into a single ``git log
<union of TOs> --not <union of FROMs> <what the push target advertises>``
call (one invocation, not one per ref -- a 500-ref push calling the old
per-ref range once each took over six minutes; the union call does not),
peels any of those that are themselves annotated tag objects, and still
runs the same always-on global scan as defence in depth for a local ref
this push does not even touch. ``refs/notes/*`` and any other ref outside
``refs/heads``/``refs/tags`` are scanned exactly like any other ref by this
path -- their namespace does not matter at all to ``local_sha``/
``remote_sha``, only the commit (or tag) object those shas resolve to; a
clean notes push is quiet, a dirty one is refused, the same as any other
ref.

**"Already public" is decided by asking the push target itself, once, every
push (DG-479 round 4, the Boss: option A):** every attempt before this round
to decide "already public" from something *local* -- git's own ``--remotes``
pseudo-flag, or this file's own round 3 fix enumerating only configured
remotes' own ``refs/remotes/*`` refs -- could be forged, because it trusted a
*name*, not an answer from the remote. Round 3's own fix still let a hand-made
local ref literally at, say, ``refs/remotes/origin/fake`` (``git update-ref``,
reachable under a name git's tooling happens to also use for real
remote-tracking) self-exclude the exact commit being pushed through it:
``git log <sha> --not refs/remotes/origin/fake`` computes "reachable from the
commit, minus reachable from a ref that already points at that same commit",
which is empty. :func:`_advertised_remote_refs` closes this the only way that
cannot be forged: one ``git ls-remote --refs <push target>`` call, right
before the scan, and ONLY the tips that call returns -- right now, from the
remote itself -- are ever treated as already-public. No local ref, under any
namespace, under any name, is trusted for this any more. A tip the remote
advertises that this repository does not actually have is dropped from the
exclusion set, never treated as a reason to refuse (:func:`_object_existence`,
one batched ``git cat-file --batch-check`` call, not one per tip -- a remote
can advertise thousands of refs). A first push to a brand-new, empty remote
sees ``git ls-remote`` return nothing, so every pushed commit is scanned,
correctly. The call is made exactly once per push (:func:`_advertised_remote_refs`
is called once in :func:`_main_push_multi`), never once per ref, so this adds
one network round trip to a push regardless of how many refs it touches --
bounded by ``DRUNKEN_LS_REMOTE_TIMEOUT_SECONDS`` (default 20s). **A push
target this cannot reach, or that times out or refuses authentication,
REFUSES the push** -- the remote is now the sole authority for "already
public", so not being able to ask it at all can never be read as "assume
nothing is public" or "assume everything is"; both would be a guess.
``credential.interactive=never``-equivalent environment (``GIT_TERMINAL_
PROMPT=0``, a no-op ``GIT_ASKPASS``, ``GCM_INTERACTIVE=Never``, a
batch-mode, short-timeout ``GIT_SSH_COMMAND``) keeps a bad credential or an
unreachable host from ever turning into an interactive hang instead of a
refusal. The push target itself -- a URL, a local path, anything ``git
ls-remote`` accepts -- is never printed by this file, in any message, or in
an exception chain that could later be printed by something else: it can
carry a credential or a token embedded as userinfo
(``https://user:token@host/...``), and ``subprocess.TimeoutExpired``'s own
default text embeds the full command it ran, so the one timeout path raises
with ``from None`` specifically to sever that chain.

The residual, honest limits -- ``git push --no-verify``, a ``core.hooksPath``
pointing elsewhere, a checkout that never ran the installer at all, or any
other tool that simply skips git hooks -- are ``drunken-doctor``'s
``guard.git_hooks`` to report, not this script's to close; see REQ-023 in
``.ai/PRD.md``.

``--push`` (singular ``PRE_COMMIT_FROM_REF``/``TO_REF``) remains for a
caller -- today, every direct test of the per-ref scanning logic itself --
that genuinely has only the one ref pre-commit's own pre-push stage used to
set; it is not what the native hook calls.

DG-480 (a brand-new repository's first push being refused) disappears the
same way: pre-commit's own "all_files" path for a from-scratch push used to
leave both ``PRE_COMMIT_FROM_REF`` and ``PRE_COMMIT_TO_REF`` unset, which
``--push`` correctly refused rather than guess -- but the native hook never
takes that path at all. git always hands it the real local/remote sha for
every ref line on stdin, including a first push (remote sha all-zero), so
``--push-multi`` always has a real ``local_sha`` to scan from. Run by hand
with empty stdin, this still refuses rather than guess what is being
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

#: `git ls-remote` must never be left free to hang this hook waiting on a
#: credential prompt (DG-468 round 2, reviewer item 3; DG-479 round 4 makes
#: this the detection itself, not merely a convenience lookup, so a prompt
#: or a hang here now means the whole push refuses -- see
#: :func:`_advertised_remote_refs`).
_NO_PROMPT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "true",
    "GCM_INTERACTIVE": "Never",
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=5",
}


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


#: How long `git ls-remote` may take before this refuses rather than hang
#: on an unreachable host or a stalled credential prompt (DG-479 round 4,
#: the Boss: option A -- the remote is now the SOLE authority for
#: "already public", so failing to ask it at all must refuse the push,
#: never fall back to guessing). Configurable: a slow host is real.
LS_REMOTE_TIMEOUT_ENV = "DRUNKEN_LS_REMOTE_TIMEOUT_SECONDS"
_DEFAULT_LS_REMOTE_TIMEOUT = 20.0


def _ls_remote_timeout() -> float:
    raw = os.environ.get(LS_REMOTE_TIMEOUT_ENV, "")
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_LS_REMOTE_TIMEOUT
    return value if value > 0 else _DEFAULT_LS_REMOTE_TIMEOUT


def _configured_remote_names() -> List[str]:
    try:
        result = subprocess.run(["git", "remote"], capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git remote could not list configured remotes") from exc
    return [r for r in result.stdout.decode("utf-8", "replace").split() if r]


def _advertised_remote_refs(remote: str) -> dict[str, str]:
    """``ref name -> sha`` for every ref *remote* (a configured name, or
    the literal URL/path git handed the hook as ``$2``) advertises right
    now -- the ONLY authority this file trusts for "already public"
    (DG-479 round 4, the Boss: option A). A local ref merely *named* under
    ``refs/remotes/*`` -- or any other local bookkeeping -- no longer
    matters at all; what the remote itself says, right now, is what
    counts.

    *remote* is never printed by this function, in any message it raises,
    or folded into an exception chain that could later be printed: a push
    or pull URL can carry a credential or a token
    (``https://user:token@host/...``), and ``subprocess.TimeoutExpired``'s
    own default message embeds the full argv it was given -- raising with
    ``from None`` here severs that chain so it can never surface even if
    this exception later escapes somewhere that prints a traceback.
    """
    env = {**os.environ, **_NO_PROMPT_ENV}
    timeout = _ls_remote_timeout()
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--refs", remote],
            capture_output=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ScanFailed(
            f"git ls-remote did not answer within {timeout:.0f}s "
            f"({LS_REMOTE_TIMEOUT_ENV} to change the timeout). Check "
            "connectivity/credentials, then retry."
        ) from None
    except OSError:
        raise ScanFailed("git ls-remote could not be run at all") from None
    if result.returncode != 0:
        raise ScanFailed(
            "git ls-remote could not reach the push target -- check "
            "connectivity/credentials, then retry."
        )
    refs: dict[str, str] = {}
    for line in result.stdout.decode("utf-8", "replace").split("\n"):
        sha, _, ref = line.partition("\t")
        sha = sha.strip()
        ref = ref.strip()
        if sha and ref:
            refs[ref] = sha
    return refs


def _advertised_tips_for_configured_remotes() -> dict[str, str]:
    """Union of every configured remote's own advertised refs -- used by
    the legacy, directly-invoked ``--push`` single-ref mode, which (unlike
    the native hook) is never told exactly which one remote it is pushing
    to. The live hook always knows and calls :func:`_advertised_remote_refs`
    with that one remote directly."""
    merged: dict[str, str] = {}
    for name in _configured_remote_names():
        merged.update(_advertised_remote_refs(name))
    return merged


def _object_existence(shas: set[str]) -> set[str]:
    """Which of *shas* resolve to a real object in this repository, one
    process call for the whole set (DG-479 round 4): a remote can
    advertise thousands of refs, and checking each with its own `git
    cat-file -e` subprocess would reopen exactly the per-item process-spawn
    cost round 3 already fixed for ref lines. A sha the remote advertises
    that this repository does not have is simply dropped from the
    exclusion set -- over-inclusive (scanned anyway), never the reverse.
    """
    if not shas:
        return set()
    try:
        result = subprocess.run(
            ["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
            input=("\n".join(sorted(shas)) + "\n").encode("utf-8"),
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git cat-file --batch-check failed") from exc
    existing: set[str] = set()
    for line in result.stdout.decode("utf-8", "replace").split("\n"):
        fields = line.strip().split()
        if len(fields) >= 2 and fields[1] != "missing":
            existing.add(fields[0])
    return existing


def _ref_specific_commit_hashes(
    to_ref: str, from_ref: str | None, excluded: set[str]
) -> List[str]:
    """Every commit in ``TO --not FROM <every sha the remote advertises>``.

    Excludes anything already reachable from what the remote itself
    advertises right now, on top of ``FROM``: a commit already public on
    another branch is not re-flagged just because this ref's own remote
    tracking has not moved past it. See the module docstring (DG-479
    round 4) for why this is the remote's own live answer, never a local
    bookkeeping ref or git's ``--remotes`` pseudo-flag.
    """
    log_args = ["git", "log", "--format=%H", to_ref, "--not"]
    if from_ref:
        log_args.append(from_ref)
    log_args.extend(sorted(excluded))
    try:
        result = subprocess.run(log_args, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git log could not resolve the push range") from exc
    return [h for h in result.stdout.decode("utf-8", "replace").split("\n") if h]


def _locally_unpublished_commit_hashes(excluded: set[str]) -> List[str]:
    """Every commit reachable from any local branch or tag, not already
    reachable from what the remote itself advertises right now -- regardless
    of which single ref this invocation's own FROM/TO describe (DG-468
    round 2)."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--branches", "--tags", "--not", *sorted(excluded)],
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


def _already_public_tag_shas(advertised: dict[str, str]) -> set[str]:
    """The object id of every tag the remote itself advertises right now
    (DG-479 round 4) -- read straight out of the one ``git ls-remote``
    call already made for this push, never a second network round trip."""
    return {
        sha.lower() for ref, sha in advertised.items() if ref.startswith("refs/tags/")
    }


def _push_sources(
    to_ref: str, from_ref: str | None, advertised: dict[str, str]
) -> List[tuple[str, str]]:
    """Everything this push could make public for the first time.

    *advertised* is every ref the push target itself answers with right
    now (DG-479 round 4, the Boss: option A) -- the sole authority for
    "already public" here; see the module docstring for why this replaced
    git's own ``--remotes`` and every local-ref-based stand-in for it.

    Ref-specific (``TO --not FROM --<advertised tips>``, plus ``TO``'s own
    tag chain when ``TO`` is a tag object) when there is a specific ref to
    look at at all -- ``TO`` as the all-zero SHA is a pure deletion, with
    nothing of its own to add here. Unioned, always, with every commit
    reachable from any local branch or tag not already advertised, and
    every local annotated tag message not already advertised (DG-468
    round 2): see the module docstring for why FROM/TO alone are not
    enough.
    """
    excluded = _object_existence(set(advertised.values()))
    already_public_tags = _already_public_tag_shas(advertised)

    commit_hashes: set[str] = set()
    tag_shas: set[str] = set()

    if to_ref != ZERO_SHA:
        commit_hashes.update(_ref_specific_commit_hashes(to_ref, from_ref, excluded))
        if _object_kind(to_ref) == "tag":
            tag_shas.add(to_ref)
            _verify_tag_resolves_to_commit(to_ref)

    commit_hashes.update(_locally_unpublished_commit_hashes(excluded))
    tag_shas.update(_locally_unpublished_tag_shas())

    sources = _commit_sources(sorted(commit_hashes))
    for sha in sorted(tag_shas):
        sources += _tag_chain_messages(sha, already_public_tags)
    return sources


def _rev_list_union(to_shas: set[str], excluded: set[str]) -> List[str]:
    """Every commit reachable from ANY of *to_shas*, that is not already
    reachable from any sha in *excluded* -- one ``git log`` call over the
    whole union, not one per ref (DG-479 round 3: one invocation per ref
    line made a 500-ref push take over six minutes).

    *excluded* is the caller's own union of every pushed ref's FROM sha
    (already public by definition -- that is what a ref's own remote sha
    means) and every sha the push target itself advertises right now
    (DG-479 round 4) -- never a local bookkeeping ref. Excluding the union
    is exactly as safe as excluding each one individually would have been,
    per ref.
    """
    if not to_shas:
        return []
    log_args = [
        "git",
        "log",
        "--format=%H",
        *sorted(to_shas),
        "--not",
        *sorted(excluded),
    ]
    try:
        result = subprocess.run(log_args, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise ScanFailed("git log could not resolve the push range") from exc
    return [h for h in result.stdout.decode("utf-8", "replace").split("\n") if h]


def _push_sources_multi(
    pairs: List[tuple[str, str]], advertised: dict[str, str]
) -> List[tuple[str, str]]:
    """Everything that EVERY ref line in this push could make public for
    the first time, in one pass (DG-479 round 3), against what the push
    target itself advertises right now as already public (DG-479 round 4,
    the Boss: option A -- see the module docstring).

    *pairs* is every ``(local_sha, remote_sha)`` this push updates,
    deletions (``local_sha == ZERO_SHA``) already filtered out by the
    caller -- a deletion contributes nothing of its own here, same as the
    single-ref ``_push_sources`` above. Each pushed ``local_sha`` that is
    itself a tag object (an annotated tag pushed by name or by sha) has its
    own tag chain walked and scanned, exactly like the single-ref version
    does for its one ``TO``. The always-on global scan (every commit and
    tag unpublished anywhere the push target does not already advertise,
    DG-468 round 2) still runs on top, as defence in depth for a local-only
    ref this push does not even touch.

    This is the fix for the real leak round 2's "first ref only, rely on
    the global scan" design opened: a commit reachable from NOTHING under
    ``refs/heads``/``refs/tags`` (a detached sha pushed directly, a branch
    deleted locally after the commit was made, ``refs/stash``,
    ``refs/original/*``, ...) is invisible to the global scan by
    definition -- it must be named explicitly by the ref line that pushes
    it, and every such ref line must be looked at, not just the first one.
    """
    to_shas = {to for to, _from in pairs}
    from_shas = {frm for _to, frm in pairs if frm and frm != ZERO_SHA}
    advertised_shas = set(advertised.values())
    excluded = _object_existence(from_shas | advertised_shas)
    already_public_tags = _already_public_tag_shas(advertised)

    commit_hashes: set[str] = set(_rev_list_union(to_shas, excluded))
    tag_shas: set[str] = set()
    for to_sha in to_shas:
        if _object_kind(to_sha) == "tag":
            tag_shas.add(to_sha)
            _verify_tag_resolves_to_commit(to_sha)

    commit_hashes.update(_locally_unpublished_commit_hashes(excluded))
    tag_shas.update(_locally_unpublished_tag_shas())

    sources = _commit_sources(sorted(commit_hashes))
    for sha in sorted(tag_shas):
        sources += _tag_chain_messages(sha, already_public_tags)
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


def _report_push_sources(sources: List[tuple[str, str]], ids: List[str]) -> int:
    """Shared by ``--push`` and ``--push-multi``: the same offender report,
    the same ref-naming remediation, the same refusal shape -- only how
    *sources* was gathered differs between the two modes."""
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
        advertised = _advertised_tips_for_configured_remotes()
        sources = _push_sources(to_ref, from_ref, advertised)
    except BinaryTooLarge as exc:
        print(
            f"A changed binary file is too large to scan safely: {exc.path}. "
            "Refusing rather than reading an unbounded blob into memory."
        )
        return 1
    except ScanFailed:
        print(
            "Could not determine which commits this push would make public, "
            "or could not ask the remote what it already has (git ls-remote "
            f"failed or timed out -- {LS_REMOTE_TIMEOUT_ENV} changes the "
            "timeout). Refusing rather than passing an unchecked push."
        )
        return 1

    return _report_push_sources(sources, ids)


def _read_ref_lines_from_stdin() -> tuple[int, List[tuple[str, str]]]:
    """Every ``(local_sha, remote_sha)`` pair git's pre-push protocol hands
    this process on stdin, one line per ref: ``<local ref> <local sha>
    <remote ref> <remote sha>``. Returns ``(lines_seen, pairs)`` -- a line
    that does not even have a local sha (truncated beyond recognition)
    still counts toward *lines_seen*, so a genuinely empty stdin (a shape
    git itself never produces) can still be told apart from one made of
    nothing but malformed lines."""
    lines_seen = 0
    pairs: List[tuple[str, str]] = []
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        lines_seen += 1
        parts = line.split()
        if len(parts) < 2:
            continue  # no local sha on this line at all -- nothing to scan from it
        local_sha = parts[1]
        remote_sha = parts[3] if len(parts) >= 4 else ""
        pairs.append((local_sha, remote_sha))
    return lines_seen, pairs


def _main_push_multi(remote: str | None) -> int:
    """``--push-multi``: every ref line this push updates, read directly
    off this process's own stdin (the native pre-push hook forwards git's
    stdin here untouched) -- the fix for DG-479 round 3's real leak: only
    looking at the first ref line missed a detached, locally-unreachable
    commit pushed by a later line in the same invocation.

    *remote* is exactly ``$2`` the hook itself received from git (the push
    URL git is actually pushing to, not a configured name that may not
    exist for an anonymous ``git push <url> ...``) -- DG-479 round 4, the
    Boss: option A makes it the sole authority for "already public", via
    one ``git ls-remote`` call in :func:`_push_sources_multi`.
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

    if not remote:
        # The native hook always passes $2 (--remote-url); run any other
        # way, there is no safe guess for which remote to ask.
        print(
            "No remote URL given (--remote-url). This runs as the native "
            "pre-push hook, which always passes it; refusing rather than "
            "guessing the push target."
        )
        return 1

    # Zero stdin lines is a real shape git itself produces -- an
    # already-up-to-date push (every ref's local sha already matches its
    # remote sha) reports no ref line at all, not a line with FROM==TO
    # (DG-479 round 4, confirmed by running it). That is correctly
    # "nothing of its own to scan", not "nothing to scan at all": the
    # always-on global scan below still runs, same as a pure-deletion
    # push already does, so a dirty local-only branch unrelated to this
    # push is still caught.
    _, pairs = _read_ref_lines_from_stdin()
    non_deletion_pairs = [(to, frm) for to, frm in pairs if to != ZERO_SHA]

    try:
        advertised = _advertised_remote_refs(remote)
        sources = _push_sources_multi(non_deletion_pairs, advertised)
    except BinaryTooLarge as exc:
        print(
            f"A changed binary file is too large to scan safely: {exc.path}. "
            "Refusing rather than reading an unbounded blob into memory."
        )
        return 1
    except ScanFailed:
        print(
            "Could not reach the push target to determine what it already "
            "has (git ls-remote failed or timed out -- "
            f"{LS_REMOTE_TIMEOUT_ENV} changes the timeout), or could not "
            "determine which commits this push would make public. Check "
            "connectivity/credentials and retry; refusing rather than "
            "passing an unchecked push."
        )
        return 1

    return _report_push_sources(sources, ids)


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
        "--push-multi",
        action="store_true",
        help=(
            "every ref line read from this process's own stdin, one git "
            "rev-list call over their union, against what --remote-url "
            "itself advertises (the native pre-push hook, "
            "scripts/git_hooks/pre-push)"
        ),
    )
    parser.add_argument(
        "--remote-url",
        default=None,
        help=(
            "the push target, exactly $2 as git handed it to the hook -- "
            "the sole authority --push-multi trusts for what is already "
            "public (DG-479 round 4)"
        ),
    )
    parser.add_argument(
        "--require-ids",
        action="store_true",
        help="fail when there are no ids to check against (CI)",
    )
    args = parser.parse_args(argv)

    if args.push:
        return _main_push()
    if args.push_multi:
        return _main_push_multi(args.remote_url)

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
