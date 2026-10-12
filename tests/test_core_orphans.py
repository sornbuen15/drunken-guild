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


def _mutable_world(processes):
    """A fake process table that actually shrinks when ``terminate_fn`` is
    called -- so the post-termination verification
    (``core.orphans._attempt_terminate``) sees a terminated pid as gone,
    the same way a real one would. Returns ``(list_processes_fn,
    terminate_fn, terminated_pids)``."""
    state = {p.pid: p for p in processes}
    terminated_pids: list[int] = []

    def list_processes_fn():
        return list(state.values())

    def terminate_fn(pid):
        terminated_pids.append(pid)
        state.pop(pid, None)

    return list_processes_fn, terminate_fn, terminated_pids


class TestFindOrphans:
    def test_leftover_pattern_is_a_substring_match_gated_by_a_dead_parent(self):
        """DG-518 review, LOW finding: ``is_session_leftover`` is a plain
        substring search (``re.search``), never anchored to the whole
        command or a whole token -- surrounding text either side is
        irrelevant. That alone is still not an orphan without a dead
        parent, which is the other half of the gate."""
        table = [
            _proc(1, 0, command="init"),
            _proc(
                100,
                1,
                command="/opt/wrapper/run.sh --then bash -c 'sleep 97' --after",
            ),
        ]
        assert orphans.find_orphans(table) == []  # live parent: not an orphan

        table_dead_parent = [
            _proc(100, 999, command="/opt/wrapper/run.sh --then bash -c 'sleep 97'"),
        ]
        assert len(orphans.find_orphans(table_dead_parent)) == 1

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
        list_processes_fn, terminate_fn, terminated_pids = _mutable_world(fresh_table)

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
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
        list_processes_fn, terminate_fn, terminated_pids = _mutable_world(fresh_table)

        orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
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


class TestProtectedPids:
    """DG-518 review, CRITICAL finding: ``reap`` must never terminate
    itself, any ancestor of it, or that ancestor's own query-helper
    children."""

    def test_the_running_pid_is_always_protected(self):
        table = [_proc(100, 1, command="drunken-install reap --apply")]
        assert orphans.protected_pids(table, self_pid=100) == {100}

    def test_the_whole_ancestor_chain_is_protected(self):
        """A table where the running pid and its parent chain (its shell,
        its terminal, the Claude session that launched it) are lock
        holders must come out fully protected."""
        table = [
            _proc(10, 1, command="claude.exe"),
            _proc(20, 10, command="bash.exe"),
            _proc(100, 20, command="drunken-install reap --apply --include-held"),
        ]
        assert orphans.protected_pids(table, self_pid=100) == {10, 20, 100}

    def test_a_claude_launched_shells_mcp_chain_is_protected(self):
        """When the plan is run from a Claude-launched shell, that
        session's own ancestor chain is shown as protected."""
        table = [
            _proc(5, 1, command="claude.exe"),
            _proc(50, 5, command="bash.exe -lc reap"),
            _proc(100, 50, command="drunken-install.exe reap --apply"),
        ]
        protected = orphans.protected_pids(table, self_pid=100)
        assert {5, 50, 100} <= protected

    def test_an_unrelated_lock_holder_is_not_protected_by_being_a_sibling(self):
        """Only the chain to the running pid is protected -- an unrelated
        lock holder elsewhere in the tree is an ordinary candidate."""
        table = [
            _proc(5, 1, command="claude.exe"),
            _proc(100, 5, command="drunken-install reap --apply"),
            _proc(200, 5, command="drunken-jira-mcp.exe --stdio"),
        ]
        assert orphans.protected_pids(table, self_pid=100) == {5, 100}

    def test_a_query_helper_child_of_a_protected_ancestor_is_protected(self):
        table = [
            _proc(5, 1, command="claude.exe"),
            _proc(100, 5, command="drunken-install reap --apply"),
            _proc(
                300,
                5,
                command="powershell -NoProfile -Command Get-CimInstance Win32_Process",
            ),
        ]
        assert 300 in orphans.protected_pids(table, self_pid=100)

    def test_apply_reap_never_terminates_a_protected_candidate_even_with_include_held_semantics(
        self,
    ):
        """The ancestor chain, planned as ordinary orphans/lock holders by
        mistake, still comes out completely untouched by ``apply_reap`` --
        the second, independent check, immediately before terminating."""
        table = [
            _proc(5, 1, command="claude.exe"),
            _proc(50, 5, command="bash.exe"),
            _proc(100, 50, command="drunken-install reap --apply"),
        ]
        candidates = [
            orphans.OrphanProcess(5, 1, "t1", "claude.exe"),
            orphans.OrphanProcess(50, 5, "t1", "bash.exe"),
            orphans.OrphanProcess(100, 50, "t1", "drunken-install reap --apply"),
        ]
        list_processes_fn, terminate_fn, terminated_pids = _mutable_world(table)

        outcome = orphans.apply_reap(
            candidates,
            apply=True,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
            self_pid=100,
        )

        assert terminated_pids == []
        assert outcome.terminated == []
        assert {c.pid for c, _ in outcome.skipped} == {5, 50, 100}
        assert all(reason == orphans.PROTECTED_LABEL for _, reason in outcome.skipped)

    def test_apply_lock_holders_never_terminates_a_protected_candidate_even_with_include_held(
        self,
    ):
        table = [
            _proc(5, 1, command="claude.exe"),
            _proc(100, 5, command="drunken-install reap --include-held --apply"),
        ]
        candidate = orphans.LockHolder(
            100,
            5,
            "t1",
            "drunken-install reap --include-held --apply",
            parent_alive=True,
        )
        list_processes_fn, terminate_fn, terminated_pids = _mutable_world(table)

        outcome = orphans.apply_lock_holders(
            [candidate],
            apply=True,
            include_held=True,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
            self_pid=100,
        )

        assert terminated_pids == []
        assert outcome.terminated == []
        assert outcome.skipped == [(candidate, orphans.PROTECTED_LABEL)]


