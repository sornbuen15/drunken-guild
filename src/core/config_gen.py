"""Generate the configuration that hosts, installers and deployments read.

DG-228. Every one of these files was hand-written at least once, and every
hand-written one drifted: ALPHA's ``.mcp.json`` was still passing ``--workspace``
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

import json
import os
import shutil
import subprocess  # nosec B404 - uv, invoked with a fixed argument list
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

#: The servers a project gets wired to.
#:
#: ``drunken-board-mcp`` is deliberately absent. DG-250 retired the local board
#: and DG-251 wrote down why: a board sitting next to Jira is a second surface
#: that can disagree with the first, which is the failure this project spent a
#: session curing. It cost 2,162 tokens per request for a server nothing should
#: call, and onboarding declared it into every project until DG-228.
#:
#: DG-265 finished the job: it is no longer packaged at all, so there is no
#: command to declare even by accident. The code is kept at
#: ``_not_used/board-mcp/`` because an agent does not delete. Do not add it back.
#: ``drunken-discord-mcp`` left the same way (DG-355): Discord is one-way
#: notification now, sent from hooks and CI, so there is no tool for an agent
#: to call and no server to declare. ``is_drunken_managed`` still matches the
#: name, which is what prunes it from a host config on the next regeneration.
MCP_SERVERS = ("drunken-jira-mcp",)


def is_drunken_managed(name: str) -> bool:
    """True for any server this project has ever shipped, current or retired.

    DG-286: a host config that merges but never prunes is why DG-277 found
    ``drunken-board-mcp`` still declared in Antigravity's config three
    releases after DG-265 retired it, and had to delete it by hand. This
    decides ownership by naming convention rather than a list that would
    need to be remembered and kept current -- every server ``MCP_SERVERS``
    has ever named follows ``drunken-<name>-mcp``, and nothing outside this
    project would collide with that prefix by accident. Antigravity's own
    extras (``kanban-board``, a third-party ``jira-board``) do not match it,
    which is what keeps them out of reach of the pruning below.
    """
    return name.startswith("drunken-") and name.endswith("-mcp")


def mcp_config(project_id: str = "") -> Dict[str, Any]:
    """The config a repository commits. Names, never paths -- see the module doc.

    **It carries no project, and that is the point (DG-341).** `--project` used
    to be written in here, which made this file the thing that decided which
    Jira a server talked to — and an entry registered at *user* scope then
    decided it for every session on the machine. One pinned config served
    sessions that were not that project, handing them its board while reporting
    success.

    Every tool takes the project as an argument now, so this config is identical
    for every project and there is nothing left to pin. *project_id* is accepted
    and ignored: callers pass one, and refusing it would break them to remove a
    value nothing reads.
    """
    return {"mcpServers": {name: {"command": name} for name in MCP_SERVERS}}


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


def host_config(project_id: str = "") -> Dict[str, Any]:
    """The config a host application reads, with commands resolved to paths.

    No project here either, and this is the shape where it mattered most: a host
    config lives in the user's home and reaches every session it opens. See
    :func:`mcp_config`.
    """
    return {
        "mcpServers": {name: {"command": resolve_command(name)} for name in MCP_SERVERS}
    }


class HostConfigDiff(NamedTuple):
    """What a merge changed, added and removed kept apart on purpose.

    A single flat list would leave a caller guessing which names in it were
    new and which had just vanished -- printing it as "added/updated" would
    misreport a deletion as work done, which is exactly the kind of quiet
    misstatement this project keeps writing post-mortems about.
    """

    added: List[str]
    removed: List[str]

    def __bool__(self) -> bool:
        return bool(self.added or self.removed)


def merge_into_host_config(path: Path, project_id: str) -> HostConfigDiff:
    """Add our servers to an existing host config, leaving its own alone.

    Antigravity's ``mcp_config.json`` declares servers of its own. Overwriting
    the file to add ours would take those with it, so entries are merged by
    name and anything this generator did not author is left untouched.

    "Did not author" is ``is_drunken_managed`` -- a naming convention, not a
    list. That is what lets a server this project retires (``drunken-board-mcp``,
    DG-265) disappear on the next regeneration instead of needing another
    round of DG-277's hand deletion, while a foreign entry that happens to
    share no prefix with us, like ``kanban-board``, is never touched.
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
    current = host_config(project_id)["mcpServers"]

    removed = [
        name
        for name in list(servers)
        if is_drunken_managed(name) and name not in current
    ]
    for name in removed:
        del servers[name]

    added = []
    for name, entry in current.items():
        if servers.get(name) != entry:
            servers[name] = entry
            added.append(name)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return HostConfigDiff(added=added, removed=removed)


def export_requirements(project_root: Path) -> Optional[str]:
    """``uv.lock`` as a pinned requirements file, or ``None`` if uv cannot.

    This is the missing half of the deployment story. ``uv tool install .``
    ignores ``uv.lock`` entirely and resolves afresh inside the declared
    ranges, which is how the installed environment came to hold ``mcp`` 1.29.0
    against a lock pinning 1.28.1 -- both satisfy ``<2`` and nothing reported
    the difference until ``drunken-doctor`` grew a check for it (DG-252).

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


# The CLI that used to live here is retired (DG-356). `drunken-config` had
# three jobs and lost one of them outright: `--kind mcp` emitted a document that
# is now a constant, because the project moved into every tool call (DG-341).
# The other two moved to where they belong rather than being dropped:
#
# * `--kind host` -- merging into a host application's own config file, pruning
#   the servers this project has retired -- is reached through
#   `scripts/onboard_project.py --merge-mcp-config`, which already called these
#   functions directly rather than shelling out to the command.
# * `--kind install` -- the pinned install line, the remedy for `uv tool
#   install` ignoring `uv.lock` -- is now `drunken-doctor --requirements`, which
#   puts it in the tool that reports the drift instead of in a second command
#   that warning had to name.
#
# What stays here is the library the two of them use. Everything below this line
# is called from Python; nothing in this module is a command any more.
