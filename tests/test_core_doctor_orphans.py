# mypy: ignore-errors
"""``processes.orphans`` (DG-518) — the doctor check wrapping ``core.orphans``.

Every test hands in a fixed process table; none of this ever reads the real
process table or touches a real process.
"""

from __future__ import annotations

from core import doctor, orphans

_TOOL_ROOT = "C:/tools/drunken-guild/"
_BIN_SHIM = "C:/bin/drunken-jira-mcp"


def _named(report, name):
    return next((c for c in report.checks if c.name == name), None)


def _proc(pid, ppid, command=""):
    return orphans.ProcessInfo(pid=pid, ppid=ppid, start_time="t1", command=command)


class TestOrphansCheck:
    def test_ok_when_no_orphans_found(self):
        report = doctor.Report()
        doctor._check_orphans(report, [_proc(1, 0, "init")])
        check = _named(report, "processes.orphans")
        assert check.status == "ok"

    def test_warns_with_count_and_ids_when_orphans_found(self):
        report = doctor.Report()
        doctor._check_orphans(report, [_proc(100, 999, "bash -c sleep 97")])
        check = _named(report, "processes.orphans")
        assert check.status == "warn"
        assert "pid 100" in check.detail
        assert "drunken-install reap" in check.remediation

    def test_never_fails_even_with_many_orphans(self):
        report = doctor.Report()
        table = [_proc(100 + i, 999, "bash -c sleep") for i in range(10)]
        doctor._check_orphans(report, table)
        check = _named(report, "processes.orphans")
        assert check.status == "warn"
        assert "and 5 more" in check.detail

    def test_skips_when_the_process_table_cannot_be_read(self, monkeypatch):
        def _raise():
            raise orphans.ProcessTableUnavailableError("no ps on PATH")

        monkeypatch.setattr(orphans, "list_processes", _raise)
        report = doctor.Report()
        doctor._check_orphans(report)
        check = _named(report, "processes.orphans")
        assert check.status == "skip"
        assert "no ps on PATH" in check.detail

    def test_a_process_with_a_live_parent_is_never_reported(self):
        report = doctor.Report()
        doctor._check_orphans(
            report,
            [
                _proc(1, 0, "init"),
                _proc(100, 1, "bash -c sleep 97"),
            ],
        )
        check = _named(report, "processes.orphans")
        assert check.status == "ok"

    def test_lists_a_held_lock_holder_without_a_dead_parent(self):
        """DG-518 scope addition: a live-parented process inside the
        installed tool is reported too, labeled distinctly from an orphan,
        and the remediation names --include-held."""
        report = doctor.Report()
        doctor._check_orphans(
            report,
            [
                _proc(50, 1, "claude.exe"),
                _proc(100, 50, r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
            ],
            tool_roots=[_TOOL_ROOT, _BIN_SHIM],
        )
        check = _named(report, "processes.orphans")
        assert check.status == "warn"
        assert "held by session 50" in check.detail
        assert "--include-held" in check.remediation

    def test_a_lock_holder_with_a_live_parent_outside_the_tool_is_not_reported(self):
        report = doctor.Report()
        doctor._check_orphans(
            report,
            [
                _proc(50, 1, "claude.exe"),
                _proc(100, 50, "bash -c sleep 97"),
            ],
            tool_roots=[_TOOL_ROOT, _BIN_SHIM],
        )
        check = _named(report, "processes.orphans")
        assert check.status == "ok"

    def test_the_running_doctor_process_never_reports_itself(self, monkeypatch):
        """DG-518 review: `drunken-doctor` itself runs from inside the
        installed tool directory, so it would otherwise always flag its own
        ancestor chain as a lock holder of itself -- noise on every run."""
        monkeypatch.setattr(orphans.os, "getpid", lambda: 999)
        report = doctor.Report()
        doctor._check_orphans(
            report,
            [
                _proc(50, 1, "claude.exe"),
                _proc(999, 50, r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
            ],
            tool_roots=[_TOOL_ROOT, _BIN_SHIM],
        )
        check = _named(report, "processes.orphans")
        assert check.status == "ok"

    def test_a_dotnet_date_start_time_is_shown_converted_not_raw(self):
        """DG-518 review: a real machine's PowerShell printed the raw
        ``/Date(...)/`` form -- the report must show a readable local
        timestamp instead."""
        dotnet_proc = orphans.ProcessInfo(
            pid=100,
            ppid=999,
            start_time="/Date(1791775989721)/",
            command="bash -c sleep 97",
        )
        report = doctor.Report()
        doctor._check_orphans(report, [dotnet_proc])
        check = _named(report, "processes.orphans")
        assert "/Date(" not in check.detail

    def test_run_doctor_includes_the_check(self, tmp_path, monkeypatch):
        """End to end: ``run_doctor`` itself includes ``processes.orphans``,
        never crashing even if the real table cannot be read on this machine."""
        from core.registry import ProjectRegistry

        registry = ProjectRegistry(tmp_path / "projects.json")
        report = doctor.run_doctor(registry=registry, offline=True)
        assert _named(report, "processes.orphans") is not None
