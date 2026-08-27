import argparse
import os

# Fixed argv, never a shell, and only ever `git rev-parse HEAD` — see _head_sha.
import subprocess  # nosec B404
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from core import paths
from service.daemon_client import call_daemon

mcp = FastMCP("drunken-discord-mcp")


# Resolved through core.paths, which is the only thing the daemon and this
# client both agree on. Anchoring it to this file's own location worked from a
# checkout and pointed inside the virtualenv once installed, at which point the
# client reports the daemon as down while it is running.
#
# Called rather than captured: a container sets DRUNKEN_DAEMON_SOCKET in its
# entrypoint, which a value frozen at import time would miss.
# DG-313: which project this server was started for. Set once in main() from
# --project, and it decides which daemon we dial -- one per project, so an
# approval raised here cannot surface in another project's Discord room.
_PROJECT: str | None = None


def socket_path() -> str:
    return str(paths.daemon_socket_path(_PROJECT))


# Generous ceiling above the daemon's own 2-attempt approval window (default
# 15 min x 2 = 30 min) so we don't time out the socket call before the daemon
# has a chance to escalate and answer on its own.
SOCKET_TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_SOCKET_TIMEOUT_SECONDS", "2400"))


@mcp.tool()  # type: ignore[misc]
async def request_boss_approval(action: str, reason: str, ticket_key: str) -> str:
    """
    DEPRECATED, kept until 3.0.0 — use request_boss_approval_async instead.

    Asks the Boss on Discord and blocks until they answer. Blocking is the
    problem: nothing else gets done while it waits.

    If the Boss is reading this conversation, just ask them here.
    """
    if not os.path.exists(socket_path()):
        return (
            f"Discord approval is unavailable right now (no daemon socket at "
            f"{socket_path()} — it's either not running or was never set up). "
            "This does NOT mean skip approval: if you're in an interactive "
            "session, ask the Boss directly here in the conversation instead. "
            "Only stop and refuse to proceed if you have no way to reach them "
            "at all (e.g. you're running unattended with no one to ask)."
        )

    try:
        result = await call_daemon(
            {
                "cmd": "request_boss_approval",
                "action": action,
                "reason": reason,
                "ticket_key": ticket_key,
            },
            socket_path(),
            SOCKET_TIMEOUT_SECONDS,
        )
    except Exception as e:
        return (
            f"Discord approval is unavailable right now ({e}). This does NOT "
            "mean skip approval: if you're in an interactive session, ask "
            "the Boss directly here in the conversation instead. Only stop "
            "and refuse to proceed if you have no way to reach them at all."
        )

    status = result.get("status", "unknown")
    if status == "approved":
        return "Approved by Boss."
    if status == "rejected":
        return "Rejected by Boss."
    if status == "escalated":
        return (
            f"No response after 2 reminders — task stopped, ticket {ticket_key} "
            "has been commented, and Boss has been notified on Discord. "
            "Do not continue this task and do not commit."
        )
    return f"Unexpected daemon response: {result}"


def _head_sha() -> str | None:
    """Current HEAD, used to bind an approval to the code it was granted for.

    Best-effort: outside a checkout there is simply nothing to bind to, and
    that is not a reason to refuse to ask for approval.

    Resolved from this process's working directory, which is the project the
    agent is actually working in — the host launches one stdio server per
    project. Pinning it to drunken-guild's own checkout, as it used to, bound an
    approval for work in TWA to a commit in a different repository.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


async def _call(payload: dict[str, Any]) -> dict[str, Any] | str:
    """Talk to the daemon, or explain in words why we could not."""
    if not os.path.exists(socket_path()):
        return (
            f"Discord approval is unavailable right now (no daemon socket at "
            f"{socket_path()} — it's either not running or was never set up). "
            "This does NOT mean skip approval: if you're in an interactive "
            "session, ask the Boss directly here in the conversation instead."
        )
    try:
        return await call_daemon(payload, socket_path(), SOCKET_TIMEOUT_SECONDS)
    except Exception as e:
        return (
            f"Discord approval is unavailable right now ({e}). This does NOT "
            "mean skip approval: if you're in an interactive session, ask the "
            "Boss directly here in the conversation instead."
        )


@mcp.tool()  # type: ignore[misc]
async def request_boss_approval_async(action: str, reason: str, ticket_key: str) -> str:
    """
    Ask the Boss on Discord and return immediately with a request id.

    Then: park this task without doing the action, take the next unblocked one,
    and collect with check_approvals when you finish a task or start a session
    — never mid-task. Do not poll and do not schedule a wake-up.

    No deadline; nothing is killed for going unanswered. Reminders back off
    15 min → 1 h → daily.

    If the Boss is reading this conversation, just ask them here.
    """
    result = await _call(
        {
            "cmd": "submit_approval",
            "action": action,
            "reason": reason,
            "ticket_key": ticket_key,
            "commit_sha": _head_sha(),
        }
    )
    if isinstance(result, str):
        return result
    req_id = result.get("req_id")
    if not req_id:
        return f"Unexpected daemon response: {result}"
    return (
        f"Submitted — request id {req_id}. The Boss has been asked on Discord. "
        "Park this task, get on with anything that isn't blocked by it, and "
        f"call check_approvals(['{req_id}']) when you next finish a task or "
        "start a new session. Do not take the action until it comes back approved."
    )


@mcp.tool()  # type: ignore[misc]
async def check_approvals(req_ids: list[str]) -> str:
    """
    Collect answers to request_boss_approval_async. Does not block.

    Call it when you finish a task or start a session — never mid-task. Reading
    an answer does not consume it, so retrying after a crash is safe.

      approved — do exactly what was approved.
      rejected — do not. The reason is included; respect it.
      pending  — leave the task parked and move on.
      stale    — approved against a different commit, so it no longer covers
                 the code. Ask again.
      unknown  — never submitted, or lost with the daemon. Re-submit; do not
                 assume either answer.
    """
    result = await _call(
        {"cmd": "poll_approvals", "req_ids": req_ids, "commit_sha": _head_sha()}
    )
    if isinstance(result, str):
        return result

    results = result.get("results") or {}
    if not results:
        return "No matching approval requests."

    lines = []
    for req_id, payload in results.items():
        status = payload.get("status", "unknown")
        bits = [f"{req_id}: {status.upper()}"]
        if payload.get("action"):
            bits.append(f"action={payload['action']!r}")
        if payload.get("ticket_key"):
            bits.append(payload["ticket_key"])
        line = "  ".join(bits)
        if payload.get("detail"):
            line += f"\n    {payload['detail']}"
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    """Entry point for the MCP server."""
    global _PROJECT

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project",
        type=str,
        help="Project ID. Selects which daemon socket to dial (DG-313).",
    )
    args, unknown = parser.parse_known_args()

    # DG-313: this used to be parsed and thrown away -- the help text said
    # "ignored by discord, kept for compat" -- so every project's server dialled
    # one shared socket and got whichever channel that daemon was pinned to.
    # Falling back to DRUNKEN_PROJECT keeps a server started without the flag
    # working, and with neither set the socket name is unchanged.
    _PROJECT = args.project or os.environ.get("DRUNKEN_PROJECT", "").strip() or None

    # Remove from sys.argv to prevent FastMCP from complaining about unknown args
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        sys.argv.pop(idx)
        if len(sys.argv) > idx:
            sys.argv.pop(idx)

    mcp.run()


if __name__ == "__main__":
    main()
