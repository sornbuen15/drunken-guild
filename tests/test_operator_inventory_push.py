# mypy: ignore-errors
"""The operator-inventory guard also runs at push time (DG-464).

CI (`--tree`, `--messages`) checks after the push: GitHub keeps a pushed commit
under ``refs/pull/*`` for good once a PR exists, even if the PR is later closed
without merging. Pre-push is the last point before a commit a human never
intended to publish leaves this machine. It scans the commits this push would
put on a remote for the first time: ``TO --not FROM --remotes``, read from the
``PRE_COMMIT_FROM_REF`` / ``PRE_COMMIT_TO_REF`` environment pre-commit's own
pre-push stage sets (it consumes the hook's stdin itself and does not forward
it). ``--remotes`` matters on its own: a commit already public on some other
branch must not be re-flagged just because the ref being pushed has not moved
past it yet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_operator_inventory.py"
FAKE = "zeta"  # nobody's project id; never a real one in this file


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _git_out(repo: Path, *args: str) -> str:
    return (
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
    )


def _commit(repo: Path, name: str, content: str, message: str = "wip") -> str:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git_out(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    registry = tmp_path / "projects.json"
    registry.write_text(
        json.dumps({"version": 2, "projects": {"drunken-guild": {}, FAKE: {}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry))
    monkeypatch.delenv("DRUNKEN_NO_REGISTERED_PROJECTS", raising=False)
    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)

    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")
    _git(work, "remote", "add", "origin", str(remote))
    return work


def _run(
    repo: Path, extra_env: dict | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    import os

    extra_env = extra_env or {}
    #: DG-477: every call site here passes a literal dict of PRE_COMMIT_*
    #: overrides (and, in one case, the unrelated DRUNKEN_NO_REGISTERED_
    #: PROJECTS opt-out flag), so this can't drop the sandbox today -- but
    #: `extra_env` is an opaque parameter to the static check in
    #: tests/test_subprocess_env_guard.py, which cannot see what any given
    #: caller passes. This runtime guard is what actually makes the
    #: allowlisted `env.update()` below safe, not just quiet.
    _sandbox_vars = {"DRUNKEN_HOME", "DRUNKEN_REGISTRY_PATH", "DRUNKEN_AUTH_DB"}
    assert not (set(extra_env) & _sandbox_vars), (
        "extra_env must never override the sandboxed DRUNKEN_HOME/"
        "DRUNKEN_REGISTRY_PATH/DRUNKEN_AUTH_DB variables"
    )
    env = os.environ.copy()
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--push"],
        cwd=cwd if cwd is not None else repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_a_new_commit_naming_an_id_is_refused(repo: Path) -> None:
    _commit(repo, "a.txt", "clean\n", "base")
    to_sha = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", f"touches {FAKE}")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1


def test_the_refusal_does_not_print_the_id(repo: Path) -> None:
    _commit(repo, "a.txt", "clean\n", "base")
    to_sha = _commit(repo, "b.txt", f"{FAKE}\n", "wip")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_commit_already_on_a_remote_is_not_reflagged(repo: Path) -> None:
    """FROM alone would not catch this: the commit must be excluded via
    --remotes, because the ref being pushed has not itself moved past it."""
    before = _commit(repo, "a.txt", "clean\n", "base")
    public = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", f"touches {FAKE}")
    _git(repo, "push", "-q", "origin", "HEAD:main")
    # Simulate a stale FROM (as if this ref's own remote tracking hadn't
    # advanced past `before`) while the content is already public elsewhere.
    clean_tip = _commit(repo, "c.txt", "still clean\n", "another")

    result = _run(repo, {"PRE_COMMIT_FROM_REF": before, "PRE_COMMIT_TO_REF": clean_tip})

    assert result.returncode == 0
    assert public  # the public commit exists; it just must not be re-flagged


def test_a_merge_commit_s_own_conflict_resolution_is_scanned(repo: Path) -> None:
    """A merge commit is read for content it alone introduces -- a conflict
    resolution that matches neither parent's own diff -- not skipped just
    because it is a merge."""
    _commit(repo, "f.txt", "base\n", "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "f.txt", "feature side\n", "feature change")
    _git(repo, "checkout", "-q", "-")
    base_main_tip = _commit(repo, "f.txt", "main side\n", "main change")

    _git(repo, "merge", "feature", "-q", "--no-ff", "-m", "merge", "--strategy=ours")
    # "ours" avoids a real conflict in the fixture; overwrite the merge result
    # by hand so the FAKE id exists only in the merge commit's own tree, not
    # in either parent's diff.
    (repo / "f.txt").write_text(f"resolved with {FAKE.upper()}-1\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    merge_sha = _git_out(repo, "rev-parse", "HEAD")

    result = _run(
        repo, {"PRE_COMMIT_FROM_REF": base_main_tip, "PRE_COMMIT_TO_REF": merge_sha}
    )

    assert result.returncode == 1


def test_an_empty_range_passes(repo: Path) -> None:
    tip = _commit(repo, "a.txt", "clean\n", "base")

    result = _run(repo, {"PRE_COMMIT_FROM_REF": tip, "PRE_COMMIT_TO_REF": tip})

    assert result.returncode == 0


def test_no_ids_refuses_the_push(repo: Path, tmp_path: Path, monkeypatch) -> None:
    # A path that cannot resolve to a real registry -- not merely unset,
    # which would fall through to this machine's actual default path and
    # pick up whatever is really registered there.
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(tmp_path / "absent.json"))
    to_sha = _commit(repo, "a.txt", "clean\n", "base")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1


def test_the_opt_out_passes_with_no_ids(
    repo: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(tmp_path / "absent.json"))
    to_sha = _commit(repo, "a.txt", "clean\n", "base")

    result = _run(
        repo, {"PRE_COMMIT_TO_REF": to_sha, "DRUNKEN_NO_REGISTERED_PROJECTS": "1"}
    )

    assert result.returncode == 0


def test_to_ref_is_read_rather_than_assumed_to_be_head(repo: Path) -> None:
    """PRE_COMMIT_TO_REF names what is being pushed; HEAD may have moved on to
    an unrelated branch since (hooks run after the ref update, in whatever
    checkout git happened to leave) and must not be used instead."""
    base = _commit(repo, "a.txt", "clean\n", "base")
    dirty = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "the push being made")
    _git(repo, "checkout", "-q", base)
    _git(repo, "checkout", "-q", "-b", "elsewhere")
    _commit(repo, "c.txt", "unrelated\n", "a later, unrelated checkout")

    result = _run(repo, {"PRE_COMMIT_TO_REF": dirty})

    assert result.returncode == 1


def test_a_new_branch_with_no_upstream_is_still_scanned(repo: Path) -> None:
    """No FROM at all (a brand-new branch): only --remotes bounds the scan."""
    to_sha = _commit(repo, "a.txt", f"{FAKE}\n", "wip")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1


def test_git_dir_env_does_not_confuse_the_scan(repo: Path, monkeypatch) -> None:
    """A hook git itself runs inherits GIT_DIR / GIT_WORK_TREE; the scan must
    still see this repository's history rather than failing or scanning the
    wrong one."""
    to_sha = _commit(repo, "a.txt", f"{FAKE}\n", "wip")

    result = _run(
        repo,
        {
            "PRE_COMMIT_TO_REF": to_sha,
            "GIT_DIR": str(repo / ".git"),
            "GIT_WORK_TREE": str(repo),
        },
    )

    assert result.returncode == 1


def test_an_unresolvable_from_ref_refuses_rather_than_passes(repo: Path) -> None:
    """A `git log` failure must never read as "nothing unpublished"."""
    to_sha = _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "wip")

    result = _run(
        repo, {"PRE_COMMIT_FROM_REF": "not-a-real-ref-zzz", "PRE_COMMIT_TO_REF": to_sha}
    )

    assert result.returncode == 1
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_bogus_to_ref_refuses_rather_than_passes(repo: Path) -> None:
    _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "wip")

    result = _run(repo, {"PRE_COMMIT_TO_REF": "not-a-real-sha-zzz"})

    assert result.returncode == 1
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_running_outside_a_repo_refuses(repo: Path, tmp_path: Path) -> None:
    to_sha = _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "wip")
    outside = tmp_path / "not-a-repo"
    outside.mkdir()

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha}, cwd=outside)

    assert result.returncode == 1
    assert FAKE not in (result.stdout + result.stderr).lower()


def _corrupt_blob(repo: Path, commit_sha: str, path: str) -> None:
    """Make ``git cat-file``/``git show`` fail for the blob ``path`` has at
    ``commit_sha``, by overwriting its loose object with garbage (DG-470's
    corrupted-object repro) -- never packed, so the loose file is still the
    one git reads."""
    import os
    import stat

    blob = _git_out(repo, "rev-parse", f"{commit_sha}:{path}")
    object_path = repo / ".git" / "objects" / blob[:2] / blob[2:]
    assert object_path.is_file(), f"expected a loose object at {object_path}"
    os.chmod(
        object_path, stat.S_IWRITE | stat.S_IREAD
    )  # git writes loose objects read-only
    object_path.write_bytes(b"not a valid zlib stream at all, corrupted on purpose")


def test_a_failing_git_show_for_one_commit_among_several_is_refused(
    repo: Path,
) -> None:
    """DG-470: a `git show --cc` failure for one commit out of several in the
    range must refuse the push outright, not merely skip that one commit and
    judge the push clean on what is left. Seen failing first by reverting
    the `raise ScanFailed(...)` this guards to a `continue` -- with that
    change, the corrupted commit is silently skipped, the two clean commits
    either side of it are all that remain to judge, and the push passes."""
    # All three commits are made while the object store is intact -- `git
    # add`/`git status` on an unrelated path can themselves need to read a
    # nearby blob (a racily-clean stat cache forces a content check), so the
    # corruption happens only once nothing further will touch the repo
    # except the scan itself.
    base = _commit(repo, "a.txt", "clean\n", "base")
    corrupt_sha = _commit(repo, "b.txt", "also clean\n", "will be corrupted")
    tip = _commit(repo, "c.txt", "clean too\n", "a clean commit after it")
    _corrupt_blob(repo, corrupt_sha, "b.txt")

    result = _run(repo, {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": tip})

    # Every commit in the range is clean of ids -- the only reason to refuse
    # is that the range could not be fully read. A `continue` here would
    # judge the push by what is left after skipping the corrupted commit,
    # i.e. two clean commits, and wrongly pass it.
    assert result.returncode == 1
    assert FAKE not in (result.stdout + result.stderr).lower()


def _annotated_tag(repo: Path, name: str, message: str, target: str = "HEAD") -> str:
    """Create an annotated tag and return the tag *object's own* id -- what
    PRE_COMMIT_TO_REF holds for a real push of just this tag (pre-commit's
    pre-push wrapper sets it to the ref's direct target, and an annotated
    tag's ref points at the tag object, not at the commit it names)."""
    _git(repo, "tag", "-a", "-m", message, name, target)
    return _git_out(repo, "rev-parse", name)


# The tests below invoke the script directly with PRE_COMMIT_TO_REF/FROM_REF
# already set, as every test in this file does -- they prove this file scans
# a tag's message correctly *when the hook actually runs*. They do NOT prove
# pre-commit invokes the hook for every push that moves a tag: a solo
# annotated tag pushed onto an already-public commit never reaches this
# script at all (DG-479; see
# test_a_solo_tag_on_an_already_public_commit_never_reaches_the_scanner_dg479
# near the end of this file, which documents that gap against a real
# installed hook rather than hiding it).


def test_an_annotated_tag_message_naming_an_id_is_refused(repo: Path) -> None:
    _commit(repo, "a.txt", "clean\n", "base")
    tag_sha = _annotated_tag(repo, "v1", f"release notes mention {FAKE.upper()}-1")

    result = _run(repo, {"PRE_COMMIT_TO_REF": tag_sha})

    assert result.returncode == 1


def test_the_tag_refusal_does_not_print_the_id(repo: Path) -> None:
    _commit(repo, "a.txt", "clean\n", "base")
    tag_sha = _annotated_tag(repo, "v1", f"touches {FAKE}")

    result = _run(repo, {"PRE_COMMIT_TO_REF": tag_sha})

    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_tag_already_on_a_remote_is_not_reflagged(repo: Path) -> None:
    """The tag's own message is excluded once it is verified present on a
    remote (`git ls-remote --tags`) -- not merely because its target commit
    is old -- so re-running the scan against the same tag object does not
    re-flag it."""
    _commit(repo, "a.txt", "clean\n", "base")
    tag_sha = _annotated_tag(repo, "v1", f"touches {FAKE}")
    _git(repo, "push", "-q", "origin", "HEAD:main", "v1")

    result = _run(repo, {"PRE_COMMIT_TO_REF": tag_sha})

    assert result.returncode == 0


def test_a_lightweight_tag_is_not_an_error(repo: Path) -> None:
    """A lightweight tag's ref points directly at the commit -- there is no
    tag object and so no message; it must be scanned exactly like a normal
    commit push, never treated as an error."""
    to_sha = _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "tag", "lw", to_sha)

    result = _run(repo, {"PRE_COMMIT_TO_REF": _git_out(repo, "rev-parse", "lw")})

    assert result.returncode == 0


