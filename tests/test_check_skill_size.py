# mypy: ignore-errors
"""DG-516. Skills and agents are read, not skimmed, and a long file costs
context on every load. ``check_skill_size.py`` is the guard: a SKILL.md over
120 lines or an agent over 100 lines fails unless a checked-in baseline
already recorded it as oversize -- and even then, only up to the line count
the baseline recorded. The baseline is a ratchet: a file may stay oversize,
but it may never grow past what was last recorded, and shrinking it is
always accepted.

Testing a checker is worth the effort in one specific way: a check that
cannot fail is worse than no check, because it reports success. Most of
what follows proves the thing actually catches something.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")  # type: ignore[misc]
def guard():
    spec = importlib.util.spec_from_file_location(
        "check_skill_size", REPO_ROOT / "scripts" / "check_skill_size.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_lines(path: Path, n: int) -> None:
    path.write_text("\n".join(f"line {i}" for i in range(n)) + "\n")


def test_the_repo_is_currently_clean(guard) -> None:
    """The real tree, scanned with the real baseline, must pass -- this is
    the gate CI and pre-commit actually run."""
    problems = guard.scan()
    assert not problems, (
        "Oversize files not covered by the baseline:\n  " + "\n  ".join(problems)
    )


def test_a_new_130_line_skill_fails(guard, tmp_path, monkeypatch) -> None:
    """ACCEPTANCE 1: a new 130-line skill fails. Over the 120-line SKILL.md
    limit and absent from the baseline -- nothing has grandfathered it in."""
    skill_dir = tmp_path / "skills" / "example" / "widget"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    _write_lines(skill_file, 130)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "load_baseline", lambda: {})

    problems = guard.scan()

    assert len(problems) == 1
    assert "SKILL.md" in problems[0]
    assert "130" in problems[0]


def test_a_baseline_file_that_grows_fails(guard, tmp_path, monkeypatch) -> None:
    """ACCEPTANCE 1: a baseline file that grows fails. The baseline recorded
    this file at 150 lines; it is now 160 -- past what the ratchet allows,
    even though both numbers are over the limit."""
    skill_dir = tmp_path / "skills" / "example" / "widget"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    _write_lines(skill_file, 160)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        guard, "load_baseline", lambda: {"skills/example/widget/SKILL.md": 150}
    )

    problems = guard.scan()

    assert len(problems) == 1
    assert "160" in problems[0] and "150" in problems[0]


def test_a_baseline_file_that_shrinks_passes(guard, tmp_path, monkeypatch) -> None:
    """ACCEPTANCE 1: a baseline file that shrinks passes. Still over the
    120-line limit, but under the 150 the baseline recorded -- the ratchet
    only ever tightens, so an improvement is never penalised."""
    skill_dir = tmp_path / "skills" / "example" / "widget"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    _write_lines(skill_file, 140)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        guard, "load_baseline", lambda: {"skills/example/widget/SKILL.md": 150}
    )

    assert guard.scan() == []


def test_a_compliant_file_passes(guard, tmp_path, monkeypatch) -> None:
    """ACCEPTANCE 1: a compliant file passes. At the 120-line limit exactly,
    with no baseline entry at all."""
    skill_dir = tmp_path / "skills" / "example" / "widget"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    _write_lines(skill_file, 120)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "load_baseline", lambda: {})

    assert guard.scan() == []


def test_an_oversize_agent_over_the_100_line_limit_fails(
    guard, tmp_path, monkeypatch
) -> None:
    """Agents carry a lower limit than skills: 100 lines, not 120."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    agent_file = agents_dir / "widget.md"
    _write_lines(agent_file, 101)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "load_baseline", lambda: {})

    problems = guard.scan()

    assert len(problems) == 1
    assert "widget.md" in problems[0]


def test_a_nested_agent_file_over_the_limit_fails(guard, tmp_path, monkeypatch) -> None:
    """A real bypass found in review of PR 204: `agent_files()` used
    `rglob("agents/*.md")`, which only matches a `*.md` file directly
    inside a directory literally named `agents` -- a file one level
    deeper, `agents/nested/huge.md`, never matched the pattern at all and
    was silently never checked, however long it grew."""
    nested_dir = tmp_path / "agents" / "nested"
    nested_dir.mkdir(parents=True)
    _write_lines(nested_dir / "huge.md", 500)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "load_baseline", lambda: {})

    problems = guard.scan()

    assert len(problems) == 1
    assert "agents/nested/huge.md" in problems[0]
    assert "500" in problems[0]


def test_agent_index_is_not_itself_checked(guard, tmp_path, monkeypatch) -> None:
    """agents/INDEX.md is generated and lists every agent -- it is not an
    agent file, and must not be measured against the agent limit."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    _write_lines(agents_dir / "INDEX.md", 150)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "load_baseline", lambda: {})

    assert guard.scan() == []


def test_a_stale_baseline_entry_for_a_file_that_no_longer_exists_fails(
    guard, tmp_path, monkeypatch
) -> None:
    """A baseline entry for a deleted file is a stale record -- the oversize
    file it grandfathered is gone, so the entry must be removed, not left
    to silently cover whatever gets created at that path next."""
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        guard,
        "load_baseline",
        lambda: {"skills/gone/SKILL.md": 200},
    )

    problems = guard.scan()

    assert len(problems) == 1
    assert "skills/gone/SKILL.md" in problems[0]


def test_a_skill_named_build_is_not_mistaken_for_the_packaging_directory(
    guard, tmp_path, monkeypatch
) -> None:
    """`skills/flow/build/SKILL.md` is a real skill named "build" — a
    top-level-only directory skip must not swallow it just because a
    nested directory happens to share a name with the packaging output
    skipped at the repository root."""
    skill_dir = tmp_path / "skills" / "flow" / "build"
    skill_dir.mkdir(parents=True)
    _write_lines(skill_dir / "SKILL.md", 10)
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "load_baseline", lambda: {})

    found = {p.relative_to(tmp_path).as_posix() for p in guard.skill_files()}

    assert "skills/flow/build/SKILL.md" in found


def test_the_baseline_file_itself_parses(guard) -> None:
    """Guards the guard: a baseline that fails to load would make every
    other assertion here pass while checking nothing real."""
    baseline = guard.load_baseline()
    assert baseline, "an empty baseline means today's oversize files were not recorded"
    for path_str, count in baseline.items():
        assert (guard.REPO_ROOT / path_str).is_file(), f"{path_str} is not a real file"
        assert count > 0


def test_every_baseline_entry_is_actually_oversize(guard) -> None:
    """A baseline entry for a file that is not even over the limit is not a
    ratchet -- it is slack nobody asked for."""
    for path_str, _count in guard.load_baseline().items():
        limit = guard.limit_for(Path(path_str))
        actual = len(
            (guard.REPO_ROOT / path_str).read_text(encoding="utf-8").splitlines()
        )
        assert actual > limit, (
            f"{path_str} is listed oversize but is only {actual} lines"
        )
