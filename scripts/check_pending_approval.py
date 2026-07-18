#!/usr/bin/env python3
"""Pre-commit safety net: block commits while the current ticket has a
pending or escalated Discord approval outstanding.

Warns (does not block) if the approval daemon isn't reachable at all —
routine local commits shouldn't be bricked by the daemon being down for an
unrelated reason.
"""

import asyncio
import os
import re
import subprocess
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))
from service.daemon_client import call_daemon  # noqa: E402

SOCKET_PATH = os.environ.get(
    "AGY_DAEMON_SOCKET", os.path.join(_REPO_ROOT, ".agents", "agy_daemon.sock")
)
TICKET_PATTERN = re.compile(r"([A-Z]+-\d+)")


def _current_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return out.stdout.strip()
    except Exception:
        return ""


async def _check_ticket(ticket_key: str) -> str:
    result = await call_daemon(
        {"cmd": "check_ticket", "ticket_key": ticket_key}, SOCKET_PATH, timeout=5
    )
    return str(result.get("status", "clear"))


def main() -> int:
    branch = _current_branch()
    match = TICKET_PATTERN.search(branch)
    if not match:
        # Nothing to correlate against, so this can't block — but say so
        # loudly rather than silently no-op, since a branch that just
        # doesn't match the naming convention would otherwise bypass this
        # safety net with zero visibility.
        print(
            f"[check_pending_approval] Branch '{branch}' has no recognizable "
            "ticket key (expected e.g. feature/DT-123-...) — cannot check for "
            "a pending approval, allowing the commit.",
            file=sys.stderr,
        )
        return 0

    ticket_key = match.group(1)

    if not os.path.exists(SOCKET_PATH):
        print(
            "[check_pending_approval] Approval daemon not running — skipping "
            f"the pending-approval check for {ticket_key} (warn-only).",
            file=sys.stderr,
        )
        return 0

    try:
        status = asyncio.run(_check_ticket(ticket_key))
    except Exception as e:
        print(
            f"[check_pending_approval] Could not reach approval daemon ({e}) — "
            f"skipping the pending-approval check for {ticket_key} (warn-only).",
            file=sys.stderr,
        )
        return 0

    if status in ("pending", "escalated"):
        print(
            f"\nBLOCKED: {ticket_key} has an unresolved Discord approval "
            f"({status}). Do not commit until it's resolved — check the "
            "ticket and Discord for details.\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
