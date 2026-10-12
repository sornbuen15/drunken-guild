# mypy: ignore-errors
"""``core.orphans`` lock holders — DG-518 scope addition (measured on Windows,
2026-10-12): ``uv tool install --force`` fails while a guild process still
holds a file inside the installed tool, and that process's parent is very
often alive (the desktop app keeps ``drunken-jira-mcp.exe`` running for a
session it itself lists as not running). A dead-parent test alone misses
these, so a lock holder is identified by its own executable path instead,
whatever its parent.

Every test hands in a fixed process table and a fixed ``tool_roots`` list;
nothing here ever reads the real process table or signals a real process.
"""

from __future__ import annotations

from core import orphans
from core.orphans import LockHolder, ProcessInfo


def _proc(pid, ppid, start_time="t1", command=""):
    return ProcessInfo(pid=pid, ppid=ppid, start_time=start_time, command=command)


def _mutable_world(processes):
    """A fake process table that actually shrinks when ``terminate_fn`` is
    called, so post-termination verification sees a terminated pid as gone.
    Returns ``(list_processes_fn, terminate_fn, terminated_pids)``."""
    state = {p.pid: p for p in processes}
    terminated_pids: list[int] = []

    def list_processes_fn():
        return list(state.values())

    def terminate_fn(pid):
        terminated_pids.append(pid)
        state.pop(pid, None)

    return list_processes_fn, terminate_fn, terminated_pids


_TOOL_ROOT = "C:/Users/op/AppData/Roaming/uv/tools/drunken-guild/"
_BIN_SHIM = "C:/Users/op/.local/bin/drunken-jira-mcp"


class TestIsInsideGuildTool:
    def test_a_path_under_the_tool_root_matches(self):
        command = r'"C:\Users\op\AppData\Roaming\uv\tools\drunken-guild\Scripts\python.exe" -m jira_mcp.server'
        assert orphans.is_inside_guild_tool(command, [_TOOL_ROOT, _BIN_SHIM])

    def test_a_known_bin_shim_matches_exactly(self):
        command = r"C:\Users\op\.local\bin\drunken-jira-mcp.exe --stdio"
        assert orphans.is_inside_guild_tool(command, [_TOOL_ROOT, _BIN_SHIM])

    def test_an_unrelated_script_sharing_the_drunken_prefix_does_not_match(self):
        """DG-518 review, MEDIUM finding: matching every ``drunken-*`` name in
        the bin directory swept in any unrelated script a user happened to
        drop there. Only the exact, known console-script names count."""
        command = r"C:\Users\op\.local\bin\drunken-my-own-script.exe --help"
        assert not orphans.is_inside_guild_tool(command, [_TOOL_ROOT, _BIN_SHIM])

    def test_matching_is_case_insensitive_on_windows_paths(self, monkeypatch):
        monkeypatch.setattr(orphans.sys, "platform", "win32")
        command = (
            r'"c:\users\op\appdata\roaming\uv\tools\drunken-guild\scripts\python.exe"'
        )
        assert orphans.is_inside_guild_tool(command, [_TOOL_ROOT, _BIN_SHIM])

    def test_a_similarly_named_directory_does_not_match_as_a_prefix(self):
        """`drunken-guild2` must never match the `drunken-guild` root -- this
        is an exact path-prefix test with a boundary, not a substring test."""
        command = (
            r'"C:\Users\op\AppData\Roaming\uv\tools\drunken-guild2\Scripts\python.exe"'
        )
        assert not orphans.is_inside_guild_tool(command, [_TOOL_ROOT, _BIN_SHIM])

    def test_a_same_named_program_elsewhere_on_disk_does_not_match(self):
        """No name-only matching -- only the real installed path counts."""
        command = r'"C:\Users\someone\Desktop\drunken-jira-mcp.exe" --stdio'
        assert not orphans.is_inside_guild_tool(command, [_TOOL_ROOT, _BIN_SHIM])

    def test_empty_tool_roots_never_matches(self):
        command = (
            r'"C:\Users\op\AppData\Roaming\uv\tools\drunken-guild\Scripts\python.exe"'
        )
        assert not orphans.is_inside_guild_tool(command, [])


