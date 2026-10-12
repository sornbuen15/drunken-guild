# mypy: ignore-errors
"""``drunken-install reap`` (DG-518) — plan by default, ``--apply`` terminates
exactly the re-verified ids. Every test here monkeypatches ``core.orphans``
directly; nothing ever reads the real process table or signals a real pid.
"""

from __future__ import annotations

from core import doctor, install, orphans

_TOOL_ROOT = "C:/tools/drunken-guild/"
_BIN_SHIM = "C:/bin/drunken-jira-mcp"


def _proc(pid, ppid, start_time="t1", command=""):
    return orphans.ProcessInfo(
        pid=pid, ppid=ppid, start_time=start_time, command=command
    )


def _patch_mutable_world(monkeypatch, processes):
    """Monkeypatch ``orphans.list_processes``/``orphans.terminate_process``
    to share one mutable table, so that calling the (fake) terminator
    actually removes the pid -- which is what the post-termination
    verification in ``apply_reap``/``apply_lock_holders`` now checks for.
    Returns the list of pids the fake terminator was called with."""
    state = {p.pid: p for p in processes}
    terminated_pids: list[int] = []

    def list_processes():
        return list(state.values())

    def terminate_process(pid):
        terminated_pids.append(pid)
        state.pop(pid, None)

    monkeypatch.setattr(orphans, "list_processes", list_processes)
    monkeypatch.setattr(orphans, "terminate_process", terminate_process)
    return terminated_pids


