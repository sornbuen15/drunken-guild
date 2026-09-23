# mypy: ignore-errors
"""The operator-inventory guard runs at commit time, on what is being committed.

DG-317 took the operator's project ids out of this public repository, and a test
has guarded it since. On 2026-09-23 a real project key went back in anyway, twice
(#89, #93). The test could not stop it: it skips on CI, where there is no
registry, and it reads `git ls-files`, so a new file is invisible to it until it
is already staged — and the suite had run before that.

So the check moves to where the mistake happens. A pre-commit hook reads the
*staged* content and a commit-msg hook reads the message, against the registry of
the machine making the commit. No registry, nothing to leak, nothing blocked.
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


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    registry = tmp_path / "projects.json"
    registry.write_text(
        json.dumps({"version": 2, "projects": {"drunken-guild": {}, FAKE: {}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry))
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    return work


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_a_staged_file_naming_a_registered_project_is_refused(repo: Path) -> None:
    (repo / "t.py").write_text(f'KEY = "{FAKE.upper()}-1"\n', encoding="utf-8")
    _git(repo, "add", "t.py")

    result = _run(repo)

    assert result.returncode == 1
    assert "t.py:1" in result.stdout + result.stderr


def test_the_refusal_does_not_print_the_id_itself(repo: Path) -> None:
    """The output lands in terminals and CI logs; it names the place, not the id."""
    (repo / "t.py").write_text(f"{FAKE}\n", encoding="utf-8")
    _git(repo, "add", "t.py")

    result = _run(repo)

    assert FAKE not in (result.stdout + result.stderr).lower()


def test_an_unstaged_file_is_not_its_business(repo: Path) -> None:
    (repo / "t.py").write_text(f"{FAKE}\n", encoding="utf-8")

    assert _run(repo).returncode == 0


def test_clean_staged_content_passes(repo: Path) -> None:
    (repo / "t.py").write_text(
        'KEY = "ALPHA-1"  # zetagonal is a word\n', encoding="utf-8"
    )
    _git(repo, "add", "t.py")

    assert _run(repo).returncode == 0


def test_a_commit_message_naming_a_project_is_refused(
    repo: Path, tmp_path: Path
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"fix: the {FAKE.upper()} board\n", encoding="utf-8")

    result = _run(repo, "--message", str(message))

    assert result.returncode == 1


def test_no_registry_blocks_nothing(repo: Path, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(tmp_path / "absent.json"))
    (repo / "t.py").write_text(f"{FAKE}\n", encoding="utf-8")
    _git(repo, "add", "t.py")

    assert _run(repo).returncode == 0


def test_both_hooks_are_wired() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "check_operator_inventory.py" in config
    assert "commit-msg" in config
