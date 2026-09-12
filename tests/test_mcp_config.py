# mypy: ignore-errors
"""A server that ships as a console script but is not wired into any project's
MCP config is code nobody can call.

That is not hypothetical: `board_available_tasks` and the `blocked` lane merged
in DG-233 and stayed unreachable from inside this project, because the config
declared two of the three servers. Nothing failed -- the tools simply were not
there. This file is the thing that would have said so.

**What it reads changed in DG-313, and the change is the finding.** These tests
used to open this repository's own `.mcp.json` from the repo root. That file is
operating config, not source -- machine paths and which project each server
serves -- so DG-313 untracked it. The tests then failed on a CI runner that had
never checked it out, and passed locally only because the file happened to
still be on disk. They were asserting against one machine's copy of a generated
artefact.

So they assert against the generator instead: `core.config_gen.mcp_config()` is
what writes every project's `.mcp.json`, this repo's included. That is both
honest and stronger -- a server missing from the generator is unreachable from
*every* project it onboards, not just from whichever one a developer happened
to run the suite in.

`test_config_gen.py` owns the invariants internal to the generator -- that the
repo shape names commands and never paths, that both shapes are scoped to a
project, that the board server is emitted by neither. This file owns the one
thing that spans two files and neither of them can see alone: **what
`pyproject.toml` ships and what the generator wires must be the same set.**
"""

import re
from pathlib import Path

import pytest

from core import config_gen

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Console-script lines in pyproject's `[project.scripts]` table.
SCRIPT_LINE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)\s*=\s*\"(?P<target>[^\"]+)\"")

#: Any project id will do -- the generator emits the same server set for all of
#: them, and the id only reaches the `--project` argument. Naming a real one
#: would suggest this repository is the subject, which is the assumption
#: DG-313 removed.
SOME_PROJECT = "any-project"


def _declared_scripts() -> dict[str, str]:
    """Every console script pyproject declares, as `name -> target`.

    Read with a regex rather than `tomllib` on purpose: the declared floor is
    Python 3.10, where `tomllib` does not exist, and a drift guard is not worth
    a new dependency.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.partition("[project.scripts]")[2].partition("\n[")[0]

    scripts = {}
    for line in block.splitlines():
        match = SCRIPT_LINE.match(line.strip())
        if match:
            scripts[match.group("name")] = match.group("target")
    return scripts


def _declared_servers() -> dict[str, str]:
    """The `drunken-*-mcp` entry points, as pyproject declares them."""
    return {
        name: target
        for name, target in _declared_scripts().items()
        if name.endswith("-mcp")
    }


@pytest.fixture()  # type: ignore[misc]
def wired_servers() -> dict:
    """The `mcpServers` block the generator writes into a project."""
    return config_gen.mcp_config(SOME_PROJECT)["mcpServers"]


def test_pyproject_still_declares_mcp_servers() -> None:
    """Guards the guard: if the entry points are ever renamed, the check below
    would pass by finding nothing to check."""
    assert _declared_servers(), (
        "No 'drunken-*-mcp' console scripts found in [project.scripts]. "
        "Either they were renamed, or this test is parsing the wrong block."
    )


#: Servers that must not come back -- not as an entry point, and not in a
#: generated config.
#:
#: This set used to mean something weaker: *ships, but is deliberately not
#: wired anywhere*. That was the state DG-265 ended. A package that has never
#: been released has no compatibility to protect, so shipping a dead server
#: from day one was a choice rather than an inheritance, and the choice was to
#: stop.
#:
#: Both directions are guarded below, because the two failures look nothing
#: alike. Re-declaring the entry point puts a runnable command on the PATH of
#: everyone who installs this. Re-adding it to the generator hands its tools
#: back to every project this onboards.
RETIRED_SERVERS = {
    # DG-250. Jira is the only coordination surface: the assignee says whose
    # work a ticket is, the status says where it is. A local board beside Jira
    # is a second surface that can disagree with the first. The code is kept at
    # _not_used/board-mcp/ rather than deleted — an agent does not delete — but
    # it is no longer packaged, so nothing installs or runs it.
    "drunken-board-mcp",
    # DG-355. Discord is one-way notification now, sent from hooks and CI, so
    # there is no tool for an agent to call. Re-declaring the entry point would
    # put a server on everyone's PATH whose every tool asked a question nothing
    # can answer.
    "drunken-discord-mcp",
}


def test_every_mcp_server_is_reachable_from_a_project(wired_servers: dict) -> None:
    """A server that ships but is not wired cannot be called at all."""
    declared = set(_declared_servers())
    wired = set(wired_servers)

    assert declared <= wired, (
        f"{sorted(declared - wired)} ship as entry points but are missing from "
        "config_gen.MCP_SERVERS, so no project this onboards can call their "
        "tools. This is how DG-233's board tools shipped unreachable."
    )


def test_nothing_is_wired_that_does_not_ship(wired_servers: dict) -> None:
    """The mirror, and the failure that only appears at somebody else's install.

    A name in the generator with no console script behind it writes a config
    whose command does not exist. The host reports a process that would not
    start, which reads like a broken install rather than a typo here.
    """
    unshipped = set(wired_servers) - set(_declared_servers())
    assert not unshipped, (
        f"{sorted(unshipped)} is wired by config_gen but is not declared in "
        "[project.scripts], so the generated config names a command that is "
        "not installed."
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


def test_a_retired_server_is_not_quietly_wired_back_in(wired_servers: dict) -> None:
    """The mirror of the test above, by name rather than by substring.

    `test_config_gen.py` already asserts that no *emitted* config contains the
    string "board". This one is crossed with the entry points, so it keeps
    holding if the board server ever comes back under a name that does not
    contain the word.
    """
    wired_again = RETIRED_SERVERS & set(wired_servers)
    assert not wired_again, (
        f"{sorted(wired_again)} is retired (DG-250) and has been wired back "
        "into config_gen. Jira is the only coordination surface — if this is "
        "deliberate, change RETIRED_SERVERS and say why."
    )


def test_no_wired_server_points_at_a_module_that_is_gone(wired_servers: dict) -> None:
    """The other direction: a config entry left behind after a server is removed
    fails at handshake time, where the host reports a process that vanished.

    The generated config names a command rather than `python -m module`, so the
    module is reached through pyproject's target for that command. That is one
    hop longer than the old check and covers the same ground plus the hop
    itself -- a script whose target package was moved out of `src/` now fails
    here rather than at somebody's first tool call.
    """
    scripts = _declared_scripts()

    for name, entry in wired_servers.items():
        command = entry["command"]
        assert command in scripts, (
            f"{name} is wired with command '{command}', which is not a console "
            "script in [project.scripts]. Nothing will install it."
        )

        module = scripts[command].partition(":")[0]
        package = module.partition(".")[0]
        assert (REPO_ROOT / "src" / package).is_dir(), (
            f"{name} runs '{scripts[command]}', but src/{package} does not exist."
        )