class TestReapPlan:
    def test_plan_lists_candidates_and_touches_nothing(self, monkeypatch, capsys):
        monkeypatch.setattr(
            orphans,
            "list_processes",
            lambda: [_proc(100, 999, command="bash -c sleep 97")],
        )
        terminated = []
        monkeypatch.setattr(orphans, "terminate_process", terminated.append)

        exit_code = install.main(["reap"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "pid 100" in out
        assert "Nothing was touched" in out
        assert terminated == []

    def test_plan_with_no_orphans_says_so(self, monkeypatch, capsys):
        monkeypatch.setattr(
            orphans, "list_processes", lambda: [_proc(1, 0, command="init")]
        )

        exit_code = install.main(["reap"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "No leftover session processes found." in out

    def test_unreadable_process_table_is_refused_not_silently_empty(
        self, monkeypatch, capsys
    ):
        def _raise():
            raise orphans.ProcessTableUnavailableError("no ps on PATH")

        monkeypatch.setattr(orphans, "list_processes", _raise)

        exit_code = install.main(["reap"])
        err = capsys.readouterr().err

        assert exit_code == 1
        assert "no ps on PATH" in err


class TestReapApply:
    def test_apply_terminates_exactly_the_reverified_candidates(
        self, monkeypatch, capsys
    ):
        table = [_proc(100, 999, start_time="t1", command="bash -c sleep 97")]
        terminated = _patch_mutable_world(monkeypatch, table)

        exit_code = install.main(["reap", "--apply"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert terminated == [100]
        assert "terminated pid 100" in out

    def test_apply_skips_a_candidate_whose_start_time_changed_since_planning(
        self, monkeypatch, capsys
    ):
        """DG-518 ACCEPTANCE 1: a reused pid at a different start time is
        skipped by --apply, never terminated."""
        call_count = {"n": 0}

        def _list_processes():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return [
                    _proc(100, 999, start_time="original", command="bash -c sleep 97")
                ]
            # Re-verification sees a different process reusing the same pid.
            return [_proc(100, 999, start_time="reused", command="bash -c sleep 97")]

        monkeypatch.setattr(orphans, "list_processes", _list_processes)
        terminated = []
        monkeypatch.setattr(orphans, "terminate_process", terminated.append)

        exit_code = install.main(["reap", "--apply"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert terminated == []
        assert "skipped pid 100" in out
        assert "start time" in out


class TestReapLockHolders:
    """DG-518 scope addition: a lock holder is reported, and reaped, by its
    own executable path -- live parent or dead -- separately from the
    session-leftover-pattern orphans above."""

    def test_a_held_lock_holder_is_listed_but_not_terminated_without_include_held(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
        ]
        monkeypatch.setattr(orphans, "list_processes", lambda: table)
        terminated = []
        monkeypatch.setattr(orphans, "terminate_process", terminated.append)

        exit_code = install.main(["reap", "--apply"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert terminated == []
        assert "held by session 50" in out
        assert "--include-held" in out

    def test_include_held_terminates_the_reverified_lock_holder(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
        ]
        terminated = _patch_mutable_world(monkeypatch, table)

        exit_code = install.main(["reap", "--apply", "--include-held"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert terminated == [100]
        assert "terminated pid 100" in out

    def test_an_orphaned_lock_holder_is_terminated_without_include_held(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [_proc(100, 999, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio')]
        terminated = _patch_mutable_world(monkeypatch, table)

        exit_code = install.main(["reap", "--apply"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert terminated == [100]
        assert "terminated pid 100" in out


class TestReapSelfProtection:
    """DG-518 review, CRITICAL finding: ``reap`` never terminates itself or
    its own ancestor chain, shown in the plan with a dedicated label."""

    def test_the_running_reap_and_its_ancestors_are_shown_protected_and_untouched(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [
            _proc(5, 1, command="claude.exe"),
            _proc(50, 5, command="bash.exe"),
            _proc(999, 50, command="drunken-install.exe reap --apply --include-held"),
        ]
        terminated = _patch_mutable_world(monkeypatch, table)
        monkeypatch.setattr(orphans.os, "getpid", lambda: 999)

        exit_code = install.main(["reap", "--apply", "--include-held"])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert terminated == []
        assert orphans.PROTECTED_LABEL in out
        # the Claude session that launched this shell is named, not silently
        # dropped from the plan.
        assert "claude.exe" in out

    def test_a_sessions_mcp_tree_is_protected_while_a_different_sessions_is_not(
        self, monkeypatch, capsys
    ):
        """DG-518 review round 2 -- the exact real-machine shape reported:
        ``drunken-jira-mcp.exe`` and two ``python.exe`` children, as a
        *sibling* of the bash chain running ``reap`` under the same
        ``claude.exe`` session, must come out protected even with
        ``--include-held --apply``. The identical shape under a different
        ``claude.exe`` session is listed as held and is terminated."""
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [
            _proc(9784, 1, command="claude.exe"),
            _proc(50, 9784, command="bash.exe"),
            _proc(999, 50, command="drunken-install.exe reap --include-held --apply"),
            _proc(1192, 9784, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
            _proc(
                19392,
                1192,
                command=r'"C:\tools\drunken-guild\Scripts\python.exe" -m jira_mcp.server',
            ),
            _proc(
                17088,
                19392,
                command=r'"C:\tools\drunken-guild\Scripts\python.exe" worker',
            ),
            _proc(9000, 1, command="claude.exe"),
            _proc(9100, 9000, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
            _proc(
                9200,
                9100,
                command=r'"C:\tools\drunken-guild\Scripts\python.exe" -m jira_mcp.server',
            ),
            _proc(
                9300,
                9200,
                command=r'"C:\tools\drunken-guild\Scripts\python.exe" worker',
            ),
        ]
        terminated = _patch_mutable_world(monkeypatch, table)
        monkeypatch.setattr(orphans.os, "getpid", lambda: 999)

        exit_code = install.main(["reap", "--include-held", "--apply"])
        out = capsys.readouterr().out

        assert exit_code == 0
        # the protected session's own MCP tree is named, never terminated.
        assert "pid 1192" in out and orphans.PROTECTED_DESCENDANT_LABEL in out
        for pid in (1192, 19392, 17088):
            assert pid not in terminated
        # the other session's identical tree is listed as held, and IS
        # terminated with --include-held --apply.
        assert sorted(terminated) == [9100, 9200, 9300]
        assert "terminated pid 9100" in out


class TestPreUpdateLockHolderWarning:
    def test_skills_apply_warns_about_existing_lock_holders(
        self, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
        ]
        monkeypatch.setattr(orphans, "list_processes", lambda: table)

        exit_code = install.main(["skills", "--target", str(tmp_path / "skills")])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "1 guild process(es)" in out
        assert "drunken-install reap --include-held --apply" in out

    def test_dry_run_prints_no_warning(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(doctor, "guild_tool_paths", lambda: [_TOOL_ROOT, _BIN_SHIM])
        table = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, command=r'"C:\bin\drunken-jira-mcp.exe" --stdio'),
        ]
        monkeypatch.setattr(orphans, "list_processes", lambda: table)

        exit_code = install.main(
            ["skills", "--target", str(tmp_path / "skills"), "--dry-run"]
        )
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "guild process(es)" not in out

    def test_an_unreadable_process_table_never_blocks_the_update(
        self, monkeypatch, tmp_path, capsys
    ):
        def _raise():
            raise orphans.ProcessTableUnavailableError("no ps on PATH")

        monkeypatch.setattr(orphans, "list_processes", _raise)

        exit_code = install.main(["skills", "--target", str(tmp_path / "skills")])

        assert exit_code == 0

    def test_any_exception_anywhere_in_the_warning_never_blocks_the_update(
        self, monkeypatch, tmp_path, capsys
    ):
        """DG-518 review, MEDIUM finding: the whole body is wrapped, not just
        the process-table read -- a raising stub standing in for
        ``guild_tool_paths`` (or anything else in there) must still never
        fail, delay or change the outcome of an ordinary skills update."""

        def _raise(*_args, **_kwargs):
            raise RuntimeError("boom, anywhere in the warning")

        monkeypatch.setattr(
            orphans, "list_processes", lambda: [_proc(1, 0, command="init")]
        )
        monkeypatch.setattr(doctor, "guild_tool_paths", _raise)

        exit_code = install.main(["skills", "--target", str(tmp_path / "skills")])
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "Traceback" not in out
        assert "boom" not in out
