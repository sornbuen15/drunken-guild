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


def test_every_mcp_server_is_reachable_from_this_project(mcp_config: dict) -> None:
    """A server that exists but is not declared here cannot be called at all."""
    declared = set(_declared_servers())
    configured = set(mcp_config["mcpServers"])

    assert declared <= configured, (
        f"{sorted(declared - configured)} ship as entry points but are missing "
        "from .mcp.json, so their tools cannot be called from inside this "
        "project. This is how DT-233's board tools shipped unreachable."
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
