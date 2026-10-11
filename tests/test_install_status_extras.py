# mypy: ignore-errors
"""DG-512 reviewer LOW finding, round 2: `drunken-install status` printing 31 "missing: <name>"
lines when the extras are not installed at all is noise, not status -- one summary line covers
that case, and the per-name lines return once there is something to actually look at.
"""

from __future__ import annotations

from pathlib import Path

from core import install


def test_status_prints_one_summary_line_when_no_extras_are_installed(
    tmp_path: Path, capsys
) -> None:
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"

    report = install.status(skills_target, agents_target)
    install._print_status(report)

    out = capsys.readouterr().out
    assert report.extras_total > 0, "the repository has no extras to report on?"
    assert report.extras_installed == 0
    assert f"{report.extras_total} available, 0 installed" in out
    assert "missing:" not in out, (
        "nothing installed must print one summary line, not one 'missing:' line per extra"
    )


def test_status_lists_names_once_something_is_installed(tmp_path: Path, capsys) -> None:
    from core import install_extras

    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"
    install_extras.install_extras(
        skills_target, agents_target, apply=True, only=["acronym-namer"]
    )

    report = install.status(skills_target, agents_target)
    install._print_status(report)

    out = capsys.readouterr().out
    assert report.extras_installed >= 1
    assert "extras (optional, drunken-install extras --apply):" in out
    assert "available, 0 installed" not in out


def test_extras_never_affect_up_to_date_either_way() -> None:
    all_missing = install.StatusReport(extras_total=31, extras_installed=0)
    assert all_missing.up_to_date is True

    some_installed = install.StatusReport(extras_total=31, extras_installed=5)
    assert some_installed.up_to_date is True

    only_core_changes = install.StatusReport(
        skills_changes=["new: something"], extras_total=31, extras_installed=31
    )
    assert only_core_changes.up_to_date is False
