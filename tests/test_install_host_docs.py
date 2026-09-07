# mypy: ignore-errors
"""Installing the global host instruction file — DG-324.

`install_host_docs.sh` overwrites `~/.gemini/config/AGENTS.md`, which is the
operator's own file and read across every project. Three things follow, and the
tests hold each of them:

- **It writes nothing without `--apply`.** Every other install script in this
  tree writes on sight; this one replaces a file the operator may have edited,
  so it shows a diff and stops.
- **A backup lands before the write,** and an existing backup is kept. The first
  one holds the state before anything was replaced; overwriting it on a second
  run leaves a "backup" of the already-replaced file.
- **A host that is not installed is not an error.** A machine with no
  `~/.gemini/config/` legitimately has none, and an install script that fails
  there is one people learn to skip.

Driven through the shell rather than reimplemented in Python, for the same
reason `test_install_index_determinism.py` does: the thing being tested is the
script an operator actually runs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "install" / "install_host_docs.sh"


def run(*args, source=None, target=None):
    argv = ["bash", str(SCRIPT)]
    if source is not None:
        argv += ["--source", str(source)]
    if target is not None:
        argv += ["--target", str(target)]
    argv += list(args)
    return subprocess.run(argv, capture_output=True, text=True, cwd=REPO)


@pytest.fixture()
def source(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_text("# the new global file\n", encoding="utf-8")
    return path


@pytest.fixture()
def target(tmp_path):
    host = tmp_path / "config"
    host.mkdir()
    path = host / "AGENTS.md"
    path.write_text("# Silent Wait Protocol\n", encoding="utf-8")
    return path


class TestItWritesNothingByDefault:
    def test_a_dry_run_leaves_the_target_alone(self, source, target) -> None:
        before = target.read_bytes()
        result = run(source=source, target=target)
        assert result.returncode == 0
        assert target.read_bytes() == before

    def test_a_dry_run_shows_what_would_change(self, source, target) -> None:
        """A diff, not "would update". The operator is being asked to approve
        replacing a file they may have written."""
        result = run(source=source, target=target)
        assert "Silent Wait Protocol" in result.stdout
        assert "the new global file" in result.stdout

    def test_a_dry_run_creates_no_backup(self, source, target) -> None:
        run(source=source, target=target)
        assert list(target.parent.glob("*.bak")) == []


class TestApplying:
    def test_the_target_becomes_the_source(self, source, target) -> None:
        run("--apply", source=source, target=target)
        assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")

    def test_a_backup_holds_what_was_replaced(self, source, target) -> None:
        run("--apply", "--ticket", "DG-324", source=source, target=target)
        backup = target.with_name(target.name + ".pre-DG-324.bak")
        assert backup.is_file()
        assert "Silent Wait Protocol" in backup.read_text(encoding="utf-8")

    def test_an_existing_backup_is_never_overwritten(self, source, target) -> None:
        run("--apply", "--ticket", "DG-324", source=source, target=target)
        source.write_text("# a third version\n", encoding="utf-8")
        run("--apply", "--ticket", "DG-324", source=source, target=target)
        backup = target.with_name(target.name + ".pre-DG-324.bak")
        assert "Silent Wait Protocol" in backup.read_text(encoding="utf-8")

    def test_an_absent_target_is_created(self, source, target) -> None:
        target.unlink()
        run("--apply", source=source, target=target)
        assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


class TestTheCasesThatAreNotErrors:
    def test_no_host_directory_is_not_a_failure(self, source, tmp_path) -> None:
        """A machine with no Antigravity installed legitimately has none, and a
        script that fails there is one people learn to skip."""
        result = run("--apply", source=source, target=tmp_path / "absent" / "AGENTS.md")
        assert result.returncode == 0
        assert not (tmp_path / "absent").exists()

    def test_an_identical_target_is_a_no_op(self, source, target) -> None:
        shutil.copy(source, target)
        result = run("--apply", source=source, target=target)
        assert result.returncode == 0
        assert "Already identical" in result.stdout
        assert list(target.parent.glob("*.bak")) == []


class TestTheCasesThatAre:
    def test_a_missing_source_fails_and_says_where_it_lives(
        self, tmp_path, target
    ) -> None:
        result = run("--apply", source=tmp_path / "gone.md", target=target)
        assert result.returncode != 0
        assert "templates/AGENTS.md" in result.stderr
        assert "Silent Wait Protocol" in target.read_text(encoding="utf-8")


def test_the_shipped_template_is_the_default_source() -> None:
    """The default must be the tracked file, not a path the operator retypes."""
    assert (REPO / "templates" / "AGENTS.md").is_file()
    assert 'SOURCE="$PROJECT_ROOT/templates/AGENTS.md"' in SCRIPT.read_text(
        encoding="utf-8"
    )
