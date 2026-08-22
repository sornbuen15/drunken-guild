# mypy: ignore-errors
"""`.mcp.json` is how this repo's own agents reach the MCP servers, so a server
that ships without an entry there is code nobody can call.

That is not hypothetical: `board_available_tasks` and the `blocked` lane merged
in DT-233 and stayed unreachable from inside this project, because `.mcp.json`
declared two of the three servers. Nothing failed -- the tools simply were not
there. This test is the thing that would have said so.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Console-script lines in pyproject's `[project.scripts]` table.
SCRIPT_LINE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)\s*=\s*\"(?P<target>[^\"]+)\"")


def _declared_servers() -> dict[str, str]:
    """The `drunken-*-mcp` entry points, as pyproject declares them.

    Read with a regex rather than `tomllib` on purpose: the declared floor is
    Python 3.10, where `tomllib` does not exist, and a drift guard is not worth
    a new dependency.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.partition("[project.scripts]")[2].partition("\n[")[0]

    servers = {}
    for line in block.splitlines():
        match = SCRIPT_LINE.match(line.strip())
        if match and match.group("name").endswith("-mcp"):
            servers[match.group("name")] = match.group("target")
    return servers


@pytest.fixture()  # type: ignore[misc]
def mcp_config() -> dict:
    return json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))


def test_pyproject_still_declares_mcp_servers() -> None:
    """Guards the guard: if the entry points are ever renamed, the check below
    would pass by finding nothing to check."""
    assert _declared_servers(), (
        "No 'drunken-*-mcp' console scripts found in [project.scripts]. "
        "Either they were renamed, or this test is parsing the wrong block."
    )


#: Servers that must not come back — not as an entry point, and not in
#: `.mcp.json`.
#:
#: This set used to mean something weaker: *ships, but is deliberately not
#: wired anywhere*. That was the state DG-265 ended. A package that has never
#: been released has no compatibility to protect, so shipping a dead server
#: from day one was a choice rather than an inheritance, and the choice was to
#: stop.
#:
#: Both directions are guarded below, because the two failures look nothing
#: alike. Re-declaring the entry point puts a runnable command on the PATH of
#: everyone who installs this. Re-adding it to `.mcp.json` hands its tools back
#: to every agent in this repo.
RETIRED_SERVERS = {
    # DG-250. Jira is the only coordination surface: the assignee says whose
    # work a ticket is, the status says where it is. A local board beside Jira
    # is a second surface that can disagree with the first. The code is kept at
    # _not_used/board-mcp/ rather than deleted — an agent does not delete — but
    # it is no longer packaged, so nothing installs or runs it.
    "drunken-board-mcp",
}


def test_every_mcp_server_is_reachable_from_this_project(mcp_config: dict) -> None:
    """A server that exists but is not declared here cannot be called at all."""
    declared = set(_declared_servers())
    configured = set(mcp_config["mcpServers"])

    assert declared <= configured, (
        f"{sorted(declared - configured)} ship as entry points but are missing "
        "from .mcp.json, so their tools cannot be called from inside this "
        "project. This is how DT-233's board tools shipped unreachable."
    )


def test_a_retired_server_is_not_packaged_again() -> None:
    """The invariant DG-265 created, and the one nothing else would catch.

    While `drunken-board-mcp` was still an entry point, `pip install` put a
    runnable command on the PATH of everyone who installed this, for a server
    whose every tool had been retired. `verify_clean_install.sh` even started it
    by name to prove it answered a handshake. Re-adding the line would restore
    all of that silently — the suite would stay green, because a shipped server
    breaks nothing until somebody runs it.
    """
    declared_again = RETIRED_SERVERS & set(_declared_servers())
    assert not declared_again, (
        f"{sorted(declared_again)} is retired (DG-250) and has been declared "
        "again in [project.scripts], so `pip install` will put it on PATH. "
        "The code lives at _not_used/board-mcp/ and is not packaged. If this "
        "is deliberate, change RETIRED_SERVERS and say why."
    )


def test_a_retired_server_is_not_quietly_wired_back_in(mcp_config: dict) -> None:
    """The mirror of the test above, and the one that matters now.

    Retiring the board was a decision, not an accident, so it needs a guard in
    the same direction: adding it back to `.mcp.json` should fail here and be
    argued for, rather than reappearing because a config was copied from an
    older project.
    """
    wired_again = RETIRED_SERVERS & set(mcp_config["mcpServers"])
    assert not wired_again, (
        f"{sorted(wired_again)} is retired (DG-250) and has been wired back "
        "into .mcp.json. Jira is the only coordination surface — if this is "
        "deliberate, change RETIRED_SERVERS and say why."
    )


def test_no_configured_server_points_at_a_module_that_is_gone(
    mcp_config: dict,
) -> None:
    """The other direction: an entry left behind after a server is removed
    fails at handshake time, where the host reports a process that vanished."""
    for name, entry in mcp_config["mcpServers"].items():
        args = entry.get("args", [])
        assert "-m" in args, (
            f"{name} is not launched with 'python -m'; this check does not "
            "know how to resolve its module and needs updating."
        )
        module = args[args.index("-m") + 1]
        package = module.partition(".")[0]
        assert (REPO_ROOT / "src" / package).is_dir(), (
            f".mcp.json launches {name} from '{module}', but src/{package} "
            "does not exist."
        )


def test_no_absolute_paths_leak_into_mcp_config(mcp_config: dict) -> None:
    """Working agreement: an absolute path in a committed `.mcp.json` is one
    developer's machine, checked into everyone else's."""
    raw = (REPO_ROOT / ".mcp.json").read_text(encoding="utf-8")
    assert "/Users/" not in raw and "/home/" not in raw, (
        ".mcp.json contains an absolute home path. Paths here must be "
        "relative to the project, or the file only works on one machine."
    )
