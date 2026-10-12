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

**Review findings (DG-518):** :func:`protected_pids` keeps the running
``reap`` itself, and every ancestor of it (its shell, its terminal, the
Claude session that launched it), off every terminate list, in both
:func:`apply_reap` and :func:`apply_lock_holders` — never only at plan time.
Every termination is itself verified (:func:`_attempt_terminate`) before
being counted, and one candidate's failure is recorded and skipped rather
than ever aborting the rest of a plan.
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

    Each pattern is a plain **substring match** against the full command
    line (``re.search``, not an anchored or whole-token match) — gated,
    always, by the dead-parent test in :func:`find_orphans`: this function
    alone is necessary, never sufficient, to call anything an orphan.
    """
    return any(pattern.search(command) for pattern in _LEFTOVER_PATTERNS)


def find_orphans(processes: Sequence[ProcessInfo]) -> list[OrphanProcess]:
    """Processes whose parent is gone **and** whose command line matches a
    known session-leftover shape (a substring match — see
    :func:`is_session_leftover`). Read-only; never kills anything.

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


def _ancestor_chain(
    processes: Sequence[ProcessInfo], self_pid: Optional[int] = None
) -> list[int]:
    """The running process itself (``os.getpid()`` by default), then every
    ancestor of it found in *processes*, nearest first, walking the ``ppid``
    chain until one is not in the table."""
    pid = self_pid if self_pid is not None else os.getpid()
    by_pid = {process.pid: process for process in processes}
    chain = [pid]
    seen = {pid}
    current = pid
    while current in by_pid:
        parent_pid = by_pid[current].ppid
        if parent_pid in seen or parent_pid not in by_pid:
            break
        chain.append(parent_pid)
        seen.add(parent_pid)
        current = parent_pid
    return chain


def protected_ancestors(
    processes: Sequence[ProcessInfo], self_pid: Optional[int] = None
) -> set[int]:
    """The running process itself and every ancestor of it found in
    *processes* — its shell, its terminal, the Claude session that launched
    it, the desktop app, the OS shell — as a set (DG-518 review, CRITICAL
    self-protection finding). See :func:`protected_pids` for what else is
    protected alongside this chain.
    """
    return set(_ancestor_chain(processes, self_pid=self_pid))


def _normalize_name(name: str) -> str:
    """*name*, case-folded only on Windows — same rule as every other path
    comparison in this module."""
    return name.casefold() if sys.platform == "win32" else name


def _is_explorer(process: Optional[ProcessInfo]) -> bool:
    if process is None:
        return False
    return _normalize_name(_program_basename(process.command)) == "explorer.exe"


#: Exact basenames (case-normalized) this module never selects as a session
#: root (DG-518 review round 4) — a shell or interpreter, never a session
#: concept of its own. A real session process spawns many of these side by
#: side (one ``bash.exe`` chain per tool call, nested shells inside each),
#: and matching on "shares a name with a sibling" against *these* is exactly
#: how a shell got chosen as the root instead of the ``claude.exe`` session
#: hosting it — see :func:`_session_root`.
_SHELL_LIKE_NAMES: Final = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "cmd",
        "powershell",
        "pwsh",
        "node",
        "uv",
    }
)


def _is_shell_or_interpreter(basename: str) -> bool:
    """Whether *basename* (already case-normalized) names a shell or
    interpreter — never a session root (DG-518 review round 4)."""
    stem = basename[:-4] if basename.endswith(".exe") else basename
    return (
        stem in _SHELL_LIKE_NAMES
        or stem.startswith("python")
        or stem.startswith("drunken-")
    )


