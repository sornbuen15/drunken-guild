"""Generate the configuration that hosts, installers and deployments read.

DT-228. Every one of these files was hand-written at least once, and every
hand-written one drifted: TWA's ``.mcp.json`` was still passing ``--workspace``
two releases after the flag was deleted, and the installed tool environment
carries ``mcp`` 1.29.0 while ``uv.lock`` pins 1.28.1 because ``uv tool install``
does not read the lock. A generator does not prevent drift on its own -- it
makes the correct version cheap enough that nobody edits by hand instead.

**Vendor-neutral by construction.** What is emitted is plain stdio MCP, which
Claude Code, Antigravity, Cursor and anything else speaking the protocol all
consume. Boss's rule 1 says any AI must be able to use this, and the way to keep
that true is to emit one shape rather than one per tool.

**Two shapes, and the difference matters.** A repository's own ``.mcp.json`` is
committed and shared, so it names commands and never paths -- an absolute path
there is one machine's layout in everyone else's history. A *host* config lives
in the user's home, is never committed, and must name absolute paths: a GUI
application launched from ``/Applications`` inherits a minimal ``PATH`` that
does not include ``~/.local/bin``, so a bare name works when you test it in a
terminal and fails silently inside the IDE.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404 - uv, invoked with a fixed argument list
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The servers a project gets wired to.
#:
#: ``drunken-board-mcp`` is deliberately absent. DT-250 retired the local board
#: and DT-251 wrote down why: a board sitting next to Jira is a second surface
#: that can disagree with the first, which is the failure this project spent a
#: session curing. It still exists, marked unused rather than deleted, and it
#: costs 2,162 tokens per request for a server nothing should call. Onboarding
#: declared it into every project until DT-228; do not add it back.
MCP_SERVERS = ("drunken-jira-mcp", "drunken-discord-mcp")


def mcp_config(project_id: str) -> Dict[str, Any]:
    """The config a repository commits. Names, never paths -- see the module doc."""
    return {
        "mcpServers": {
            name: {"command": name, "args": ["--project", project_id]}
            for name in MCP_SERVERS
        }
    }


def _tool_bin_dir() -> Path:
    """Where ``uv tool install`` puts executables. The stable location."""
    override = os.environ.get("UV_TOOL_BIN_DIR")
    return Path(override).expanduser() if override else Path.home() / ".local" / "bin"


def resolve_command(name: str) -> str:
    """Absolute path to *name*, for a config a GUI application will read.

    Falls back to whatever is on ``PATH``, and says so when that is a
    development virtualenv: writing one into a host config produces something
    that works until the venv is rebuilt and then fails with no obvious
    connection to the cause.
    """
    installed = _tool_bin_dir() / name
    if installed.is_file():
        return str(installed)

    found = shutil.which(name)
    if found and ".venv" not in Path(found).parts:
        return found

    if found:
        print(
            f"warning: {name} resolved to {found}, inside a development "
            "virtualenv. Run `uv tool install .` so the host points at a "
            "stable location instead.",
            file=sys.stderr,
        )
        return found

    print(
        f"warning: {name} is not installed, so the config will name it bare "
        "and the host will fail to start it. Run `uv tool install .` first.",
        file=sys.stderr,
    )
    return name


def host_config(project_id: str) -> Dict[str, Any]:
    """The config a host application reads, with commands resolved to paths."""
    return {
        "mcpServers": {
            name: {"command": resolve_command(name), "args": ["--project", project_id]}
            for name in MCP_SERVERS
        }
    }


def merge_into_host_config(path: Path, project_id: str) -> List[str]:
    """Add our servers to an existing host config, leaving its own alone.

    Antigravity's ``mcp_config.json`` declares servers of its own. Overwriting
    the file to add ours would take those with it, so entries are merged by name
    and anything unrecognised is left untouched. Returns the names that changed,
    so running it twice reports nothing the second time.
    """
    document: Dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                document = loaded
        except json.JSONDecodeError:
            raise SystemExit(
                f"error: {path} is not valid JSON. Refusing to rewrite it."
            ) from None

    servers = document.setdefault("mcpServers", {})
    changed = []
    for name, entry in host_config(project_id)["mcpServers"].items():
        if servers.get(name) != entry:
            servers[name] = entry
            changed.append(name)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return changed


def export_requirements(project_root: Path) -> Optional[str]:
    """``uv.lock`` as a pinned requirements file, or ``None`` if uv cannot.

    This is the missing half of the deployment story. ``uv tool install .``
    ignores ``uv.lock`` entirely and resolves afresh inside the declared
    ranges, which is how the installed environment came to hold ``mcp`` 1.29.0
    against a lock pinning 1.28.1 -- both satisfy ``<2`` and nothing reported
    the difference until ``drunken-doctor`` grew a check for it (DT-252).

    Returns ``None`` rather than raising: an environment without ``uv`` can
    still generate its MCP configs, and the caller says what was skipped.
    """
    try:
        result = subprocess.run(  # nosec B603 - fixed argv, no shell
            [
                "uv",
                "export",
                "--format",
                "requirements-txt",
                "--no-emit-project",
                "--no-dev",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def count_pins(exported: str) -> int:
    """Packages in an exported requirements file, not lines.

    The export carries a hash block per package, so a 43-package export is
    1,337 lines. Reporting the line count would overstate it by thirty times --
    a number nobody would check and everybody would quote.
    """
    return sum(1 for line in exported.splitlines() if "==" in line)


def install_command(requirements: Optional[Path]) -> str:
    """The install line that honours the lock, or the one that admits it cannot."""
    if requirements is None:
        return (
            "uv tool install .    # NOTE: ignores uv.lock; versions may drift "
            "inside the declared ranges"
        )
    return f"uv tool install . --with-requirements {requirements}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drunken-config",
        description=(
            "Generate the configuration hosts and installers read, instead of "
            "hand-writing it."
        ),
    )
    parser.add_argument("--project", required=True, help="Project id to scope to.")
    parser.add_argument(
        "--kind",
        choices=("mcp", "host", "install"),
        default="mcp",
        help=(
            "mcp: a repository's own .mcp.json, names only. "
            "host: a host application's config, absolute paths. "
            "install: the pinned install command, with requirements exported "
            "from uv.lock."
        ),
    )
    parser.add_argument(
        "--out",
        help=(
            "Write here instead of printing. For --kind host the file is "
            "merged, so the host's own servers survive."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from core.registry import validate_project_id

    validate_project_id(args.project)

    if args.kind == "install":
        return _emit_install(args.out)

    if args.kind == "host":
        if not args.out:
            print(json.dumps(host_config(args.project), indent=2))
            return 0
        changed = merge_into_host_config(Path(args.out).expanduser(), args.project)
        print(
            f"{args.out}: {', '.join(changed)} written"
            if changed
            else f"{args.out}: already correct, nothing changed"
        )
        return 0

    document = json.dumps(mcp_config(args.project), indent=2)
    if not args.out:
        print(document)
        return 0
    Path(args.out).expanduser().write_text(document + "\n", encoding="utf-8")
    print(f"{args.out}: written")
    return 0


def _emit_install(out: Optional[str]) -> int:
    """Print the install command, writing the pinned requirements beside it.

    Printed rather than run. Installing is the operator's call -- it replaces
    the deployment that a host config is already pointing at, and doing that as
    a side effect of asking for a config would be the kind of surprise this
    project keeps writing post-mortems about.
    """
    root = Path.cwd()
    exported = export_requirements(root)
    if exported is None:
        print(
            "warning: could not export uv.lock (is `uv` on PATH, and is this a "
            "project root?). Falling back to an unpinned install.",
            file=sys.stderr,
        )
        print(install_command(None))
        return 0

    target = Path(out).expanduser() if out else root / "requirements.lock.txt"
    target.write_text(exported, encoding="utf-8")
    # Say what was and was not done, in that order. The first version printed
    # the filename and the command with no verb between them, which reads as a
    # report of work completed -- and was taken as one, leaving a deployment
    # three tickets behind while every surface looked fine.
    print(f"Wrote {target} ({count_pins(exported)} pinned packages).")
    print("NOT INSTALLED. To deploy, run:\n")
    print(f"    {install_command(target)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
