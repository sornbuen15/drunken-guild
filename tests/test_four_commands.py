# mypy: ignore-errors
"""What this package puts on an operator's PATH — DG-356.

Ten console scripts shipped once. Five went with the Discord machinery
(DG-355); two more answer questions nothing asks any more: `drunken-status`
re-derives what `/audit` reports, and `drunken-config` generated an MCP
configuration that is now identical for every project and therefore a constant.

A list in a test rather than a count, because the failure this catches is not
"too many" — it is **a command shipping whose reason has gone**, which is
invisible until somebody runs it. `drunken-board-mcp` sat on every installer's
PATH for three releases that way, and `verify_clean_install.sh` started it by
name to prove it answered a handshake.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPT_LINE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)\s*=\s*\"(?P<target>[^\"]+)\"")

#: The four an operator types.
OPERATOR_COMMANDS = {
    "drunken-doctor",
    "drunken-init",
    "drunken-usage",
}

#: Not typed by anyone: one is a server a host launches, one is a hook
#: `.claude/settings.json` calls. They ship as entry points because that is how
#: a host finds them, which is a different thing from being a command.
PLUMBING = {
    "drunken-jira-mcp",
    "drunken-hook",
}

EXPECTED = OPERATOR_COMMANDS | PLUMBING


def declared_scripts() -> dict[str, str]:
    """Every console script pyproject declares, as `name -> target`.

    Read with a regex rather than `tomllib`: the declared floor is Python 3.10,
    where `tomllib` does not exist, and a guard is not worth a new dependency.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.partition("[project.scripts]")[2].partition("\n[")[0]
    return {
        match.group("name"): match.group("target")
        for line in block.splitlines()
        if (match := SCRIPT_LINE.match(line.strip()))
    }


def test_exactly_these_commands_ship() -> None:
    declared = set(declared_scripts())

    assert declared == EXPECTED, (
        f"unexpected: {sorted(declared - EXPECTED)}; "
        f"missing: {sorted(EXPECTED - declared)}. "
        "Adding a command means adding it here with a reason — the point is "
        "that every name on an operator's PATH still has one."
    )


def test_every_declared_target_is_importable() -> None:
    """A console script naming a module that moved is a command that exists
    until it is run, and then reports an ImportError the operator cannot act
    on."""
    import importlib

    for name, target in sorted(declared_scripts().items()):
        module_name, _, attribute = target.partition(":")
        module = importlib.import_module(module_name)
        assert hasattr(module, attribute), (
            f"{name} points at {target}, which does not exist any more."
        )
