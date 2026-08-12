import argparse
import os

# Fixed argv, never a shell, and only ever `git rev-parse HEAD` — see _head_sha.
import subprocess  # nosec B404
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from service.daemon_client import call_daemon

mcp = FastMCP("drunken-discord-mcp")

# Anchored to the repo root via this file's own location (not os.getcwd()) so
# it agrees with the daemon's socket path regardless of which directory this
# MCP stdio subprocess happens to be launched from.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOCKET_PATH = os.environ.get(
    "AGY_DAEMON_SOCKET", os.path.join(_REPO_ROOT, ".agents", "agy_daemon.sock")
)
# Generous ceiling above the daemon's own 2-attempt approval window (default
# 15 min x 2 = 30 min) so we don't time out the socket call before the daemon
# has a chance to escalate and answer on its own.
SOCKET_TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_SOCKET_TIMEOUT_SECONDS", "2400"))


@mcp.tool()  # type: ignore[misc]
async def request_boss_approval(action: str, reason: str, ticket_key: str) -> str:
    """
    Request approval from the Boss via Discord and BLOCK until answered.

    Use this specifically when the Boss may NOT be watching this conversation
    right now (a dispatched/background task, or they've stepped away) — that's
    the whole point of routing through Discord instead of just asking here.

    If you're in a live, interactive session and the Boss is right here
    reading your responses, don't reach for this tool at all — just ask them
    directly in the conversation, like you normally would. Discord is a
    fallback channel for reaching them when they're away, not the only way
    to get approval. If Discord isn't configured or the daemon isn't running,
    this tool tells you to do exactly that instead of failing you closed.

    This call genuinely waits for a reply — do not schedule a follow-up
    check and do not end your turn to "come back later". It returns only
    once the Boss has reacted, or after 2 unanswered reminders trigger
    auto-escalation (the task is stopped for you at that point).

    Args:
        action: A short description of the action you want to take or what you need.
        reason: Why you need to take this action or need this clarification.
        ticket_key: The Jira ticket key this work belongs to (e.g. "DT-65").
            Required — it's how an escalation gets commented onto the right
            ticket and how the pre-commit safety net knows what to block.

    Returns:
        A final answer string. If it says the task was escalated, treat that
        as an instruction: stop, do not continue, and do not commit. If it
        says Discord is unavailable, ask the Boss directly in this
        conversation instead — do not just proceed without approval.
    """
    if not os.path.exists(SOCKET_PATH):
        return (
            f"Discord approval is unavailable right now (no daemon socket at "
            f"{SOCKET_PATH} — it's either not running or was never set up). "
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
            SOCKET_PATH,
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
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
    except Exception:
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


async def _call(payload: dict[str, Any]) -> dict[str, Any] | str:
    """Talk to the daemon, or explain in words why we could not."""
    if not os.path.exists(SOCKET_PATH):
        return (
            f"Discord approval is unavailable right now (no daemon socket at "
            f"{SOCKET_PATH} — it's either not running or was never set up). "
            "This does NOT mean skip approval: if you're in an interactive "
            "session, ask the Boss directly here in the conversation instead."
        )
    try:
        return await call_daemon(payload, SOCKET_PATH, SOCKET_TIMEOUT_SECONDS)
    except Exception as e:
        return (
            f"Discord approval is unavailable right now ({e}). This does NOT "
            "mean skip approval: if you're in an interactive session, ask the "
            "Boss directly here in the conversation instead."
        )


@mcp.tool()  # type: ignore[misc]
async def request_boss_approval_async(action: str, reason: str, ticket_key: str) -> str:
    """
    Ask the Boss on Discord and return IMMEDIATELY, without waiting.

    Prefer this over request_boss_approval whenever you have other work you
    could be getting on with. It posts the question and hands you back a
    request id; the Boss answers in their own time, and you collect the
    answer later with check_approvals.

    What to do with the id you get back:
      1. Park this task — record that it is waiting on this req_id, and do
         NOT carry on with the action you just asked about.
      2. Pick up the next task that is not blocked by it. If nothing else is
         available, say what you are waiting on and end your turn. Do not
         sit in a loop polling, and do not schedule a wake-up just to check.
      3. Call check_approvals when you next finish a task, or at the start of
         your next session. Finish whatever is in your hands first — an
         answer arriving is never a reason to abandon work half-done.

    There is no deadline and nothing gets killed for going unanswered. The
    Boss gets reminded at a decreasing rate (15 min, an hour, then daily)
    until they reply, however long that takes.

    Args:
        action: The action you want to take, described in one short line.
        reason: Why it is needed.
        ticket_key: The Jira ticket this belongs to (e.g. "DT-232").

    Returns:
        A request id to poll with, or a message explaining that Discord is
        unreachable — in which case ask the Boss directly instead.
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
    Collect answers to requests made with request_boss_approval_async.

    Does not block: whatever has been answered comes back, and anything
    still outstanding is reported as pending. Reading an answer does not
    consume it, so polling again after a crash is safe.

    Call this when you finish a task and at the start of a session — not on
    a timer, and never in the middle of work you have already started.

    Statuses you can get back:
      - approved  — go ahead with exactly the action that was approved.
      - rejected  — do not do it. The reason is included; respect it.
      - pending   — no answer yet. Leave the task parked and move on.
      - stale     — it was approved, but against a different commit. The code
                    has changed since the Boss said yes, so that yes no longer
                    covers it. Ask again with request_boss_approval_async.
      - unknown   — never submitted, or lost with a daemon that died before
                    it could persist. Re-submit; do not assume either answer.

    Args:
        req_ids: The request ids you are waiting on.

    Returns:
        A readable line per request.
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project", type=str, help="Project ID (ignored by discord, kept for compat)"
    )
    args, unknown = parser.parse_known_args()

    # Remove from sys.argv to prevent FastMCP from complaining about unknown args
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        sys.argv.pop(idx)
        if len(sys.argv) > idx:
            sys.argv.pop(idx)

    mcp.run()


if __name__ == "__main__":
    main()
