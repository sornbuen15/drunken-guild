import argparse
import os
import sys

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