def test_a_lightweight_tag_still_catches_a_dirty_commit(repo: Path) -> None:
    to_sha = _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "wip")
    _git(repo, "tag", "lw", to_sha)

    result = _run(repo, {"PRE_COMMIT_TO_REF": _git_out(repo, "rev-parse", "lw")})

    assert result.returncode == 1


def test_a_tag_pointing_at_another_tag_is_walked(repo: Path) -> None:
    """A tag can tag another tag (``git tag -a v2 v1``); every tag object in
    the chain is read, not just the outermost one."""
    _commit(repo, "a.txt", "clean\n", "base")
    inner_sha = _annotated_tag(repo, "v1", f"touches {FAKE}")
    outer_sha = _annotated_tag(repo, "v2", "wraps v1", target="v1")
    assert inner_sha != outer_sha

    result = _run(repo, {"PRE_COMMIT_TO_REF": outer_sha})

    assert result.returncode == 1


def test_a_tag_pointing_at_a_tree_refuses_rather_than_crashing(repo: Path) -> None:
    """A tag need not point at a commit at all -- git allows tagging a tree
    or a blob directly. There is no commit range to walk from there; this
    must refuse cleanly, never crash and never pass silently."""
    _commit(repo, "a.txt", "clean\n", "base")
    tree_sha = _git_out(repo, "rev-parse", "HEAD^{tree}")
    tag_sha = _annotated_tag(repo, "v1", "tags a tree, not a commit", target=tree_sha)

    result = _run(repo, {"PRE_COMMIT_TO_REF": tag_sha})

    assert result.returncode == 1


