#!/usr/bin/env python3
"""Move credentials out of ``.env`` and into the registry the servers read.

Why this exists
---------------
2.2.0 deleted ``jira_mcp/config.py`` and its ``.env`` parent-walk (S3) and
replaced it with the registry plus :mod:`core.secrets`. Nothing carried the
existing credentials across, so on any machine set up before 2.2.0 the Jira MCP
server answers every call with "started without a project" while the older
shell paths keep working — which is exactly why it went unnoticed.

This script is the missing step. It reads ``.env`` **in-process**, writes the
token into a secrets file under ``$DRUNKEN_HOME``, and registers the project
with a ``file://`` *reference* to it. The token is never printed, never passed
as an argument, and never reaches the registry — only the reference does.

``drunken-init`` does the registry write, deliberately: it is the documented
command, and a second implementation of it here is how two of them drift apart.

Safe to re-run: the secrets file is merged key by key, and ``drunken-init`` is
itself idempotent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core import paths  # noqa: E402
from core.registry import validate_project_id  # noqa: E402

#: Read-write for the owner only. The directory above is already 0700.
SECRETS_MODE = 0o600


def load_env_file(path: Path) -> Dict[str, str]:
    """Parse ``KEY=value`` lines. Values stay in memory and are never logged."""
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        values[key.strip()] = raw.strip().strip('"').strip("'")
    return values


def value_of(*names: str, env_file: Dict[str, str]) -> Optional[str]:
    """First value found, checking the real environment before the file.

    Several names per value because the token has two of them in the wild:
    ``.env.example`` documents ``JIRA_API_TOKEN`` while ``jira_bridge.py`` reads
    ``JIRA_TOKEN`` first, so real ``.env`` files carry either.
    """
    for name in names:
        found = os.environ.get(name) or env_file.get(name)
        if found:
            return found
    return None


def merge_secrets(secrets_path: Path, additions: Dict[str, Dict[str, str]]) -> None:
    """Merge *additions* into the secrets file, one nested level deep.

    Merged rather than overwritten so that migrating one project does not
    silently drop another project's credential.
    """
    document: Dict[str, Dict[str, str]] = {}
    if secrets_path.is_file():
        try:
            loaded = json.loads(secrets_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                document = loaded
        except json.JSONDecodeError:
            raise SystemExit(
                f"error: {secrets_path} exists but is not valid JSON.\n"
                "  -> Fix or move it; refusing to overwrite a file that may "
                "hold the only copy of a credential."
            ) from None

    for section, entries in additions.items():
        document.setdefault(section, {}).update(entries)

    # Create with the right mode from the start rather than chmod-ing after:
    # otherwise the token is briefly world-readable between the two calls.
    fd = os.open(str(secrets_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, SECRETS_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=4, sort_keys=True)
        handle.write("\n")
    os.chmod(secrets_path, SECRETS_MODE)


def _tildify(path: Path) -> str:
    """``/Users/me/.drunken/x`` -> ``~/.drunken/x`` when it is under $HOME."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_env_to_registry.py",
        description=(
            "Move Jira credentials from .env into $DRUNKEN_HOME and register "
            "the project with a file:// reference to them."
        ),
    )
    parser.add_argument("--project", required=True, help="Project id to register.")
    parser.add_argument(
        "--path",
        help="Absolute path to the checkout. Defaults to the repo this lives in.",
    )
    parser.add_argument("--description", default="", help="Human-readable label.")
    parser.add_argument(
        "--env-file",
        default=str(Path(__file__).resolve().parent.parent / ".env"),
        help="Where to read credentials from. Default: the repo's .env",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be written without writing anything.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    validate_project_id(args.project)

    env_file = load_env_file(Path(args.env_file))
    required = {
        "url": value_of("JIRA_URL", env_file=env_file),
        "email": value_of("JIRA_EMAIL", env_file=env_file),
        "project_key": value_of("JIRA_PROJECT_KEY", env_file=env_file),
        "token": value_of("JIRA_TOKEN", "JIRA_API_TOKEN", env_file=env_file),
    }
    missing = sorted(name for name, found in required.items() if not found)
    if missing:
        print(f"error: no value found for {', '.join(missing)}")
        print(f"  -> Looked in the environment, then {args.env_file}.")
        return 1

    home = paths.home().path
    secrets_path = home / "secrets.json"
    # Written with ``~`` where possible: the resolver expands it, and the
    # registry then carries no username, so it can be copied to another
    # machine or another account without editing.
    reference = f"file://{_tildify(secrets_path)}#jira.{args.project}"
    checkout = args.path or str(Path(__file__).resolve().parent.parent)

    channel = value_of("DISCORD_CHANNEL_ID", env_file=env_file)

    if args.dry_run:
        print(f"state directory : {home}")
        print(f"secrets file    : {secrets_path}  (mode {oct(SECRETS_MODE)[2:]})")
        print(f"would store     : jira.{args.project}  (value not shown)")
        print(f"registry ref    : {reference}")
        print(f"jira url        : {required['url']}")
        print(f"jira email      : {required['email']}")
        print(f"project key     : {required['project_key']}")
        print(f"discord channel : {channel or '(none found)'}")
        print("\nDry run: nothing written.")
        return 0

    paths.ensure_home()
    merge_secrets(secrets_path, {"jira": {args.project: str(required["token"])}})
    print(f"secrets         : {secrets_path}  (mode {oct(SECRETS_MODE)[2:]})")

    command = [
        "drunken-init",
        "--project",
        args.project,
        "--path",
        checkout,
        "--jira-url",
        str(required["url"]),
        "--jira-email",
        str(required["email"]),
        "--jira-project-key",
        str(required["project_key"]),
        "--jira-credential",
        reference,
    ]
    if args.description:
        command += ["--description", args.description]
    if channel:
        command += ["--discord-channel", channel]

    # The token is not in this argv -- only the reference to it is. That is the
    # whole point, and it is also why this is safe to see in a process list.
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print("error: drunken-init failed; the secrets file was still written.")
        return completed.returncode

    print("\nNext: verify it actually resolves, which is a separate step:")
    print(f"  uv run drunken-doctor --project {args.project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
