# mypy: ignore-errors
"""``core.orphans`` — DG-518: detect leftover session processes, and the plan
re-verification ``drunken-install reap --apply`` relies on before it ever
touches a real pid.

Every test here builds its own :class:`~core.orphans.ProcessInfo` table by
hand — a monkeypatched process table throughout, per the task's hard rule.
Nothing here starts, stops or signals a real process.
"""

from __future__ import annotations

import pytest

from core import orphans
from core.orphans import OrphanProcess, ProcessInfo, ProcessTableUnavailableError


def _proc(pid, ppid, start_time="t1", command="") -> ProcessInfo:
    return ProcessInfo(pid=pid, ppid=ppid, start_time=start_time, command=command)


class TestFindOrphans:
    def test_an_orphan_matching_a_pattern_is_listed(self):
        table = [
            _proc(100, 1, command="/bin/bash -c 'sleep 97'"),
        ]
        found = orphans.find_orphans(table)
        assert found == [OrphanProcess(100, 1, "t1", "/bin/bash -c 'sleep 97'")]

    def test_a_process_with_a_live_parent_is_not_listed(self):
        table = [
            _proc(1, 0, command="init"),
            _proc(100, 1, command="/bin/bash -c 'sleep 97'"),
        ]
        assert orphans.find_orphans(table) == []

    def test_a_name_only_match_is_not_listed_without_a_dead_parent(self):
        """A command that matches a known leftover shape but whose parent is
        still present is not reported -- the dead parent is the floor, the
        pattern is additional evidence, never sufficient alone."""
        table = [
            _proc(5, 0, command="/usr/bin/some-init"),
            _proc(50, 5, command="drunken-jira-mcp --stdio"),
        ]
        assert orphans.find_orphans(table) == []

    def test_a_dead_parent_alone_is_not_enough_without_a_matching_pattern(self):
        """A real daemon can be reparented too -- a dead parent with a command
        line that matches nothing known is not reported either."""
        table = [_proc(200, 999, command="/usr/bin/some-long-running-daemon")]
        assert orphans.find_orphans(table) == []

    def test_stdin_python_interpreter_matches(self):
        table = [_proc(300, 999, command="python - ")]
        assert len(orphans.find_orphans(table)) == 1

    def test_a_real_flag_like_python_dash_c_does_not_match_the_stdin_pattern(self):
        table = [_proc(301, 999, command="python -c 'print(1)'")]
        assert orphans.find_orphans(table) == []

    def test_uv_run_matches(self):
        table = [_proc(302, 999, command="uv run pytest")]
        assert len(orphans.find_orphans(table)) == 1

    def test_pyenv_shim_chain_matches(self):
        table = [_proc(303, 999, command="/home/user/.pyenv/shims/python script.py")]
        assert len(orphans.find_orphans(table)) == 1


class TestApplyReapReVerification:
    def test_reused_pid_with_a_different_start_time_is_skipped(self):
        """DG-518 ACCEPTANCE 1: a candidate's pid now belongs to a different
        process (same pid, different start time) -- never terminated."""
        candidate = OrphanProcess(100, 999, "original-start", "bash -c sleep")
        fresh_table = [
            _proc(100, 999, start_time="reused-start", command="bash -c sleep")
        ]
        terminated_pids = []

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminated_pids.append,
            list_processes_fn=lambda: fresh_table,
        )

        assert outcome.terminated == []
        assert terminated_pids == []
        assert outcome.skipped[0][0] == candidate
        assert "start time" in outcome.skipped[0][1]

    def test_pid_no_longer_present_is_skipped(self):
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        terminated_pids = []

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminated_pids.append,
            list_processes_fn=lambda: [],
        )

        assert outcome.terminated == []
        assert terminated_pids == []
        assert "no longer present" in outcome.skipped[0][1]

    def test_parent_alive_again_is_skipped(self):
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        fresh_table = [
            _proc(999, 1, command="restarted-parent"),
            _proc(100, 999, start_time="t1", command="bash -c sleep"),
        ]
        terminated_pids = []

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminated_pids.append,
            list_processes_fn=lambda: fresh_table,
        )

        assert outcome.terminated == []
        assert terminated_pids == []
        assert "parent" in outcome.skipped[0][1]

    def test_a_verified_candidate_is_terminated_only_with_apply_true(self):
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        fresh_table = [_proc(100, 999, start_time="t1", command="bash -c sleep")]
        terminated_pids = []

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminated_pids.append,
            list_processes_fn=lambda: fresh_table,
        )

        assert outcome.terminated == [candidate]
        assert terminated_pids == [100]
        assert outcome.skipped == []

    def test_plan_only_never_terminates_even_when_verified(self):
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        fresh_table = [_proc(100, 999, start_time="t1", command="bash -c sleep")]
        terminated_pids = []

        outcome = orphans.apply_reap(
            [candidate],
            apply=False,
            terminate_fn=terminated_pids.append,
            list_processes_fn=lambda: fresh_table,
        )

        assert terminated_pids == []
        assert outcome.terminated == [candidate]

    def test_only_candidates_from_the_plan_are_ever_considered(self):
        """A second orphan appearing in the fresh table but never in the
        plan is never touched, whatever it looks like."""
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        fresh_table = [
            _proc(100, 999, start_time="t1", command="bash -c sleep"),
            _proc(101, 998, start_time="t1", command="bash -c sleep too"),
        ]
        terminated_pids = []

        orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminated_pids.append,
            list_processes_fn=lambda: fresh_table,
        )

        assert terminated_pids == [100]

    def test_empty_plan_never_reads_the_process_table(self):
        calls = []
        orphans.apply_reap(
            [],
            apply=True,
            terminate_fn=lambda pid: None,
            list_processes_fn=lambda: calls.append("called") or [],
        )
        assert calls == []