def _session_root(
    processes: Sequence[ProcessInfo],
    chain: Sequence[int],
    by_pid: dict[int, ProcessInfo],
) -> int:
    """Which pid in *chain* is the **session root** — DG-518 review round 3
    (scoping descendant expansion to one ancestor, not every one) and round
    4 (this rule, below, misfiring on a shell).

    Round 3's rule — the nearest ancestor sharing a name with a sibling
    under the same parent, or a direct child of ``Explorer.EXE`` — still
    matched a ``bash.exe`` on a real machine: a Claude session spawns many
    ``bash.exe`` chains side by side, one per tool call, so "shares a name
    with a sibling" fired on a shell nested in the running ``reap``'s own
    chain, long before the walk ever reached the actual ``claude.exe``
    session. A shell or interpreter (:func:`_is_shell_or_interpreter` —
    ``bash``, ``sh``, ``zsh``, ``cmd``, ``powershell``, ``pwsh``, ``python*``,
    ``node``, ``uv``, ``drunken-*``) is therefore never even considered here,
    whichever condition would otherwise have matched it.

    Among what remains, walking the chain from the running process outward,
    the nearest ancestor that either (a) shares its own executable's full
    **path** — not merely its file name — with a sibling under the same
    parent (several session processes launched from the identical binary,
    side by side — the signature of "one app, several sessions", and the
    reason this is a path comparison: two different, same-named programs
    must never be mistaken for the same session) or (b) is itself a direct
    child of ``Explorer.EXE`` wins. Whichever is found nearer to the running
    process wins between the two.

    If neither ever matches anywhere in the chain, the conservative fallback
    walks outward from two hops above the running process (never closer)
    until it finds an ancestor that is not itself a shell or interpreter;
    narrow, and never reaching further up than it has to.
    """
    children_by_ppid: dict[int, list[int]] = {}
    for entry in processes:
        children_by_ppid.setdefault(entry.ppid, []).append(entry.pid)

    for pid in chain[1:]:
        process = by_pid.get(pid)
        if process is None:
            continue
        parent = by_pid.get(process.ppid)
        if parent is None:
            continue
        own_name = _normalize_name(_program_basename(process.command))
        if _is_shell_or_interpreter(own_name):
            continue
        own_path = _normalize_path_text(_first_token(process.command))
        path_sibling_match = bool(own_path) and any(
            sibling_pid != pid
            and _normalize_path_text(_first_token(by_pid[sibling_pid].command))
            == own_path
            for sibling_pid in children_by_ppid.get(process.ppid, [])
            if sibling_pid in by_pid
        )
        if path_sibling_match or _is_explorer(parent):
            return pid

    for pid in chain[2:]:
        process = by_pid.get(pid)
        if process is None:
            continue
        if not _is_shell_or_interpreter(
            _normalize_name(_program_basename(process.command))
        ):
            return pid

    return chain[-1]


def protected_pids(
    processes: Sequence[ProcessInfo], self_pid: Optional[int] = None
) -> set[int]:
    """Never-reap pids, for *this run of* ``reap``: :func:`protected_ancestors`
    plus every descendant of the **session root** alone — see
    :func:`_session_root` for how that one ancestor is chosen and why round
    2's "every ancestor" swept in two unrelated Claude sessions and every
    webview2 helper on the desktop, found on a real machine.

    Labeled distinctly by whichever caller reports it:
    :data:`PROTECTED_LABEL` for the chain itself, :data:`PROTECTED_DESCENDANT_LABEL`
    for everything under the session root. An unrelated session (a sibling
    of the session root, or anywhere outside its subtree) is untouched by
    this function, and stays an ordinary, terminable candidate.
    """
    by_pid = {process.pid: process for process in processes}
    chain = _ancestor_chain(processes, self_pid=self_pid)
    ancestors = set(chain)
    root = _session_root(processes, chain, by_pid)

    children_by_ppid: dict[int, list[int]] = {}
    for process in processes:
        children_by_ppid.setdefault(process.ppid, []).append(process.pid)

    protected = set(ancestors)
    protected.add(root)
    frontier = [root]
    while frontier:
        parent_pid = frontier.pop()
        for child_pid in children_by_ppid.get(parent_pid, []):
            if child_pid not in protected:
                protected.add(child_pid)
                frontier.append(child_pid)
    return protected


#: The label shown in a reap plan for the running ``reap`` itself, or one of
#: its ancestors (its shell, the Claude session that launched it) -- never
#: terminated, whatever flag is passed.
PROTECTED_LABEL: Final = "this session (running reap) -- never stopped"

#: The label for anything *else* under a protected ancestor's own tree (DG-518
#: review round 2) -- a lock holder's MCP server and its own children, which
#: are "this session's tools" even though they are not on the direct path to
#: the running ``reap`` process.
PROTECTED_DESCENDANT_LABEL: Final = (
    "this session's tools (running reap) -- never stopped"
)


def _protected_label(pid: int, ancestors: set[int]) -> str:
    return PROTECTED_LABEL if pid in ancestors else PROTECTED_DESCENDANT_LABEL


