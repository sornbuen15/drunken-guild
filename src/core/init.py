"""``drunken-init`` — create the state directory and register a project.

Setting up used to mean running ``drunken-register``, answering six interactive
prompts, and ending up with the Jira token and the Discord bot token written in
plaintext into ``<project>/.agents/`` — inside the repository. It also never
wrote the central registry that the servers actually read, so following the
on-screen instructions could not produce a working install.

This is the replacement, and the constraints follow directly from the four rules
this redesign is built on:

* **Non-interactive.** A setup step that blocks on ``input()`` cannot run in a
  Dockerfile, a CI job, or a provisioning script. Everything is a flag.
* **Never accepts a secret.** ``--jira-credential`` takes a *reference*, and the
  reference is validated before anything is written. There is no flag that
  accepts a token, so a token cannot end up in the file — or in shell history.
* **Idempotent.** Re-running updates in place and leaves unrelated fields alone,
  so it is safe to put in a provisioning script that runs more than once.

``drunken-register`` was kept alongside this for one release, because it also
provisioned Antigravity's dashboard entry. It is gone as of 2.2.0 (S11) and is
no longer declared in ``[project.scripts]``, so anything still naming it — an
error's remediation, a README step — is quoting a command that exits 127.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional

from . import paths, secrets
from .errors import DrunkenError, ValidationError
from .registry import SCHEMA_VERSION, validate_project_id


def _validate_credential_reference(reference: str) -> None:
    """Refuse anything that is not a resolvable reference.

    Checked here as well as at resolution time so the mistake is caught while
    the operator is still looking at the terminal, rather than surfacing much
    later as a confusing failure inside a server.
    """
    secrets.parse_ref(reference)


def _build_jira_block(args: argparse.Namespace) -> Optional[dict[str, str]]:
    supplied = {
        "url": args.jira_url,
        "email": args.jira_email,
        "project_key": args.jira_project_key,
        "credential": args.jira_credential,
    }
    if not any(supplied.values()):
        return None

    missing = [name for name, value in supplied.items() if not value]
    if missing:
        raise ValidationError(
            f"Incomplete Jira options: missing --jira-{'/--jira-'.join(m.replace('_', '-') for m in missing)}.",
            remediation="Provide all four Jira options together, or none of them.",
        )

    _validate_credential_reference(supplied["credential"])
    return {key: str(value) for key, value in supplied.items()}


def _ensure_registry_document(registry_file: str) -> dict[str, Any]:
    if not os.path.exists(registry_file):
        return {"version": SCHEMA_VERSION, "projects": {}}

    with open(registry_file, "r", encoding="utf-8") as handle:
        document = json.load(handle)

    if not isinstance(document, dict):
        raise ValidationError(
            f"{registry_file} is not a JSON object.",
            remediation="Fix or remove the file, then run drunken-init again.",
        )

    if "projects" in document and isinstance(document["projects"], dict):
        return document

    # A v1 file: the document *is* the project map. Wrapping it is a real
    # migration, so it happens only here, where the operator asked for it.
    return {"version": SCHEMA_VERSION, "projects": document}


def _apply_project(document: dict[str, Any], args: argparse.Namespace) -> str:
    project_id = validate_project_id(args.project)
    entry: dict[str, Any] = dict(document["projects"].get(project_id, {}))

    if args.path:
        path = os.path.abspath(os.path.expanduser(args.path))
        if not os.path.isdir(path):
            raise ValidationError(
                f"Path does not exist: {path}",
                remediation=(
                    "Point --path at an existing directory. Omit it entirely for a "
                    "project that only talks to Jira or Discord — a containerised "
                    "server has no host checkout."
                ),
            )
        entry["path"] = path

    if args.git_root:
        entry["git_root"] = args.git_root
    if args.description:
        entry["description"] = args.description

    jira = _build_jira_block(args)
    if jira:
        entry["jira"] = jira
    if args.discord_webhook:
        # Validated the same way as the Jira credential: a webhook URL pasted
        # here instead of a reference would be written straight into a file
        # meant to be readable and shareable — and anyone holding that URL can
        # post as the bot.
        _validate_credential_reference(args.discord_webhook)
        entry["discord"] = {"webhook": str(args.discord_webhook)}
    if args.board_dir:
        entry["board"] = {"dir": args.board_dir}

    document["projects"][project_id] = entry
    return project_id


def _write(registry_file: str, document: dict[str, Any]) -> None:
    directory = os.path.dirname(registry_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(registry_file, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=4)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drunken-init",
        description=(
            "Create the drunken-guild state directory and register a project. "
            "Non-interactive and idempotent, so it can run in a Dockerfile or a "
            "provisioning script."
        ),
        epilog=(
            "Credentials are referenced, never stored: --jira-credential takes "
            "env://VAR, file://path#key.path, op://vault/item/field or "
            "keyring://service/user. There is deliberately no flag that accepts "
            "a token."
        ),
    )
    parser.add_argument("--project", help="Project id to add or update.")
    parser.add_argument("--path", help="Absolute path to the checkout (optional).")
    parser.add_argument(
        "--git-root", help="Subdirectory holding the git repo, if not the root."
    )
    parser.add_argument("--description", help="Human-readable description.")
    parser.add_argument("--jira-url", help="e.g. https://your-domain.atlassian.net")
    parser.add_argument("--jira-email", help="Account the credential belongs to.")
    parser.add_argument("--jira-project-key", help="e.g. ALPHA")
    parser.add_argument(
        "--jira-credential",
        help="Secret REFERENCE, not a token. e.g. env://JIRA_TOKEN_ALPHA",
    )
    parser.add_argument(
        "--discord-webhook",
        help=(
            "Secret REFERENCE to a Discord webhook URL, not the URL itself. "
            "Notifications are one-way and optional."
        ),
    )
    parser.add_argument("--board-dir", help="Board directory relative to the checkout.")
    parser.add_argument(
        "--registry", help="Registry file to write instead of the resolved default."
    )
    return parser


def main() -> int:
    """Entry point for ``drunken-init``."""
    args = build_parser().parse_args()

    try:
        home = paths.ensure_home()
        registry_file = args.registry or str(paths.registry_path())

        document = _ensure_registry_document(registry_file)
        project_id = _apply_project(document, args) if args.project else None
        _write(registry_file, document)
    except DrunkenError as exc:
        print(f"error: {exc}")
        if exc.remediation:
            print(f"  -> {exc.remediation}")
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1

    print(f"state directory : {home}  (mode {oct(paths.HOME_MODE)[2:]})")
    print(f"registry        : {registry_file}  (schema v{document['version']})")
    if project_id:
        print(f"registered      : {project_id}")
    print(
        f"projects        : {', '.join(sorted(document['projects'])) or '(none yet)'}"
    )
    print()
    print("Next: drunken-doctor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
