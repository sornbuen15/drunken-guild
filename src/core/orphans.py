"""``processes.orphans`` and ``drunken-install reap`` — DG-518.

FINDING this answers: the Boss sees shells, browsers and stray interpreters left
running after a session ends. Windows does not kill children when their parent
exits, so a background command started by an agent — or a stdin interpreter left
waiting forever once a tool's own timeout moved it to the background — outlives
the session that started it, silently.

Two things live here, both read-only until a human says otherwise:

* :func:`find_orphans` — a process counts only when **both** are true: its parent
  process id is no longer present in the table at all (a dead parent — never
  "ppid looks suspicious", nothing is inferred from a name alone) **and** its
  command line matches a known session-leftover shape. An MCP server or a
  browser helper with a live parent never matches, however its command line
  reads — the dead-parent test is the floor, the pattern is additional evidence,
  and neither is sufficient on its own.
* :func:`apply_reap` — terminates exactly the ids a prior :func:`find_orphans`
  call named, each one re-verified **immediately before** it is touched: still
  that pid, still that same start time (a reused pid is a different process even
  at the same number), and its parent still absent. Anything that no longer
  matches all three is skipped, named, and never terminated — this is the one
  function in this module an agent must never call with ``apply=True``; it is
  wired only into ``drunken-install reap --apply``, a command for the Boss to
  run themselves.

Nothing here is ever killed by inference. A caller that cannot read the process
table at all gets :class:`ProcessTableUnavailableError` instead of an empty,
falsely reassuring list — silence here would read as "nothing to report" when
the honest answer is "could not look".

**Lock holders** (DG-518 scope addition, measured on Windows): ``uv tool
install --force`` fails outright while a process still has an open handle on
a file inside the installed tool — and the parent of that process is very
often alive: the desktop app keeps a ``drunken-jira-mcp.exe`` and its python
child running for a session it itself lists as not running, with no window
open. A dead parent is therefore the wrong test for *this* question.
:func:`find_lock_holders` instead matches the executable's own path against
the installed tool's directories (:func:`is_inside_guild_tool` — an exact
path prefix, case-insensitive only on Windows, never a bare name match), live
parent or dead, and labels each one accordingly. :func:`apply_lock_holders`
reaps a dead-parented one exactly like a plain orphan, and a live-parented
one only with ``include_held=True`` — terminating a held MCP server stops it
until the session restarts it, which must be the Boss's explicit choice.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess  # nosec B404 - fixed argv, shell=False, no user input
import sys
from dataclasses import dataclass, field
from typing import Callable, Final, Optional, Sequence

from .errors import DrunkenError


class ProcessTableUnavailableError(DrunkenError):
    """The process table could not be read at all (DG-518).

    Deliberately not an empty list: a caller that cannot look must say so
    rather than reporting a clean bill of health it never actually checked.
    """

    code = "process_table_unavailable"


@dataclass(frozen=True)
class ProcessInfo:
    """One row of the process table, platform-neutral."""

    pid: int
    ppid: int
    #: Opaque and platform-specific (a CIM ``CreationDate`` string on Windows,
    #: ``ps -o lstart`` text on POSIX) — never parsed as a real timestamp here,
    #: only ever compared for equality against the same pid later.
    start_time: str
    command: str


@dataclass(frozen=True)
class OrphanProcess:
    """One candidate :func:`find_orphans` named — what a plan lists, and the
    only shape :func:`apply_reap` is ever handed to act on."""

    pid: int
    ppid: int
    start_time: str
    command: str

    @classmethod
    def from_process(cls, process: ProcessInfo) -> "OrphanProcess":
        return cls(process.pid, process.ppid, process.start_time, process.command)


@dataclass
class ReapOutcome:
    """What :func:`apply_reap` did (or, with ``apply=False``, would do)."""

    terminated: list[OrphanProcess] = field(default_factory=list)
    #: Candidate plus the reason it was skipped — never terminated.
    skipped: list[tuple[OrphanProcess, str]] = field(default_factory=list)


#: Known session-leftover shapes (DG-518 SCOPE 1). Matched against the full
#: command line, never the pid or the name alone — a process named
#: ``python.exe`` with a live parent is an ordinary interpreter, not evidence
#: of anything.
_LEFTOVER_PATTERNS: Final = (
    re.compile(r"\bbash\s+-c\b"),
    re.compile(r"\bsh\s+-c\b"),
    # A stdin interpreter: `python -`, `python3 -`, `python3.11 -`, the same
    # on Windows with `.exe`. The trailing `-` must be its own token, not the
    # start of a real flag such as `-c` or `-m`.
    re.compile(r"(?:^|[\\/])python(?:\d+(?:\.\d+)?)?(?:\.exe)?\s+-(?:\s|$)"),
    re.compile(r"pyenv[\\/]+shims"),
    re.compile(r"drunken-jira-mcp"),
    re.compile(r"\buv\s+run\b"),
)


def is_session_leftover(command: str) -> bool:
    """Whether *command* matches a known session-leftover shape.

    Necessary, never sufficient on its own — see :func:`find_orphans`.
    """
    return any(pattern.search(command) for pattern in _LEFTOVER_PATTERNS)


def find_orphans(processes: Sequence[ProcessInfo]) -> list[OrphanProcess]:
    """Processes whose parent is gone **and** whose command line matches a
    known session-leftover shape. Read-only; never kills anything.

    A dead parent alone is not enough — a legitimate daemon can be reparented
    too — and a matching command line with a live parent is not enough either,
    which is what keeps a healthy ``drunken-jira-mcp`` server or a webview2
    helper (both seen with live parents) off this list.
    """
    live_pids = {process.pid for process in processes}
    return [
        OrphanProcess.from_process(process)
        for process in processes
        if process.ppid not in live_pids and is_session_leftover(process.command)
    ]


def apply_reap(
    candidates: Sequence[OrphanProcess],
    *,
    apply: bool,
    terminate_fn: Callable[[int], None],
    list_processes_fn: Callable[[], Sequence[ProcessInfo]],
) -> ReapOutcome:
    """Re-verify, then (only with ``apply=True``) terminate exactly *candidates*.

    *list_processes_fn* is called once, immediately before any termination, so
    every candidate is checked against the same fresh snapshot — never a
    second, later read that could itself have gone stale between candidates.
    A candidate is terminated only when, in that snapshot, the same pid still
    has the same ``start_time`` (a reused pid at a different start time is a
    different process) and its parent is still absent. Nothing outside
    *candidates* is ever considered, whatever the snapshot contains.

    Raises :class:`ProcessTableUnavailableError` if *list_processes_fn* does
    — propagated, never swallowed into an empty, falsely-safe outcome.
    """
    outcome = ReapOutcome()
    if not candidates:
        return outcome

    current = list_processes_fn()
    current_by_pid = {process.pid: process for process in current}
    live_pids = set(current_by_pid)

    for candidate in candidates:
        now = current_by_pid.get(candidate.pid)
        if now is None:
            outcome.skipped.append((candidate, "no longer present"))
            continue
        if now.start_time != candidate.start_time:
            outcome.skipped.append(
                (candidate, "pid reused by a different process (start time changed)")
            )
            continue
        if now.ppid in live_pids:
            outcome.skipped.append((candidate, "parent is alive again"))
            continue
        if apply:
            terminate_fn(candidate.pid)
        outcome.terminated.append(candidate)

    return outcome


def _normalize_path_text(text: str) -> str:
    """*text*, forward-slashed and quote-stripped, case-folded only on
    Windows — filesystem paths are case-insensitive there and nowhere else."""
    cleaned = text.strip().strip('"').strip("'").replace("\\", "/")
    return cleaned.casefold() if sys.platform == "win32" else cleaned


def _first_token(command: str) -> str:
    """The program a command line starts with — the quoted form if it is
    quoted, otherwise the first whitespace-delimited token."""
    stripped = command.strip()
    if not stripped:
        return ""
    if stripped[0] in ('"', "'"):
        quote = stripped[0]
        end = stripped.find(quote, 1)
        if end != -1:
            return stripped[1:end]
    return stripped.split(None, 1)[0]


def is_inside_guild_tool(command: str, tool_roots: Sequence[str]) -> bool:
    """Whether *command*'s own executable path starts with one of
    *tool_roots* — an exact path prefix, never a bare name match, so a
    same-named program living anywhere else never counts (DG-518 scope
    addition). *tool_roots* is normally :func:`core.doctor.guild_tool_paths`:
    the installed tool environment's own directory, and the ``drunken-*``
    console-script shim prefix beside it.
    """
    program = _normalize_path_text(_first_token(command))
    if not program:
        return False
    return any(
        program.startswith(_normalize_path_text(root)) for root in tool_roots if root
    )


@dataclass(frozen=True)
class LockHolder:
    """A process whose executable lives inside the installed guild tool,
    whatever its parent (DG-518 scope addition) — what :func:`find_lock_holders`
    lists and the only shape :func:`apply_lock_holders` ever acts on."""

    pid: int
    ppid: int
    start_time: str
    command: str
    parent_alive: bool
    #: The parent's own program, best-effort, only when ``parent_alive``.
    parent_name: str = ""

    @property
    def label(self) -> str:
        if not self.parent_alive:
            return "orphan"
        suffix = f" ({self.parent_name})" if self.parent_name else ""
        return f"held by session {self.ppid}{suffix}"


def find_lock_holders(
    processes: Sequence[ProcessInfo], tool_roots: Sequence[str]
) -> list[LockHolder]:
    """Every process whose executable is inside *tool_roots*, live parent or
    dead (DG-518 scope addition) — these hold files ``uv tool install
    --force`` needs to overwrite even while a session keeps their parent
    alive, which :func:`find_orphans` alone never reports because it requires
    a dead parent. Empty *tool_roots* (nothing resolved) means no claim is
    made either way, not "none found".
    """
    if not tool_roots:
        return []
    by_pid = {process.pid: process for process in processes}
    live_pids = set(by_pid)
    holders: list[LockHolder] = []
    for process in processes:
        if not is_inside_guild_tool(process.command, tool_roots):
            continue
        parent_alive = process.ppid in live_pids
        parent_name = ""
        if parent_alive:
            parent = by_pid[process.ppid]
            parent_name = _first_token(parent.command)
        holders.append(
            LockHolder(
                pid=process.pid,
                ppid=process.ppid,
                start_time=process.start_time,
                command=process.command,
                parent_alive=parent_alive,
                parent_name=parent_name,
            )
        )
    return holders


@dataclass
class LockHolderOutcome:
    """The lock-holder twin of :class:`ReapOutcome` — what
    :func:`apply_lock_holders` did, or would do."""

    terminated: list[LockHolder] = field(default_factory=list)
    skipped: list[tuple[LockHolder, str]] = field(default_factory=list)


def apply_lock_holders(
    candidates: Sequence[LockHolder],
    *,
    apply: bool,
    include_held: bool,
    terminate_fn: Callable[[int], None],
    list_processes_fn: Callable[[], Sequence[ProcessInfo]],
) -> LockHolderOutcome:
    """The lock-holder twin of :func:`apply_reap` (DG-518 scope addition).

    A dead-parented lock holder is reaped exactly like a plain orphan —
    nothing else is managing it. A live-parented one is left alone unless
    *include_held* is ``True``: terminating it stops a running guild process
    (an MCP server, most often) that a session still depends on, and that
    must be the Boss's own, explicit choice, never a default. Every
    candidate is re-verified against one fresh snapshot of the process
    table — same pid, same start time, and the same live/dead parent state
    it was planned with — immediately before anything is terminated.
    """
    outcome = LockHolderOutcome()
    if not candidates:
        return outcome

    current = list_processes_fn()
    current_by_pid = {process.pid: process for process in current}
    live_pids = set(current_by_pid)

    for candidate in candidates:
        now = current_by_pid.get(candidate.pid)
        if now is None:
            outcome.skipped.append((candidate, "no longer present"))
            continue
        if now.start_time != candidate.start_time:
            outcome.skipped.append(
                (candidate, "pid reused by a different process (start time changed)")
            )
            continue
        parent_alive_now = now.ppid in live_pids
        if parent_alive_now and not include_held:
            outcome.skipped.append(
                (
                    candidate,
                    f"parent (pid {now.ppid}) is alive; re-run with "
                    "--include-held to terminate it anyway",
                )
            )
            continue
        if apply:
            terminate_fn(candidate.pid)
        outcome.terminated.append(candidate)

    return outcome


def terminate_process(pid: int) -> None:
    """The only real terminator in this module — never called by a test, and
    never called by anything but ``drunken-install reap --apply`` run by a
    human. ``taskkill /F`` on Windows (``os.kill`` has no real ``SIGTERM`` on
    that platform); ``SIGTERM`` on POSIX."""
    if sys.platform == "win32":
        subprocess.run(  # nosec B603 B607 - fixed argv, no shell, pid is an int
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    else:
        os.kill(pid, signal.SIGTERM)


def _run_text(argv: Sequence[str], *, timeout: float = 15.0) -> str:
    """*argv*'s stdout, or :class:`ProcessTableUnavailableError` naming why not."""
    try:
        result = subprocess.run(  # nosec B603 - fixed argv, shell=False
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcessTableUnavailableError(
            f"could not run {argv[0]!r}: {exc}",
            remediation="Install or add the process-listing tool to PATH.",
        ) from exc
    if result.returncode != 0:
        raise ProcessTableUnavailableError(
            f"{argv[0]!r} exited {result.returncode}: {result.stderr.strip()[:300]}",
            remediation="Check that the process-listing tool runs on this machine.",
        )
    return result.stdout


def parse_windows_cim_json(text: str) -> list[ProcessInfo]:
    """Parse ``Get-CimInstance Win32_Process | ConvertTo-Json`` output.

    A single result comes back as a JSON object rather than a one-element
    array — handled here so a machine with exactly one process never raises.
    """
    stripped = text.strip()
    if not stripped:
        return []
    try:
        data = json.loads(stripped)
    except ValueError as exc:
        raise ProcessTableUnavailableError(
            f"could not parse the process table: {exc}"
        ) from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ProcessTableUnavailableError(
            "the process table was not a JSON array or object"
        )

    processes: list[ProcessInfo] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("ProcessId")
        ppid = entry.get("ParentProcessId")
        if pid is None or ppid is None:
            continue
        try:
            processes.append(
                ProcessInfo(
                    pid=int(pid),
                    ppid=int(ppid),
                    start_time=str(entry.get("CreationDate") or ""),
                    command=str(entry.get("CommandLine") or ""),
                )
            )
        except (TypeError, ValueError):
            continue
    return processes


def parse_posix_ps_output(text: str) -> list[ProcessInfo]:
    """Parse ``ps -eo pid,ppid,lstart,command`` output (a header row, then
    ``pid ppid <5-token lstart> command...`` per line)."""
    lines = text.splitlines()
    if not lines:
        return []

    processes: list[ProcessInfo] = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        # pid, ppid, then 5 lstart tokens (day, month, date, time, year), then
        # the rest of the line is the command, however many spaces it holds.
        parts = stripped.split(None, 7)
        if len(parts) < 8:
            continue
        pid_raw, ppid_raw = parts[0], parts[1]
        start_time = " ".join(parts[2:7])
        command = parts[7]
        try:
            processes.append(
                ProcessInfo(
                    pid=int(pid_raw),
                    ppid=int(ppid_raw),
                    start_time=start_time,
                    command=command,
                )
            )
        except ValueError:
            continue
    return processes


def _list_processes_windows() -> list[ProcessInfo]:
    text = _run_text(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | "
            "ConvertTo-Json -Compress",
        ]
    )
    return parse_windows_cim_json(text)


def _list_processes_posix() -> list[ProcessInfo]:
    text = _run_text(["ps", "-eo", "pid,ppid,lstart,command"])
    return parse_posix_ps_output(text)


def list_processes(platform: Optional[str] = None) -> list[ProcessInfo]:
    """The current process table. Windows via CIM, POSIX via ``ps``.

    Raises :class:`ProcessTableUnavailableError` rather than ever returning an
    empty list when the table genuinely could not be read.
    """
    if (platform or sys.platform) == "win32":
        return _list_processes_windows()
    return _list_processes_posix()