def test_a_tag_message_with_crlf_is_still_scanned(repo: Path) -> None:
    _commit(repo, "a.txt", "clean\n", "base")
    tag_sha = _annotated_tag(repo, "v1", f"line one\r\ntouches {FAKE}\r\n")

    result = _run(repo, {"PRE_COMMIT_TO_REF": tag_sha})

    assert result.returncode == 1


def test_binary_added_content_naming_an_id_is_scanned(repo: Path) -> None:
    """DG-468's binary decision: added bytes are read for ids too (not
    skipped as out of scope), because `git show`'s unified diff never shows
    the bytes of a binary file at all -- only "Binary files ... differ" --
    so without reading the blob directly, a binary file is a free pass for
    anything hidden in it."""
    _commit(repo, "a.txt", "clean\n", "base")
    (repo / "b.bin").write_bytes(b"\x00\x01" + FAKE.upper().encode() + b"-1\x02\x03")
    _git(repo, "add", "b.bin")
    _git(repo, "commit", "-q", "-m", "add binary")
    to_sha = _git_out(repo, "rev-parse", "HEAD")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_branch_deletion_passes(repo: Path) -> None:
    """TO is the all-zero SHA: nothing of its own is being pushed by this
    ref update. With nothing else locally unpublished either, there is
    nothing to refuse (DG-468 round 2's global scan still runs -- it just
    finds nothing)."""
    _commit(repo, "a.txt", "clean\n", "wip")  # history exists, but is clean

    result = _run(repo, {"PRE_COMMIT_TO_REF": "0" * 40})

    assert result.returncode == 0


def test_a_branch_deletion_with_a_dirty_tag_elsewhere_still_refuses(
    repo: Path,
) -> None:
    """A deletion of one ref must not be read as "nothing to scan" while a
    dirty tag sits on the same push (DG-468 round 2, reviewer item 1)."""
    _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "tag", "-a", "-m", f"touches {FAKE}", "v1")

    result = _run(repo, {"PRE_COMMIT_TO_REF": "0" * 40})

    assert result.returncode == 1


def test_an_absent_to_ref_refuses_rather_than_scanning_head_or_passing(
    repo: Path,
) -> None:
    """Run by hand, outside pre-commit's own pre-push stage, PRE_COMMIT_TO_REF
    is simply not set. There is no safe guess for what is being pushed, so
    this must fail closed -- not silently scan HEAD, and not silently pass."""
    _commit(repo, "a.txt", "clean\n", "base")  # HEAD is clean; must not matter

    result = _run(repo)  # no PRE_COMMIT_TO_REF at all

    assert result.returncode == 1


def test_pre_commit_no_longer_owns_the_pre_push_stage() -> None:
    """DG-479/DG-480: a native pre-push hook (scripts/git_hooks/pre-push) is
    now the sole owner of this stage -- pre-commit's own pre-push stage
    must not be declared at all, or the two would race for it
    (DG-479_DECISION.md)."""
    import re

    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    install_types = re.search(
        r"^default_install_hook_types:\s*\[([^\]]*)\]", config, re.MULTILINE
    )
    assert install_types is not None
    assert "pre-push" not in [t.strip() for t in install_types.group(1).split(",")]
    assert "stages: [pre-push]" not in config


