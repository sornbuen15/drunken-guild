#!/usr/bin/env python3
"""Remove servers this project does not own from a host's MCP config.

**This is the operator's tool, and it is deliberately not `drunken-config`.**

`drunken-config` already prunes, and prunes only its own: `is_drunken_managed`
matches ``drunken-*-mcp`` and nothing else, because `core/config_gen.py` records
that keeping foreign entries out of its reach is the point rather than a gap. A
generator that removed a server it never wrote is a generator nobody could trust
with a host's own file. Adding the foreign case there would have made one tool
answer two questions with two different owners.

So this is the other half, with the manners the other half needs:

- **It writes nothing without ``--apply``.** The default run says what it would
  do and stops. A host config is not this project's file.
- **A backup lands before the write,** as ``<name>.pre-<TICKET>.bak`` — the
  convention already sitting in that directory from DG-277 and DT-246. An
  existing backup is never overwritten: a second run must not replace the record
  of the original state with the already-pruned one.
- **A ``drunken-*-mcp`` name is refused outright.** Two tools that can both
  remove the same entry are two tools that can disagree about who removed it.
- **Servers are named explicitly, never inferred.** "Remove everything that does
  not resolve" would have taken Antigravity's own datacloud entries with it —
  they point at an uninstalled version, the host regenerates them, and they are
  none of our business. `drunken-doctor` reports them; that is the right
  division.

Usage:

    python scripts/clean_host_config.py \\
        --config ~/.gemini/config/mcp_config.json \\
        --drop jira-board --drop-archived --ticket DG-324

    ... then the same command with --apply once the printed plan looks right.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

#: The prefix and suffix `drunken-config` owns. Duplicated as a literal rather
#: than imported: this script must run from a checkout without the package
#: installed, which is exactly the situation an operator cleaning up a broken
#: host config is in. The guard is a refusal, so a stale copy fails closed.
MANAGED_PREFIX = "drunken-"
MANAGED_SUFFIX = "-mcp"

ARCHIVED_KEY = "archivedMcpServers"


def is_drunken_managed(name: str) -> bool:
    """True for a server `drunken-config` owns, current or retired."""
    return name.startswith(MANAGED_PREFIX) and name.endswith(MANAGED_SUFFIX)


def load(path: Path) -> Dict[str, Any]:
    """The host config, or exit saying why it will not be touched."""
    if not path.is_file():
        sys.exit(
            f"error: no host config at {path}. Refusing to create one — a config "
            "the host reads and nobody wrote is worse than none."
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"error: {path} is not valid JSON ({exc}). Refusing to rewrite it.")
    if not isinstance(document, dict):
        sys.exit(f"error: {path} is not a JSON object. Refusing to rewrite it.")
    return document


def back_up(path: Path, ticket: str) -> Path:
    """Copy the file aside before it is written, keeping any earlier copy.

    The first backup is the one worth having: it holds the state before anything
    was pruned. Overwriting it on a second run would leave a "backup" of the
    half-cleaned file, which looks like a recovery path and is not one.
    """
    backup = path.with_name(f"{path.name}.pre-{ticket}.bak")
    if backup.exists():
        print(f"  backup   {backup.name} exists already — kept, not overwritten")
        return backup
    shutil.copy2(path, backup)
    print(f"  backup   {backup.name}")
    return backup


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Remove named servers, and optionally the archived block, from a "
            "host MCP config. Prints the plan and writes nothing unless --apply."
        )
    )
    parser.add_argument(
        "--config", required=True, help="The host config to edit, e.g. ~/.gemini/..."
    )
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        metavar="SERVER",
        help="Server name to remove. Repeatable. Never inferred.",
    )
    parser.add_argument(
        "--drop-archived",
        action="store_true",
        help=f"Also remove the whole {ARCHIVED_KEY} block.",
    )
    parser.add_argument(
        "--ticket",
        default="manual",
        help="Ticket key for the backup filename. Defaults to 'manual'.",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually write. Off by default."
    )
    args = parser.parse_args(argv)

    path = Path(args.config).expanduser()

    # A refusal exits rather than returning a code. A caller that ignores a
    # return value would turn "this script will not touch that" into silence,
    # and the whole point of the guard is that it cannot be passed over.
    refused = [name for name in args.drop if is_drunken_managed(name)]
    if refused:
        sys.exit(
            f"error: {', '.join(refused)} is managed by drunken-config, which "
            "prunes it on every regeneration. Two tools that can both remove one "
            "entry can disagree about who removed it — this script will not "
            "touch that prefix. Run `drunken-config --kind host --out <file>`."
        )

    document = load(path)
    servers = document.get("mcpServers")
    servers = servers if isinstance(servers, dict) else {}

    print(f"{path}")
    print(
        f"  {len(servers)} server(s), "
        f"{'with' if ARCHIVED_KEY in document else 'no'} {ARCHIVED_KEY}"
    )

    removing = [name for name in args.drop if name in servers]
    for name in args.drop:
        if name in servers:
            print(f"  remove   {name}")
        else:
            print(f"  skip     {name} — not present in this config")

    archiving = args.drop_archived and ARCHIVED_KEY in document
    if args.drop_archived:
        if archiving:
            archived = document[ARCHIVED_KEY]
            names = ", ".join(archived) if isinstance(archived, dict) else "?"
            print(f"  remove   {ARCHIVED_KEY} ({names})")
        else:
            print(f"  skip     {ARCHIVED_KEY} — not present in this config")

    if not removing and not archiving:
        print("  nothing to do.")
        return 0

    if not args.apply:
        print("\n  Dry run — nothing written. Re-run with --apply.")
        return 0

    back_up(path, args.ticket)
    for name in removing:
        del servers[name]
    if archiving:
        del document[ARCHIVED_KEY]
    document["mcpServers"] = servers
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"\n  Written. {len(servers)} server(s) remain.")
    print("  Verify with: drunken-doctor --project <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
