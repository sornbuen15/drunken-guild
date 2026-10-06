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

    env = os.environ.copy()
    env.update(extra_env or {})
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


def test_a_branch_deletion_passes(repo: Path) -> None:
    """TO is the all-zero SHA: nothing is being pushed, so there is nothing to
    scan -- the one case where no range at all is legitimately a pass."""
    _commit(repo, "a.txt", f"{FAKE.upper()}-1\n", "wip")  # history exists, irrelevant

    result = _run(repo, {"PRE_COMMIT_TO_REF": "0" * 40})

    assert result.returncode == 0


def test_an_absent_to_ref_refuses_rather_than_scanning_head_or_passing(
    repo: Path,
) -> None:
    """Run by hand, outside pre-commit's own pre-push stage, PRE_COMMIT_TO_REF
    is simply not set. There is no safe guess for what is being pushed, so
    this must fail closed -- not silently scan HEAD, and not silently pass."""
    _commit(repo, "a.txt", "clean\n", "base")  # HEAD is clean; must not matter

    result = _run(repo)  # no PRE_COMMIT_TO_REF at all

    assert result.returncode == 1


def test_the_config_wires_the_pre_push_stage() -> None:
    import re

    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "check_operator_inventory.py --push" in config

    install_types = re.search(
        r"^default_install_hook_types:\s*\[([^\]]*)\]", config, re.MULTILINE
    )
    assert install_types is not None
    assert "pre-push" in [t.strip() for t in install_types.group(1).split(",")]

    assert re.search(
        r"check_operator_inventory\.py --push[\s\S]{0,200}stages:\s*\[pre-push\]",
        config,
    )