class TestWindowsCimParsing:
    def test_parses_a_json_array_of_entries(self):
        text = (
            '[{"ProcessId": 100, "ParentProcessId": 1, '
            '"CreationDate": "2026-10-12T10:00:00", '
            '"CommandLine": "bash -c sleep 97"}]'
        )
        parsed = orphans.parse_windows_cim_json(text)
        assert parsed == [
            ProcessInfo(100, 1, "2026-10-12T10:00:00", "bash -c sleep 97")
        ]

    def test_a_single_result_comes_back_as_a_bare_object_not_an_array(self):
        text = (
            '{"ProcessId": 4, "ParentProcessId": 0, '
            '"CreationDate": null, "CommandLine": null}'
        )
        parsed = orphans.parse_windows_cim_json(text)
        assert parsed == [ProcessInfo(4, 0, "", "")]

    def test_empty_output_parses_to_an_empty_table(self):
        assert orphans.parse_windows_cim_json("") == []

    def test_unparseable_output_raises_process_table_unavailable(self):
        with pytest.raises(ProcessTableUnavailableError):
            orphans.parse_windows_cim_json("not json at all {{{")


class TestPosixPsParsing:
    def test_parses_pid_ppid_lstart_and_command(self):
        text = (
            "  PID  PPID                  STARTED COMMAND\n"
            "  100     1 Mon Oct 12 10:00:00 2026 bash -c sleep 97\n"
        )
        parsed = orphans.parse_posix_ps_output(text)
        assert parsed == [
            ProcessInfo(100, 1, "Mon Oct 12 10:00:00 2026", "bash -c sleep 97")
        ]

    def test_header_only_output_parses_to_an_empty_table(self):
        assert orphans.parse_posix_ps_output("  PID  PPID STARTED COMMAND\n") == []

    def test_empty_output_parses_to_an_empty_table(self):
        assert orphans.parse_posix_ps_output("") == []

    def test_a_short_line_that_cannot_be_a_real_row_is_skipped(self):
        text = "PID PPID STARTED COMMAND\ngarbage\n"
        assert orphans.parse_posix_ps_output(text) == []


class TestListProcessesDispatchesByPlatform:
    def test_win32_calls_the_windows_path(self, monkeypatch):
        monkeypatch.setattr(orphans, "_list_processes_windows", lambda: [_proc(1, 0)])
        monkeypatch.setattr(
            orphans,
            "_list_processes_posix",
            lambda: (_ for _ in ()).throw(AssertionError("posix path called")),
        )
        assert orphans.list_processes(platform="win32") == [_proc(1, 0)]

    def test_non_windows_calls_the_posix_path(self, monkeypatch):
        monkeypatch.setattr(
            orphans,
            "_list_processes_windows",
            lambda: (_ for _ in ()).throw(AssertionError("windows path called")),
        )
        monkeypatch.setattr(orphans, "_list_processes_posix", lambda: [_proc(2, 0)])
        assert orphans.list_processes(platform="linux") == [_proc(2, 0)]


class TestRunTextRaisesWhenTheProcessTableCannotBeRead:
    def test_a_missing_executable_raises_process_table_unavailable(self):
        with pytest.raises(ProcessTableUnavailableError):
            orphans._run_text(["a-command-that-almost-certainly-does-not-exist-dg518"])

    def test_a_nonzero_exit_raises_process_table_unavailable(self, monkeypatch):
        class _FakeCompleted:
            returncode = 1
            stdout = ""
            stderr = "boom"

        monkeypatch.setattr(
            orphans.subprocess, "run", lambda *a, **kw: _FakeCompleted()
        )
        with pytest.raises(ProcessTableUnavailableError):
            orphans._run_text(["whatever"])