def _attempt_terminate(
    pid: int,
    expected_start_time: str,
    *,
    terminate_fn: Callable[[int], None],
    list_processes_fn: Callable[[], Sequence[ProcessInfo]],
) -> tuple[bool, str]:
    """Call *terminate_fn*, then confirm it actually worked (DG-518 review,
    HIGH finding): re-read the process table once more and check *pid* is
    either gone or now has a different ``start_time`` (a new process reusing
    the same number). Returns ``(True, "")`` only once that is confirmed;
    otherwise ``(False, <reason>)`` — ``"access denied"``,
    ``"still running"``, or whatever the failure said — and never raises:
    one candidate's failure must never stop the rest of a plan from running,
    and the caller's report is always printed.
    """
    try:
        terminate_fn(pid)
    except ProcessLookupError:
        return True, ""  # already gone -- the goal was already true
    except PermissionError:
        return False, "access denied"
    except Exception as exc:  # noqa: BLE001 - one candidate must never abort the rest
        return False, f"could not terminate: {exc}"

    try:
        after = {process.pid: process for process in list_processes_fn()}
    except Exception as exc:  # noqa: BLE001 - see above
        return False, f"could not confirm termination: {exc}"

    still_there = after.get(pid)
    if still_there is None or still_there.start_time != expected_start_time:
        return True, ""
    return False, "still running"


def apply_reap(
    candidates: Sequence[OrphanProcess],
    *,
    apply: bool,
    terminate_fn: Callable[[int], None],
    list_processes_fn: Callable[[], Sequence[ProcessInfo]],
    self_pid: Optional[int] = None,
) -> ReapOutcome:
    """Re-verify, then (only with ``apply=True``) terminate exactly *candidates*.

    *list_processes_fn* is called once, immediately before any termination, so
    every candidate is checked against the same fresh snapshot — never a
    second, later read that could itself have gone stale between candidates.
    A candidate is terminated only when, in that snapshot, the same pid still
    has the same ``start_time`` (a reused pid at a different start time is a
    different process), its parent is still absent, and it is not one of
    :func:`protected_pids` (the running ``reap`` itself, or an ancestor of
    it — DG-518 review, layer 2: :func:`core.install._reap_plan` already
    excludes these at plan time; this is the second check, immediately before
    anything is touched). Nothing outside *candidates* is ever considered,
    whatever the snapshot contains.

    Each termination is itself verified (:func:`_attempt_terminate`) before
    being counted — one candidate's failure (access denied, still running)
    is recorded in ``skipped`` and never stops the rest of the plan.

    Raises :class:`ProcessTableUnavailableError` if *list_processes_fn* does
    — propagated, never swallowed into an empty, falsely-safe outcome.
    """
    outcome = ReapOutcome()
    if not candidates:
        return outcome

    current = list_processes_fn()
    current_by_pid = {process.pid: process for process in current}
    live_pids = set(current_by_pid)
    ancestors = protected_ancestors(current, self_pid=self_pid)
    protected = protected_pids(current, self_pid=self_pid)

    for candidate in candidates:
        if candidate.pid in protected:
            outcome.skipped.append(
                (candidate, _protected_label(candidate.pid, ancestors))
            )
            continue
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
        if not apply:
            outcome.terminated.append(candidate)
            continue
        ok, reason = _attempt_terminate(
            candidate.pid,
            candidate.start_time,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
        )
        if ok:
            outcome.terminated.append(candidate)
        else:
            outcome.skipped.append((candidate, reason))

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


def _program_basename(command: str) -> str:
    """Just the executable's own file name — ``claude.exe``, not the full
    path — for a human-readable label (DG-518 review)."""
    token = _first_token(command).replace("\\", "/")
    return token.rsplit("/", 1)[-1] if token else ""


def _matches_tool_root(program: str, root: str) -> bool:
    """Whether normalized *program* counts as "inside" normalized *root*.

    A root ending in ``/`` is a **directory** — the installed tool
    environment itself — and matches by exact path prefix, so anything
    actually inside that tree counts. Anything else is an **exact
    console-script shim path**, matched exactly or with a bare ``.exe``
    suffix — never as a prefix (DG-518 review: a prefix match on a bin
    directory swept in any unrelated ``drunken-my-own-script`` a user
    happened to drop beside the real shims).
    """
    if not root:
        return False
    if root.endswith("/"):
        return program.startswith(root)
    return program == root or program == root + ".exe"