class TestVerifiedTermination:
    """DG-518 review, HIGH finding: a termination is counted only once it is
    confirmed; one candidate's failure never aborts the rest, and the report
    always has something to say about every candidate."""

    def test_a_process_lookup_error_counts_as_already_gone(self):
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        table = [_proc(100, 999, start_time="t1", command="bash -c sleep")]

        def _raise_lookup(pid):
            raise ProcessLookupError("no such process")

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=_raise_lookup,
            list_processes_fn=lambda: table,
        )

        assert outcome.terminated == [candidate]
        assert outcome.skipped == []

    def test_a_permission_error_is_skipped_as_access_denied(self):
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        table = [_proc(100, 999, start_time="t1", command="bash -c sleep")]

        def _raise_permission(pid):
            raise PermissionError("denied")

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=_raise_permission,
            list_processes_fn=lambda: table,
        )

        assert outcome.terminated == []
        assert outcome.skipped == [(candidate, "access denied")]

    def test_a_process_still_present_after_terminate_fn_is_skipped_as_still_running(
        self,
    ):
        """``terminate_fn`` raising nothing is not enough -- the table is
        re-read and the pid must actually be gone (or reused)."""
        candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        table = [_proc(100, 999, start_time="t1", command="bash -c sleep")]

        outcome = orphans.apply_reap(
            [candidate],
            apply=True,
            terminate_fn=lambda pid: None,  # looks like it worked, but nothing changed
            list_processes_fn=lambda: table,
        )

        assert outcome.terminated == []
        assert outcome.skipped == [(candidate, "still running")]

    def test_one_failing_candidate_does_not_abort_the_rest_of_the_plan(self):
        ok_candidate = OrphanProcess(100, 999, "t1", "bash -c sleep")
        bad_candidate = OrphanProcess(200, 998, "t1", "uv run pytest")
        table = [
            _proc(100, 999, start_time="t1", command="bash -c sleep"),
            _proc(200, 998, start_time="t1", command="uv run pytest"),
        ]
        state = {p.pid: p for p in table}

        def terminate_fn(pid):
            if pid == 200:
                raise PermissionError("denied")
            state.pop(pid, None)

        outcome = orphans.apply_reap(
            [ok_candidate, bad_candidate],
            apply=True,
            terminate_fn=terminate_fn,
            list_processes_fn=lambda: list(state.values()),
        )

        assert outcome.terminated == [ok_candidate]
        assert outcome.skipped == [(bad_candidate, "access denied")]

    def test_taskkill_a_nonzero_exit_on_windows_is_treated_as_a_failure(
        self, monkeypatch
    ):
        monkeypatch.setattr(orphans.sys, "platform", "win32")

        class _FakeCompleted:
            returncode = 5
            stdout = ""
            stderr = "ERROR: Access is denied."

        monkeypatch.setattr(
            orphans.subprocess, "run", lambda *a, **kw: _FakeCompleted()
        )

        with pytest.raises(OSError):
            orphans.terminate_process(4321)


class TestFormatStartTime:
    """DG-518 review: a real machine's PowerShell printed the legacy
    ``/Date(...)/`` form, not an ISO string -- displayed, converted to a
    local, readable timestamp; never used for the equality check itself."""

    def test_a_dotnet_date_is_converted_to_local_iso(self):
        formatted = orphans.format_start_time("/Date(1791775989721)/")
        assert len(formatted) == 19  # "YYYY-MM-DD HH:MM:SS"
        assert formatted[4] == "-" and formatted[7] == "-" and formatted[10] == " "

    def test_a_plain_string_is_returned_unchanged(self):
        assert orphans.format_start_time("Mon Oct 12 10:00:00 2026") == (
            "Mon Oct 12 10:00:00 2026"
        )

    def test_an_unparseable_dotnet_looking_string_is_returned_unchanged(self):
        assert (
            orphans.format_start_time("/Date(not-a-number)/") == "/Date(not-a-number)/"
        )