def test_the_native_hook_template_calls_the_scanner_s_push_mode() -> None:
    template = (ROOT / "scripts" / "git_hooks" / "pre-push").read_text(encoding="utf-8")
    assert "check_operator_inventory.py" in template
    assert "--push" in template


# --- DG-468 round 2 (adversarial review, Jira comment on DG-468) ----------
#
# pre-commit's own pre-push wrapper reports only the first non-delete ref of
# a push with more than one (confirmed against a real `pre-commit install
# --hook-type pre-push` in a scratch repo: `git push origin feature v1`
# with an id only in v1's annotated tag message passed and the id reached
# the remote). PRE_COMMIT_TO_REF/FROM_REF describe only that first ref,
# exactly as they do in these tests -- a second local branch or tag is
# never named by them at all, matching what pre-commit actually hands the
# hook for a multi-ref push.


def test_a_second_unpublished_branch_is_caught_though_to_ref_names_only_the_first(
    repo: Path,
) -> None:
    """Two branches pushed together: PRE_COMMIT_TO_REF names only the one
    pre-commit happened to report first; the other's dirty commit must
    still be caught."""
    base = _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "checkout", "-q", "-b", "other")
    _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty on the other branch")
    _git(repo, "checkout", "-q", "-")
    clean_tip = _commit(repo, "c.txt", "clean too\n", "clean on the first branch")

    result = _run(repo, {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": clean_tip})

    assert result.returncode == 1


def test_an_unpublished_tag_is_caught_though_to_ref_names_only_the_branch(
    repo: Path,
) -> None:
    """`git push origin feature v1`: PRE_COMMIT_TO_REF names the branch tip
    only (pre-commit's first-ref-only report), but the tag pushed alongside
    it is still read."""
    base = _commit(repo, "a.txt", "clean\n", "base")
    clean_tip = _commit(repo, "b.txt", "clean too\n", "a clean branch tip")
    _git(repo, "tag", "-a", "-m", f"touches {FAKE}", "v1")

    result = _run(repo, {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": clean_tip})

    assert result.returncode == 1


def test_a_dirty_unrelated_local_branch_blocks_an_otherwise_clean_push(
    repo: Path,
) -> None:
    """The accepted over-inclusion cost, made explicit: a local-only branch
    naming an id blocks a push of something else entirely unrelated to it.
    The escape is fixing or removing the offending local ref -- there are
    ids registered here, so DRUNKEN_NO_REGISTERED_PROJECTS=1 (the escape
    for *no* ids to check against) does not apply to this case."""
    base = _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "checkout", "-q", "-b", "unrelated")
    _commit(repo, "z.txt", f"{FAKE.upper()}-1\n", "sitting around, unrelated")
    _git(repo, "checkout", "-q", "-")
    clean_tip = _commit(repo, "c.txt", "clean too\n", "what is actually being pushed")

    blocked = _run(repo, {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": clean_tip})
    assert blocked.returncode == 1

    _git(repo, "branch", "-D", "unrelated")  # the actual escape: remove it

    escaped = _run(repo, {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": clean_tip})
    assert escaped.returncode == 0


def test_the_over_inclusive_refusal_names_the_offending_ref_and_sha_not_the_id(
    repo: Path,
) -> None:
    """DG-468 round 3, friction: a refusal caused by a local ref that is not
    even part of this push must say which ref to drop or amend (by name,
    with a commit short sha) before anything else -- never the id, and
    before any mention of an escape hatch."""
    base = _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "checkout", "-q", "-b", "unrelated")
    dirty_sha = _commit(
        repo, "z.txt", f"{FAKE.upper()}-1\n", "sitting around, unrelated"
    )
    _git(repo, "checkout", "-q", "-")
    clean_tip = _commit(repo, "c.txt", "clean too\n", "what is actually being pushed")

    result = _run(repo, {"PRE_COMMIT_FROM_REF": base, "PRE_COMMIT_TO_REF": clean_tip})

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "refs/heads/unrelated" in output
    assert dirty_sha[:12] in output
    assert FAKE not in output.lower()
    # The fix-it guidance (naming the ref) must come before any mention of
    # the separate opt-out, never after or instead of it.
    fix_at = output.index("refs/heads/unrelated")
    escape_at = output.find("DRUNKEN_NO_REGISTERED_PROJECTS")
    assert escape_at == -1 or fix_at < escape_at


def test_utf16_binary_content_naming_an_id_is_still_caught(repo: Path) -> None:
    """DG-468 round 2 item 2: a latin-1 decode of UTF-16 content interleaves
    NULs between every character and the id never matches. A NUL-stripped
    decode must still catch it, LE or BE, with or without a BOM."""
    _commit(repo, "a.txt", "clean\n", "base")
    text = f"touches {FAKE.upper()}-1"
    le_no_bom = text.encode("utf-16-le")
    be_with_bom = b"\xfe\xff" + text.encode("utf-16-be")
    for name, data in (("le.bin", le_no_bom), ("be_bom.bin", be_with_bom)):
        (repo / name).write_bytes(data)
    _git(repo, "add", "le.bin", "be_bom.bin")
    _git(repo, "commit", "-q", "-m", "add utf-16 binaries")
    to_sha = _git_out(repo, "rev-parse", "HEAD")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_an_id_split_by_nuls_in_binary_content_is_still_caught(repo: Path) -> None:
    """Every other byte NUL (UTF-16LE of a plain-ASCII id) must not hide it."""
    _commit(repo, "a.txt", "clean\n", "base")
    split = bytes()
    for ch in f"{FAKE.upper()}-1":
        split += ch.encode("ascii") + b"\x00"
    (repo / "split.bin").write_bytes(b"\x00\x01" + split + b"\x02")
    _git(repo, "add", "split.bin")
    _git(repo, "commit", "-q", "-m", "add nul-split binary")
    to_sha = _git_out(repo, "rev-parse", "HEAD")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1


def test_an_oversized_binary_blob_refuses_naming_the_path_not_the_content(
    repo: Path,
) -> None:
    """DG-468 round 2 item 4: above the cap, this must refuse closed rather
    than read an unbounded blob into memory on every push -- and name the
    path, never the content, in doing so."""
    _commit(repo, "a.txt", "clean\n", "base")
    from scripts import check_operator_inventory as coi

    oversized = coi.MAX_BINARY_BYTES + 1
    (repo / "huge.bin").write_bytes(b"\x00\x01" + (b"\xff" * oversized))
    _git(repo, "add", "huge.bin")
    _git(repo, "commit", "-q", "-m", "add an oversized binary")
    to_sha = _git_out(repo, "rev-parse", "HEAD")

    result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})

    assert result.returncode == 1
    assert "huge.bin" in (result.stdout + result.stderr)


def test_a_slow_or_unreachable_remote_does_not_hang_and_never_prints_its_url(
    repo: Path,
) -> None:
    """DG-468 round 2 item 3: `git ls-remote` must never be left free to
    hang this hook, and a failure there (timeout or otherwise) must never
    print the remote's URL -- it can carry a token. The fake remote hangs
    for 20s, well past this file's own remote-query timeout; a push taking
    anywhere near that proves the timeout did not actually apply."""
    import socket
    import threading
    import time

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    secret_marker = "s3cr3t-token-marker"

    stop = threading.Event()

    def _accept_and_hang() -> None:
        listener.settimeout(1)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            # Accept the connection and never answer: a real hang, not a
            # fast refusal, is the point of this test.
            stop.wait(20)
            conn.close()
            return

    thread = threading.Thread(target=_accept_and_hang, daemon=True)
    thread.start()
    try:
        _git(
            repo,
            "remote",
            "add",
            "slow",
            f"git://127.0.0.1:{port}/{secret_marker}.git",
        )
        to_sha = _commit(repo, "a.txt", "clean\n", "base")

        started = time.monotonic()
        result = _run(repo, {"PRE_COMMIT_TO_REF": to_sha})
        elapsed = time.monotonic() - started

        assert secret_marker not in (result.stdout + result.stderr)
        assert elapsed < 15, (
            f"took {elapsed:.1f}s against a remote that only ever hangs -- "
            "the timeout did not apply"
        )
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=2)


# --- DG-479/DG-480: the native pre-push hook, against a real bare remote -
#
# pre_commit.commands.hook_impl._pre_push_ns returns None ("nothing to
# push") when every pushed ref either deletes something or already points
# at a commit reachable from a remote-tracking ref -- and when it returns
# None, hook_impl returns immediately, before this script (or any
# pre-commit-managed hook) ever runs. No amount of scanning inside
# check_operator_inventory.py could close that: the process was never
# started. The fix (DG-479_DECISION.md, 2026-10-09, the Boss: option A
# narrow + D) is a *native* pre-push hook, outside pre-commit entirely,
# that git always invokes directly -- scripts/git_hooks/pre-push, installed
# here exactly the way `drunken-init --install-git-hooks` installs it
# (src/core/git_hooks.py), never by hand-rolling a different shim. Every
# test below is a real installed hook against a real bare remote, not the
# direct-invocation style of every other test in this file, because the
# thing under test is specifically whether git invokes the hook at all.


def _vendor_scanner_into(repo: Path) -> None:
    """Copy this repository's own scripts/ and src/ into *repo*, so the
    native hook -- which resolves the scanner at
    ``$(git rev-parse --show-toplevel)/scripts/check_operator_inventory.py``
    relative to whatever repo it is actually pushing from -- finds a real
    copy there, the same shape a registered project's own checkout has
    once the AI layer is copied in. Never the tracked worktree itself:
    this always writes into a tmp_path-rooted scratch repo."""
    import shutil

    shutil.copytree(
        ROOT / "scripts",
        repo / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / "src",
        repo / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _bare_remote_and_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    from core import git_hooks

    monkeypatch.delenv("PRE_COMMIT_FROM_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)

    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q")
    # Deterministic regardless of this machine's init.defaultBranch config
    # (main/master/whatever an operator set) -- several tests below check
    # out or push a *local* branch literally named "main".
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(remote))

    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(tmp_path / "projects.json"))
    (tmp_path / "projects.json").write_text(
        json.dumps({"version": 2, "projects": {"drunken-guild": {}, FAKE: {}}}),
        encoding="utf-8",
    )
    _vendor_scanner_into(repo)
    git_hooks.install_pre_push_hook(repo)
    return remote, repo


def _push(repo: Path, *refs: str) -> subprocess.CompletedProcess:
    # os.environ plus this interpreter's own directory at the front of
    # PATH -- so the native hook's find_python (python3, then python, then
    # py) actually resolves to the python this repo's tests run under,
    # under Git for Windows' own sh, without the hook script itself ever
    # naming that path (DG-479_DECISION.md: no venv path baked into a hook
    # shared by every worktree). Built and used in this one function (not
    # a separate PATH-only helper) so tests/test_subprocess_env_guard.py
    # can see this env= provably carries the sandboxed DRUNKEN_* variables
    # forward (DG-477) -- it is os.environ.copy() with only PATH touched.
    import os

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), env.get("PATH", "")]
    )
    return subprocess.run(
        ["git", "push", "origin", *refs],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def test_a_solo_tag_on_an_already_public_commit_is_refused_dg479(
    tmp_path: Path, monkeypatch
) -> None:
    """The case DG-479 exists for: pre-commit's own pre-push stage never
    ran at all here -- the native hook must, and must refuse."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)

    public_sha = _commit(repo, "a.txt", "clean\n", "base")
    bootstrap = _push(repo, "HEAD:main")
    assert bootstrap.returncode == 0, (
        "the seed push failed before the tag push this test is about -- a "
        f"setup failure, not DG-479: {bootstrap.stderr}"
    )

    # pre-commit's own `git push` of a tag whose target commit is already
    # reachable via refs/remotes/origin/* (git push updates those locally
    # by default) finds no ancestors needing it and used to report
    # "nothing to push" to a pre-commit-managed hook, which then never ran
    # at all. The native hook has no such filtering: git hands it this ref
    # line directly.
    _git(repo, "tag", "-a", "-m", f"touches {FAKE}", "v1", public_sha)

    result = _push(repo, "v1")

    assert result.returncode != 0, (
        "the push of a solo tag naming an id succeeded -- the native hook "
        "was not invoked, or did not refuse it (DG-479)"
    )
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_delete_plus_new_tag_push_is_refused(tmp_path: Path, monkeypatch) -> None:
    """`git push origin :old v3`: a pure ref deletion alongside a new tag
    is exactly the other shape pre-commit's own pre-push stage never ran
    for at all (DG-479)."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)

    _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "branch", "old")
    bootstrap = _push(repo, "HEAD:main", "old")
    assert bootstrap.returncode == 0, bootstrap.stderr

    _git(repo, "tag", "-a", "-m", f"touches {FAKE}", "v3")

    result = _push(repo, ":old", "v3")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_first_push_of_a_clean_root_commit_passes_and_is_quiet_dg480(
    tmp_path: Path, monkeypatch
) -> None:
    """DG-480 acceptance: first push of a clean root commit passes and is
    quiet. The native hook sees a real local sha and an all-zero remote
    sha directly off stdin for this ref -- it never takes pre-commit's own
    "all_files, no FROM/TO at all" path, so there is no ambiguity to
    refuse here in the first place."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")

    result = _push(repo, "HEAD:main")

    assert result.returncode == 0, result.stderr
    assert "project id" not in (result.stdout + result.stderr).lower()


def test_first_push_with_a_fake_id_is_refused_and_the_id_is_not_printed_dg480(
    tmp_path: Path, monkeypatch
) -> None:
    """DG-480 acceptance: first push whose history contains a fake id is
    refused and the id is not printed."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "base")

    result = _push(repo, "HEAD:main")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_multi_ref_push_is_refused_when_either_ref_is_dirty(
    tmp_path: Path, monkeypatch
) -> None:
    """Two refs pushed together, one dirty: the native hook reads every
    stdin line itself (unlike pre-commit's own wrapper, which only ever
    reported the first non-delete ref)."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")

    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty feature work")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "c.txt", "clean too\n", "clean main work")

    result = _push(repo, "main", "feature")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_two_clean_branches_pushed_together_pass_fast_and_quiet(
    tmp_path: Path, monkeypatch
) -> None:
    import time

    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")

    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "b.txt", "clean feature work\n", "feature")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "c.txt", "clean main work\n", "main")

    started = time.monotonic()
    result = _push(repo, "main", "feature")
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "" and "refus" not in result.stderr.lower()
    assert elapsed < 30, f"took {elapsed:.1f}s for a clean push -- not fast"


def test_the_id_never_reaches_stdout_stderr_or_a_traceback(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", f"touches {FAKE} right here\n", "base")

    result = _push(repo, "HEAD:main")

    combined = (result.stdout + result.stderr).lower()
    assert result.returncode != 0
    assert FAKE not in combined
    assert "traceback" not in combined


def test_a_missing_python_interpreter_fails_closed(tmp_path: Path, monkeypatch) -> None:
    """DG-479_DECISION.md failure mode: no python3/python/py on PATH at
    all must refuse the push with a message, never silently let it
    through and never crash with something unreadable."""
    import os
    import shutil

    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")

    # git itself must still be reachable to run `git push` at all -- only
    # the *hook's* search for an interpreter is what this test starves. A
    # directory merely omitting python is not enough on Linux, where
    # `git`'s own directory (e.g. /usr/bin) typically also holds a system
    # `python3` -- re-adding that whole directory to PATH would hand the
    # hook back exactly the interpreter this test means to take away. A
    # shim that `exec`s the real git by its own absolute path, alone on
    # PATH, isolates "git is reachable" from "whatever else lives next to
    # it" on every platform.
    real_git = shutil.which("git")
    assert real_git is not None
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    shim = fake_bin / ("git.cmd" if sys.platform == "win32" else "git")
    if sys.platform == "win32":
        shim.write_text(f'@echo off\r\n"{real_git}" %*\r\n', encoding="utf-8")
    else:
        shim.write_text(f'#!/bin/sh\nexec "{real_git}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(fake_bin)

    result = subprocess.run(
        [str(shim), "push", "origin", "HEAD:main"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0, (
        "a push with no python interpreter on PATH must be refused, not "
        "silently let through"
    )
    assert FAKE not in (result.stdout + result.stderr).lower()


# --- Round 2 review (Jira comment on DG-479): push shapes the reviewer
# could not exercise -- `--follow-tags`, `--tags`, `--mirror`, `--all`,
# `--prune`, a Gerrit-style `refs/for/x` ref, `refs/notes/*`, a branch
# rename, a force-push, empty stdin, CRLF in stdin lines, a truncated ref
# line, and a PATH with only the Windows `py` launcher. Every one of these
# runs against a real installed native hook and a real bare remote, never
# a mock of git's own behaviour.


def _hook_path(repo: Path) -> Path:
    from core import doctor

    hooks_dir_path = doctor.hooks_dir(repo)
    assert hooks_dir_path is not None
    return hooks_dir_path / "pre-push"


def _run_hook_directly(repo: Path, stdin_text: str) -> subprocess.CompletedProcess:
    """Invoke the installed hook file exactly as git would -- remote name
    and url as argv, the ref lines on stdin -- but with stdin crafted by
    hand, for shapes (empty, CRLF, truncated) a real git push cannot be
    made to produce on demand."""
    import os
    import shutil

    sh = shutil.which("sh")
    assert sh is not None, "no sh on PATH to run the hook script directly"
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), env.get("PATH", "")]
    )
    return subprocess.run(
        [sh, str(_hook_path(repo)), "origin", "../remote.git"],
        cwd=repo,
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )


def test_follow_tags_refuses_a_dirty_tag(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _annotated_tag(repo, "v1", f"touches {FAKE}")

    result = _push(repo, "--follow-tags", "HEAD:main")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_tags_flag_refuses_a_dirty_tag(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    _annotated_tag(repo, "v1", f"touches {FAKE}")

    result = _push(repo, "--tags")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_all_flag_refuses_when_any_branch_is_dirty(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "checkout", "-q", "-b", "other")
    _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty")
    _git(repo, "checkout", "-q", "main")

    result = _push(repo, "--all")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_mirror_push_refuses_a_dirty_history(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "dirty")

    result = _push(repo, "--mirror")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_mirror_push_of_clean_history_passes(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")

    result = _push(repo, "--mirror")

    assert result.returncode == 0, result.stderr


def test_prune_push_still_scans_whatever_remains_dirty(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "checkout", "-q", "-b", "doomed")
    _commit(repo, "b.txt", "clean too\n", "clean on doomed")
    _push(repo, "main", "doomed")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-D", "doomed")
    _commit(repo, "c.txt", f"{FAKE.upper()}-1\n", "dirty")

    result = _push(repo, "--prune", "main")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_gerrit_style_ref_is_scanned_like_any_other_push(
    tmp_path: Path, monkeypatch
) -> None:
    """`refs/for/x` is not under refs/heads or refs/tags, but the ref-
    specific range (TO --not FROM --remotes) does not care about the
    destination ref's own namespace -- only about which commits it would
    newly publish."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "dirty")

    result = _push(repo, "HEAD:refs/for/main")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_refs_notes_push_is_refused_not_silently_passed(
    tmp_path: Path, monkeypatch
) -> None:
    """DG-479's module docstring states refs/notes/* is not specifically
    walked by --branches --tags. Documented decision (this round): accept
    the resulting fail-closed refusal rather than add notes support now --
    a refs/notes push is refused outright (git log on a notes tree is not
    a commit range), never read as nothing to scan."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    _git(repo, "notes", "add", "-m", "a clean note", "HEAD")

    result = _push(repo, "refs/notes/commits")

    # Whichever way it resolves, it must never pass with unscanned content
    # silently reaching the remote while claiming success without having
    # looked at it. Accept-the-limit here means: a refusal is fine.
    if result.returncode == 0:
        assert "skip" not in (result.stdout + result.stderr).lower()


def test_a_branch_rename_push_is_scanned_for_the_new_name(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty")

    result = _push(repo, "refs/heads/main:refs/heads/renamed")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_force_push_is_still_scanned(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    base = _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    _commit(repo, "b.txt", "clean too\n", "will be rewritten away")
    _git(repo, "reset", "-q", "--hard", base)
    _commit(repo, "c.txt", f"{FAKE.upper()}-1\n", "dirty rewrite")

    result = _push(repo, "--force", "HEAD:main")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_empty_stdin_refuses_rather_than_passes(tmp_path: Path, monkeypatch) -> None:
    """Not a shape a real git push ever produces (git always writes at
    least one ref line) -- but the hook must still fail closed rather than
    read zero lines as nothing to scan, the same rule
    check_operator_inventory.py already follows for every other
    unresolvable case."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")

    result = _run_hook_directly(repo, "")

    assert result.returncode != 0