def is_inside_guild_tool(command: str, tool_roots: Sequence[str]) -> bool:
    """Whether *command*'s own executable path is one of *tool_roots* — the
    installed tool environment's directory (a path prefix), or one of this
    package's own console-script shims (an exact file, never a bare-prefix
    "any ``drunken-*`` name") — never a bare name match, so a same-named
    program living anywhere else never counts (DG-518 scope addition).
    *tool_roots* is normally :func:`core.doctor.guild_tool_paths`.
    """
    program = _normalize_path_text(_first_token(command))
    if not program:
        return False
    return any(
        _matches_tool_root(program, _normalize_path_text(root)) for root in tool_roots
    )


_DOTNET_DATE_RE: Final = re.compile(r"^/Date\((-?\d+)\)/$")


def format_start_time(raw: str) -> str:
    """*raw* as a human-readable local ``YYYY-MM-DD HH:MM:SS``, for display
    only — never used for re-verification, which always compares the raw,
    unformatted value for exact equality against a later read of the same pid.

    Handles the legacy .NET ``/Date(<milliseconds-since-epoch>)/`` form a real
    machine's PowerShell emitted for a CIM ``CreationDate`` (DG-518 review);
    anything else — a plain ISO-ish string, POSIX ``lstart`` text — is
    returned unchanged rather than guessed at.
    """
    match = _DOTNET_DATE_RE.match(raw.strip())
    if not match:
        return raw
    try:
        from datetime import datetime

        return datetime.fromtimestamp(int(match.group(1)) / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (OverflowError, OSError, ValueError):
        return raw


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
            parent_name = _program_basename(parent.command)
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
    self_pid: Optional[int] = None,
) -> LockHolderOutcome:
    """The lock-holder twin of :func:`apply_reap` (DG-518 scope addition).

    A dead-parented lock holder is reaped exactly like a plain orphan —
    nothing else is managing it. A live-parented one is left alone unless
    *include_held* is ``True``: terminating it stops a running guild process
    (an MCP server, most often) that a session still depends on, and that
    must be the Boss's own, explicit choice, never a default. Every
    candidate is re-verified against one fresh snapshot of the process
    table — same pid, same start time, the same live/dead parent state it
    was planned with, and not one of :func:`protected_pids` (DG-518 review:
    the running ``reap`` itself and its ancestors are never terminated,
    whatever flag is passed) — immediately before anything is terminated.
    Each termination is itself verified (:func:`_attempt_terminate`) before
    being counted; one candidate's failure never stops the rest.
    """
    outcome = LockHolderOutcome()
    if not candidates:
        return outcome

    current = list_processes_fn()
    current_by_pid = {process.pid: process for process in current}
    live_pids = set(current_by_pid)
    ancestors = protected_ancestors(current, self_pid=self_pid)
    protected = protected_pids(current, self_pid=self_pid)

    for candidate in candidates:
        if candidate.pid in protected:
            outcome.skipped.append(
                (candidate, _protected_label(candidate.pid, ancestors))
            )
            continue
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
        if not apply:
            outcome.terminated.append(candidate)
            continue
        ok, reason = _attempt_terminate(
            candidate.pid,
            candidate.start_time,
            terminate_fn=terminate_fn,
            list_processes_fn=list_processes_fn,
        )
        if ok:
            outcome.terminated.append(candidate)
        else:
            outcome.skipped.append((candidate, reason))

    return outcome


def terminate_process(pid: int) -> None:
    """The only real terminator in this module — never called by a test, and
    never called by anything but ``drunken-install reap --apply`` run by a
    human. ``taskkill /F`` on Windows (``os.kill`` has no real ``SIGTERM`` on
    that platform); ``SIGTERM`` on POSIX.

    Raises ``OSError`` (DG-518 review, HIGH finding) when ``taskkill``'s own
    return code says it failed — ``5`` (access denied), ``128`` (no such
    process), or anything else nonzero — so :func:`_attempt_terminate` sees a
    real failure instead of a silent no-op. ``os.kill`` already raises
    ``ProcessLookupError``/``PermissionError`` on POSIX for the equivalent
    cases; both are handled by the same caller.
    """
    if sys.platform == "win32":
        result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell, pid is an int
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:200]
            raise OSError(f"taskkill exited {result.returncode}: {detail}")
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