class TestFindLockHolders:
    def test_a_lock_holder_with_a_live_parent_is_labeled_held(self):
        table = [
            _proc(50, 1, command="claude.exe"),
            _proc(
                100,
                50,
                command=r'"C:\Users\op\.local\bin\drunken-jira-mcp.exe" --stdio',
            ),
        ]
        holders = orphans.find_lock_holders(table, [_TOOL_ROOT, _BIN_SHIM])
        assert holders == [
            LockHolder(
                100,
                50,
                "t1",
                r'"C:\Users\op\.local\bin\drunken-jira-mcp.exe" --stdio',
                parent_alive=True,
                parent_name="claude.exe",
            )
        ]
        assert holders[0].label == "held by session 50 (claude.exe)"

    def test_a_lock_holder_with_a_dead_parent_is_labeled_orphan(self):
        table = [
            _proc(
                100,
                999,
                command=r'"C:\Users\op\.local\bin\drunken-jira-mcp.exe" --stdio',
            ),
        ]
        holders = orphans.find_lock_holders(table, [_TOOL_ROOT, _BIN_SHIM])
        assert len(holders) == 1
        assert holders[0].parent_alive is False
        assert holders[0].label == "orphan"

    def test_a_process_outside_the_tool_roots_is_never_a_lock_holder(self):
        table = [_proc(1, 0, command="init"), _proc(100, 1, command="bash -c sleep")]
        assert orphans.find_lock_holders(table, [_TOOL_ROOT, _BIN_SHIM]) == []

    def test_empty_tool_roots_reports_no_lock_holders_rather_than_guessing(self):
        table = [
            _proc(
                100,
                1,
                command=r'"C:\Users\op\.local\bin\drunken-jira-mcp.exe" --stdio',
            )
        ]
        assert orphans.find_lock_holders(table, []) == []


class TestApplyLockHolders:
    def _held(self, pid=100, ppid=50, start_time="t1"):
        return LockHolder(
            pid, ppid, start_time, "drunken-jira-mcp.exe", parent_alive=True
        )

    def test_a_held_lock_holder_is_skipped_without_include_held(self):
        candidate = self._held()
        fresh = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, start_time="t1", command="drunken-jira-mcp.exe"),
        ]
        terminated = []

        outcome = orphans.apply_lock_holders(
            [candidate],
            apply=True,
            include_held=False,
            terminate_fn=terminated.append,
            list_processes_fn=lambda: fresh,
        )

        assert outcome.terminated == []
        assert terminated == []
        assert "include-held" in outcome.skipped[0][1]

    def test_a_held_lock_holder_is_terminated_with_include_held(self):
        candidate = self._held()
        fresh = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, start_time="t1", command="drunken-jira-mcp.exe"),
        ]
        list_processes_fn, terminate_fn, terminated = _mutable_world(fresh)

        outcome = orphans.apply_lock_holders(
            [candidate],
            apply=True,
            include_held=True,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
        )

        assert terminated == [100]
        assert outcome.terminated == [candidate]

    def test_an_orphaned_lock_holder_is_terminated_even_without_include_held(self):
        candidate = LockHolder(
            100, 999, "t1", "drunken-jira-mcp.exe", parent_alive=False
        )
        fresh = [_proc(100, 999, start_time="t1", command="drunken-jira-mcp.exe")]
        list_processes_fn, terminate_fn, terminated = _mutable_world(fresh)

        outcome = orphans.apply_lock_holders(
            [candidate],
            apply=True,
            include_held=False,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
        )

        assert terminated == [100]
        assert outcome.terminated == [candidate]

    def test_a_reused_pid_with_a_different_start_time_is_skipped(self):
        candidate = self._held()
        fresh = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, start_time="reused", command="drunken-jira-mcp.exe"),
        ]
        terminated = []

        outcome = orphans.apply_lock_holders(
            [candidate],
            apply=True,
            include_held=True,
            terminate_fn=terminated.append,
            list_processes_fn=lambda: fresh,
        )

        assert terminated == []
        assert "start time" in outcome.skipped[0][1]

    def test_plan_only_never_terminates(self):
        candidate = self._held()
        fresh = [
            _proc(50, 1, command="claude.exe"),
            _proc(100, 50, start_time="t1", command="drunken-jira-mcp.exe"),
        ]
        terminated = []

        orphans.apply_lock_holders(
            [candidate],
            apply=False,
            include_held=True,
            terminate_fn=terminated.append,
            list_processes_fn=lambda: fresh,
        )

        assert terminated == []