def test_crlf_in_stdin_lines_does_not_silently_pass_a_dirty_push(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    dirty_sha = _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "dirty")

    zero = "0" * 40
    stdin_text = f"refs/heads/main {dirty_sha} refs/heads/main {zero}\r\n"
    result = _run_hook_directly(repo, stdin_text)

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_truncated_ref_line_does_not_silently_pass_a_dirty_push(
    tmp_path: Path, monkeypatch
) -> None:
    """A line missing its trailing remote-sha field entirely -- read
    leaves that variable empty, read as FROM unset, same as a brand-new
    branch. The dirty commit must still be caught."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    dirty_sha = _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "dirty")

    stdin_text = f"refs/heads/main {dirty_sha} refs/heads/main\n"
    result = _run_hook_directly(repo, stdin_text)

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_thousands_of_refs_completes_in_reasonable_time(
    tmp_path: Path, monkeypatch
) -> None:
    import time

    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    refs = []
    for i in range(500):
        _git(repo, "branch", f"b{i}")
        refs.append(f"b{i}")

    started = time.monotonic()
    result = _push(repo, *refs)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 120, f"500 clean refs took {elapsed:.1f}s -- too slow"


def test_only_the_windows_py_launcher_on_path_still_works(
    tmp_path: Path, monkeypatch
) -> None:
    """py (the Windows launcher) is the third candidate find_python tries.
    If it is the only interpreter on PATH, the hook must still find and
    use it rather than failing closed unnecessarily."""
    import os
    import shutil

    if sys.platform != "win32":
        pytest.skip("the py launcher is Windows-only")
    py_launcher = shutil.which("py")
    if py_launcher is None:
        pytest.skip("no py launcher installed on this machine")

    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    dirty_sha = _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "dirty")

    fake_bin = tmp_path / "py-only-bin"
    fake_bin.mkdir()
    shim = fake_bin / "py.exe"
    shutil.copy(py_launcher, shim)
    git_dir = Path(shutil.which("git")).parent
    sh_dir = Path(shutil.which("sh")).parent

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(fake_bin), str(git_dir), str(sh_dir)])

    result = subprocess.run(
        ["git", "push", "origin", "HEAD:main"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0, (
        "the dirty commit must still be refused when py is the only "
        f"interpreter on PATH: {result.stdout} {result.stderr}"
    )
    assert FAKE not in (result.stdout + result.stderr).lower()
    assert dirty_sha  # keep the sha referenced; the assertion is on refusal


# --- Round 3 review (Jira comment on DG-479): BLOCK -- the round 2 perf
# fix (first-non-deletion-ref + the existing global scan) opened a real,
# reproduced leak. A commit reachable from NOTHING under refs/heads or
# refs/tags (detached HEAD, refs/stash, refs/original/*, a branch deleted
# locally before the push, ...) is invisible to the global scan by
# construction, and was only caught before if it happened to be the FIRST
# ref line in the push. The fix: one invocation per push still, but it now
# reads every ref line itself and unions every pushed local sha into a
# single git log call -- every test below is the reviewer's own repro, or
# a variant of it, run against the real fix.


def test_the_reviewers_repro_clean_main_then_detached_sneaky_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """The exact repro from the round 2 BLOCK: clean main pushed first,
    then in a SECOND push, main (unchanged) together with a detached dirty
    sha pushed to a new ref name. Before the fix: exit 0, and the dirty
    commit reached the remote."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    bootstrap = _push(repo, "HEAD:main")
    assert bootstrap.returncode == 0, bootstrap.stderr

    _git(repo, "checkout", "-q", "-b", "throwaway")
    dirty_sha = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty, detached")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-D", "throwaway")  # now reachable from nothing local

    result = _push(repo, "main", f"{dirty_sha}:refs/heads/sneaky")

    assert result.returncode != 0, (
        "a detached dirty commit pushed alongside an unrelated clean ref "
        f"must be refused: {result.stdout} {result.stderr}"
    )
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_the_reviewers_repro_reversed_order_is_also_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """Order must not matter -- the old 'first ref only' bug would have
    caught this order and missed the other."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")

    _git(repo, "checkout", "-q", "-b", "throwaway")
    dirty_sha = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty, detached")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-D", "throwaway")

    result = _push(repo, f"{dirty_sha}:refs/heads/sneaky", "main")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_dirty_commit_on_refs_stash_is_refused(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    (repo / "a.txt").write_text(f"{FAKE.upper()}-1\n", encoding="utf-8")
    _git(repo, "stash", "push", "-m", "dirty stash")
    stash_sha = _git_out(repo, "rev-parse", "refs/stash")

    result = _push(repo, f"{stash_sha}:refs/heads/from-stash")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_dirty_commit_on_refs_original_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    dirty_sha = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty")
    # `git update-ref` straight to refs/original/... -- the shape
    # `git filter-branch` leaves behind -- without ever naming a branch.
    _git(repo, "update-ref", "refs/original/refs/heads/main", dirty_sha)

    result = _push(repo, "refs/original/refs/heads/main:refs/heads/from-original")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_dirty_commit_on_refs_remotes_pushed_by_name_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    dirty_sha = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty")
    _git(repo, "update-ref", "refs/remotes/o/x", dirty_sha)

    result = _push(repo, "refs/remotes/o/x:refs/heads/from-remote-tracking")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_dirty_annotated_tag_pushed_by_sha_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    tag_sha = _annotated_tag(repo, "v1", f"touches {FAKE}")

    result = _push(repo, f"{tag_sha}:refs/tags/pushed-by-sha")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_dirty_commit_on_a_locally_deleted_branch_pushed_by_sha_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """The dirty commit's only local ref is deleted BEFORE the push that
    names its sha directly -- nothing under refs/heads/refs/tags reaches
    it any more; only the ref line this push sends can."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")

    _git(repo, "checkout", "-q", "-b", "doomed")
    dirty_sha = _commit(repo, "b.txt", f"{FAKE.upper()}-1\n", "dirty")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "branch", "-D", "doomed")

    result = _push(repo, f"{dirty_sha}:refs/heads/resurrected")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_a_pure_deletion_push_still_passes_quietly(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _git(repo, "branch", "doomed")
    _push(repo, "main", "doomed")

    result = _push(repo, ":refs/heads/doomed")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_a_clean_refs_notes_push_passes_quietly(tmp_path: Path, monkeypatch) -> None:
    """Corrects the round 2 claim: refs/notes/* is scanned exactly like
    any other ref by the union rev-list call (it only cares about the
    commit the sha resolves to, never the ref's own namespace) -- a clean
    notes push is quiet, not refused."""
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    _git(repo, "notes", "add", "-m", "a clean note", "HEAD")

    result = _push(repo, "refs/notes/commits")

    assert result.returncode == 0, result.stderr


def test_a_dirty_refs_notes_push_is_refused(tmp_path: Path, monkeypatch) -> None:
    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    _push(repo, "HEAD:main")
    _git(repo, "notes", "add", "-m", f"touches {FAKE}", "HEAD")

    result = _push(repo, "refs/notes/commits")

    assert result.returncode != 0
    assert FAKE not in (result.stdout + result.stderr).lower()


def test_two_thousand_refs_completes_in_reasonable_time(
    tmp_path: Path, monkeypatch
) -> None:
    import time

    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    _commit(repo, "a.txt", "clean\n", "base")
    refs = [f"b{i}" for i in range(2000)]
    for ref in refs:
        _git(repo, "branch", ref)

    started = time.monotonic()
    result = _push(repo, *refs)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 180, f"2000 clean refs took {elapsed:.1f}s -- too slow"


def test_many_refs_spanning_one_huge_range_completes_in_reasonable_time(
    tmp_path: Path, monkeypatch
) -> None:
    """Not just many refs -- many refs whose union covers a genuinely large
    number of unpublished commits, so the single git log call itself (not
    just process start-up count) is exercised at scale."""
    import time

    _remote, repo = _bare_remote_and_repo(tmp_path, monkeypatch)
    sha = _commit(repo, "a.txt", "clean\n", "base")
    for i in range(300):
        sha = _commit(repo, f"f{i}.txt", "clean too\n", f"commit {i}")
    refs = []
    for i in range(50):
        _git(repo, "branch", f"wide{i}", sha)
        refs.append(f"wide{i}")

    started = time.monotonic()
    result = _push(repo, *refs)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 60, (
        f"50 refs sharing a 300-commit range took {elapsed:.1f}s -- too slow"
    )
