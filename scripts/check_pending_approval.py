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

# Import bootstrap only: pre-commit runs this with `language: system`, whose
# `python` is not necessarily the one that has this project installed. This
# locates *code*, which is what __file__ is for — the state path below comes
# from core.paths, and must, or this hook checks the wrong socket.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
)
from core import paths  # noqa: E402
from service.daemon_client import call_daemon  # noqa: E402


def socket_path() -> str:
    """The daemon's socket, resolved the same way the daemon resolves it.

    This hook fails open by design — a daemon that is down must not stop you
    committing. That is exactly what made the previous version's mistake
    invisible: it pointed at the pre-DG-241 path, found nothing, reported
    "daemon not running", and returned 0. pre-commit printed Passed while the
    check could not run at all.
    """
    return str(paths.daemon_socket_path())


TICKET_PATTERN = re.compile(r"([A-Z]+-\d+)")


def _current_branch() -> str:
    """The branch being committed to.

    Resolved from the working directory rather than a fixed repo: pre-commit
    runs the hook from the root of whichever repository is being committed to,
    and pinning it to this checkout would read drunken-guild's branch while
    guarding a commit somewhere else entirely.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


async def _check_ticket(ticket_key: str) -> str:
    result = await call_daemon(
        {"cmd": "check_ticket", "ticket_key": ticket_key}, socket_path(), timeout=5
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
            "ticket key (expected e.g. feature/DG-123-...) — cannot check for "
            "a pending approval, allowing the commit.",
            file=sys.stderr,
        )
        return 0

    ticket_key = match.group(1)

    if not os.path.exists(socket_path()):
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
