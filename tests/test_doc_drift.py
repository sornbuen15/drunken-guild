# mypy: ignore-errors
"""The guard that stops DT-238 from being needed a second time.

Testing a checker is worth the effort in one specific way: a check that cannot
fail is worse than no check, because it reports success. Most of what follows
proves the thing actually catches something.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")  # type: ignore[misc]
def drift():
    spec = importlib.util.spec_from_file_location(
        "check_doc_drift", REPO_ROOT / "scripts" / "check_doc_drift.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_repo_is_currently_clean(drift) -> None:
    """The check is also the assertion — if this fails, some document is
    telling a reader to run something that no longer exists."""
    problems = drift.scan()
    assert not problems, "Stale documentation:\n  " + "\n  ".join(problems)


def test_it_actually_reads_documents(drift) -> None:
    """Guards the guard. A path filter that quietly matched nothing would make
    every other assertion here pass while checking an empty set."""
    documents = drift.documents()

    assert len(documents) > 20
    names = {path.name for path in documents}
    assert {"README.md", "Integration-Guide.md", "Drunken-Team-Guide.md"} <= names


def test_it_catches_a_retired_name(drift, tmp_path, monkeypatch) -> None:
    stale = tmp_path / "guide.md"
    stale.write_text("Set it up by running `uv run drunken-register`.\n")
    monkeypatch.setattr(drift, "documents", lambda: [stale])
    monkeypatch.setattr(drift, "REPO_ROOT", tmp_path)

    problems = drift.scan()

    assert len(problems) == 1
    assert "drunken-register" in problems[0]
    assert "drunken-init" in problems[0], (
        "The failure names what is gone but not what replaced it, which leaves "
        "the reader exactly as stuck as the stale doc did."
    )


def test_a_line_may_opt_out_with_a_reason(drift, tmp_path, monkeypatch) -> None:
    """A prohibition has to be able to name what it prohibits. `.agents/AGENTS.md`
    telling agents *not* to write `discord_outbox.json` is correct text, not
    drift."""
    allowed = tmp_path / "rules.md"
    allowed.write_text(
        "Never write `.agents/discord_outbox.json`. <!-- drift-ok: the "
        "prohibition has to name what it prohibits -->\n"
    )
    monkeypatch.setattr(drift, "documents", lambda: [allowed])
    monkeypatch.setattr(drift, "REPO_ROOT", tmp_path)

    assert drift.scan() == []


def test_records_of_what_changed_are_not_scanned(drift) -> None:
    """SESSION_CHECKPOINT.md's job is to say what was removed. It cannot do
    that without naming it."""
    scanned = {path.name for path in drift.documents()}

    assert "SESSION_CHECKPOINT.md" not in scanned
    assert drift.RECORDS, "An empty exemption list means the rule below is untested."


def test_worktrees_and_vendored_copies_are_not_scanned(drift) -> None:
    """`.claude/worktrees` holds whole copies of this repo at older commits.
    Reporting drift there is reporting the past, and they are not ours to edit."""
    assert not [p for p in drift.documents() if ".claude" in p.parts]


def test_the_templates_we_hand_out_are_scanned(drift) -> None:
    """`.guild_templates/` is copied into every downstream project, so a stale
    instruction there propagates instead of just sitting still."""
    scanned = {path.name for path in drift.documents()}

    assert ".cursorrules" in scanned
    assert "CONVENTIONS.md" in scanned


def test_every_retired_entry_says_what_to_use_instead(drift) -> None:
    for retired in drift.RETIRED:
        assert retired.use_instead, f"{retired.name} has no replacement recorded."
        assert retired.removed_in, f"{retired.name} does not say when it went."
