# mypy: ignore-errors
"""The pinned-install command moves to the tool that reports the drift — DG-356.

`uv tool install` ignores `uv.lock`, so the installed environment drifts inside
the allowed range: the deployment carried `mcp` 1.29.0 against a lock pinning
1.28.1 for two releases, both satisfying `<2`, with nothing reporting it.
`drunken-doctor` is what reports it, and the fix used to live in a second
command the warning had to name. It lives here now, so the tool that finds the
problem is the tool that prints the remedy.

**Printed, never run.** Installing replaces the deployment a host config already
points at; doing that as a side effect of asking a diagnostic question is the
kind of surprise this project keeps writing post-mortems about.
"""

from pathlib import Path

from core import doctor


class TestItPrintsRatherThanInstalls:
    def test_it_writes_the_pins_and_prints_the_command(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(
            doctor, "export_requirements", lambda root: "mcp==1.28.1\nhttpx==0.27.0\n"
        )
        target = tmp_path / "requirements.lock.txt"

        assert doctor.emit_requirements(str(target)) == 0

        assert target.read_text().startswith("mcp==1.28.1")
        out = capsys.readouterr().out
        assert "NOT INSTALLED" in out, (
            "The first version printed a filename and a command with no verb "
            "between them, which was read as a report of work completed."
        )
        assert "--with-requirements" in out

    def test_an_unexportable_lock_falls_back_and_says_so(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        """`uv` absent, or not a project root. An unpinned install is still
        better than a command that does not run, as long as the difference is
        stated."""
        monkeypatch.setattr(doctor, "export_requirements", lambda root: None)

        assert doctor.emit_requirements(str(tmp_path / "unused.txt")) == 0

        captured = capsys.readouterr()
        assert "uv tool install" in captured.out
        assert "--with-requirements" not in captured.out
        assert "could not export" in captured.err

    def test_nothing_is_written_when_there_is_nothing_to_write(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(doctor, "export_requirements", lambda root: None)
        target = Path(tmp_path / "requirements.lock.txt")

        doctor.emit_requirements(str(target))

        assert not target.exists()
