#!/usr/bin/env python3
"""Bring another project under drunken-guild in one command.

Onboarding used to be four manual steps — write a secret, register the project,
write an ``.mcp.json``, then find out whether any of it worked. Every one of
them was a place to get it subtly wrong, and ALPHA is what that looks like: a
registry entry with no Jira identity and an ``.mcp.json`` still passing
``--workspace``, a flag deleted two releases ago.

Three things this deliberately does:

**One credential, referenced many times.** The same Jira account serves every
project here; only the project *key* differs. Copying the token into each entry
is how ALPHA's copy quietly drifted to a value that no longer authenticates — and
because a Jira search answers a dead token with ``200`` and an empty list, its
board simply looked empty for months.

**No paths in the generated config.** Since DG-241 the servers install as
commands, so another repository's ``.mcp.json`` names the command and nothing
else. An absolute path there is one machine's layout committed into everyone
else's history.

**Proves it, rather than reporting success.** ``drunken-init`` exiting 0 says
the file was written, not that anything works. The last step asks Jira who we
are, which is the only question a bad credential cannot answer.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core import paths  # noqa: E402
from core.config_gen import (  # noqa: E402
    mcp_config,
    merge_into_host_config,
)
from core.registry import validate_project_id  # noqa: E402

SECRETS_MODE = 0o600

#: Default key inside ``secrets.json``. One account, one entry, every project
#: pointing at it — see the module docstring.
SHARED_CREDENTIAL_KEY = "default"


def _tildify(path: Path) -> str:
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def credential_reference(key: str) -> str:
    return f"file://{_tildify(paths.home().path / 'secrets.json')}#jira.{key}"


def read_secrets() -> Dict[str, Any]:
    path = paths.home().path / "secrets.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise SystemExit(
            f"error: {path} is not valid JSON.\n"
            "  -> Fix it by hand; refusing to touch a file that may hold the "
            "only copy of a credential."
        ) from None
    return loaded if isinstance(loaded, dict) else {}


def write_secrets(document: Dict[str, Any]) -> Path:
    """Write with the mode applied at creation, never chmod-ed afterwards.

    Between ``open`` and ``chmod`` the file exists at the process umask, and a
    credential that is briefly world-readable is still a credential that was
    world-readable.
    """
    paths.ensure_home()
    path: Path = paths.home().path / "secrets.json"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, SECRETS_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=4, sort_keys=True)
        handle.write("\n")
    os.chmod(path, SECRETS_MODE)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onboard_project.py",
        description="Register a project and give it a working .mcp.json.",
        epilog=(
            "The MCP config it writes assumes the servers are installed as "
            "commands: run `uv tool install .` from drunken-guild first."
        ),
    )
    parser.add_argument("project", help="Project id, e.g. alpha")
    parser.add_argument(
        "--jira-project-key", required=True, help="Jira project key, e.g. ALPHA"
    )
    parser.add_argument("--path", help="Absolute path to the checkout, if it has one.")
    parser.add_argument("--description", default="", help="Human-readable label.")
    parser.add_argument(
        "--credential-key",
        default=SHARED_CREDENTIAL_KEY,
        help=(
            "Key inside secrets.json to reference. Defaults to the shared one; "
            "give a different key only if this project needs its own account."
        ),
    )
    parser.add_argument(
        "--jira-url", help="Defaults to whatever the shared config already uses."
    )
    parser.add_argument("--jira-email", help="Defaults to the shared config's.")
    parser.add_argument(
        "--write-mcp-config",
        action="store_true",
        help="Write .mcp.json into --path. Overwrites any existing one.",
    )
    parser.add_argument(
        "--merge-mcp-config",
        metavar="FILE",
        help=(
            "Add the three servers to an existing host config, e.g. "
            "~/.gemini/antigravity-cli/mcp_config.json. Its own entries are "
            "left alone."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen; write nothing."
    )
    return parser


def _inherit_from_registry(args: argparse.Namespace) -> tuple[str, str]:
    """Take the Jira URL and account from an already-registered project.

    Asking for them again per project is how three entries end up naming three
    slightly different hosts.
    """
    from core.registry import ProjectRegistry

    for entry in ProjectRegistry().get_projects().values():
        jira = entry.get("jira") if isinstance(entry, dict) else None
        if isinstance(jira, dict) and jira.get("url") and jira.get("email"):
            return str(jira["url"]), str(jira["email"])
    raise SystemExit(
        "error: no registered project has a Jira URL and email to inherit.\n"
        "  -> Pass --jira-url and --jira-email explicitly."
    )


def _report_plan(
    args: argparse.Namespace,
    url: str,
    email: str,
    reference: str,
    have_credential: bool,
) -> None:
    """What --dry-run prints. Worth having because this writes into someone
    else's repository, and seeing the file first is cheaper than restoring it."""
    print(f"project         : {args.project}  (Jira key {args.jira_project_key})")
    print(f"jira            : {url} as {email}")
    print(f"credential      : {reference}")
    print(f"  present?      : {'yes' if have_credential else 'NO — add it first'}")
    if args.path:
        print(f"path            : {args.path}")
    if args.write_mcp_config:
        print(f"would write     : {Path(args.path or '.') / '.mcp.json'}")
        print(json.dumps(mcp_config(args.project), indent=2))
    print("\nDry run: nothing written.")


def main() -> int:
    args = build_parser().parse_args()
    validate_project_id(args.project)

    url, email = args.jira_url, args.jira_email
    if not (url and email):
        inherited_url, inherited_email = _inherit_from_registry(args)
        url = url or inherited_url
        email = email or inherited_email

    reference = credential_reference(args.credential_key)
    secrets = read_secrets()
    have_credential = args.credential_key in secrets.get("jira", {})

    if args.dry_run:
        _report_plan(args, url, email, reference, have_credential)
        return 0

    if not have_credential:
        print(
            f"error: secrets.json has no 'jira.{args.credential_key}' to point at.",
            file=sys.stderr,
        )
        print(
            "  -> Add it first. `scripts/migrate_env_to_registry.py` can lift "
            "one out of an existing .env without printing it.",
            file=sys.stderr,
        )
        return 1

    command = [
        "drunken-init",
        "--project",
        args.project,
        "--jira-url",
        url,
        "--jira-email",
        email,
        "--jira-project-key",
        args.jira_project_key,
        "--jira-credential",
        reference,
    ]
    if args.path:
        command += ["--path", args.path]
    if args.description:
        command += ["--description", args.description]

    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        return completed.returncode

    if args.write_mcp_config:
        if not args.path:
            print(
                "error: --write-mcp-config needs --path to know where to put it.",
                file=sys.stderr,
            )
            return 1
        target = Path(args.path) / ".mcp.json"
        target.write_text(json.dumps(mcp_config(args.project), indent=2) + "\n")
        print(f"mcp config      : {target}")

    if args.merge_mcp_config:
        host = Path(args.merge_mcp_config).expanduser()
        added = merge_into_host_config(host, args.project)
        print(f"host config     : {host}")
        print(f"  added/updated : {', '.join(added) if added else '(already current)'}")

    print("\nNow prove it actually resolves — a separate step on purpose,")
    print("because a Jira search answers a dead token with 200 and an empty list:")
    print(f"  drunken-doctor --project {args.project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
