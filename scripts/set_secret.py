#!/usr/bin/env python3
"""Put a secret into ``$DRUNKEN_HOME/secrets.json``, without it being seen.

The gap this fills: `migrate_env_to_registry.py` lifts a credential out of an
existing `.env`, and `onboard_project.py` requires one to already be there.
Neither can *rotate* one, so the only route was hand-editing JSON that holds
the only copy of a live credential — which is a poor place to make a typo.

Three properties, each deliberate:

**Never on the command line.** The value is read from a hidden prompt or from
stdin, never taken as an argument. An argument lands in shell history and is
visible in `ps` to every process on the machine for as long as this runs.

**Never echoed.** Not while typing, not in the confirmation. The confirmation
prints a truncated SHA-256 instead, which is enough to check that two machines
hold the same value without either of them showing it.

**Written at 0600 from the start**, with the file created at that mode rather
than chmod-ed afterwards — in between, it exists at whatever the umask allowed.

Rotating is the case this was written for, and it is one edit precisely because
every project references this file rather than copying from it.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core import paths  # noqa: E402

SECRETS_MODE = 0o600


def fingerprint(value: str) -> str:
    """Enough to compare two copies, useless for reconstructing either."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def read_document(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise SystemExit(
            f"error: {path} is not valid JSON.\n"
            "  -> Fix it by hand. Refusing to overwrite a file that may hold "
            "the only copy of a credential."
        ) from None
    return loaded if isinstance(loaded, dict) else {}


def write_document(path: Path, document: Dict[str, Any]) -> None:
    paths.ensure_home()
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, SECRETS_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=4, sort_keys=True)
        handle.write("\n")
    os.chmod(path, SECRETS_MODE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="set_secret.py",
        description=(
            "Store or rotate a secret. The value is prompted for, never passed "
            "as an argument."
        ),
        epilog=(
            "Example: set_secret.py jira.default   then paste the token at the "
            "prompt. Nothing is echoed."
        ),
    )
    parser.add_argument(
        "key",
        help="Dotted path inside secrets.json, e.g. jira.default or discord.default",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read the value from stdin instead of prompting, for scripted use.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    parts = args.key.split(".")
    if len(parts) != 2 or not all(parts):
        print(
            f"error: expected a two-part key like 'jira.default', got {args.key!r}",
            file=sys.stderr,
        )
        return 1
    section, name = parts

    if args.stdin:
        value = sys.stdin.read().strip()
    else:
        value = getpass.getpass(f"Value for {args.key} (input hidden): ").strip()

    if not value:
        print("error: empty value, nothing written.", file=sys.stderr)
        return 1

    if value.startswith(("env://", "file://", "op://", "keyring://", "literal://")):
        print(
            "error: that looks like a reference, not a secret. This file holds "
            "the value the reference points *at*.",
            file=sys.stderr,
        )
        return 1

    path = paths.home().path / "secrets.json"
    document = read_document(path)
    previous = document.get(section, {}).get(name)
    document.setdefault(section, {})[name] = value
    write_document(path, document)

    print(f"stored          : {args.key}  ->  {path}  (mode 600)")
    if previous and previous != value:
        print(f"  replaced      : {fingerprint(previous)}  (now invalid if revoked)")
    print(f"  fingerprint   : {fingerprint(value)}")
    print("\nEverything referencing this picks it up on next use. Confirm with:")
    print("  drunken-doctor --project <id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
