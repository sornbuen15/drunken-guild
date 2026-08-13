# mypy: ignore-errors
"""There is one registry, and every server reads that one.

`board_mcp` was the last module still resolving its registry from its own
``__file__`` — the §1.3 bug `core.paths` exists to eliminate. It mattered here
for a second reason: while the Jira and Discord servers read
``$DRUNKEN_HOME/projects.json``, the board read ``<repo>/.agents/projects.json``,
so the two could disagree about which projects exist and neither would say so.
"""

import ast
from pathlib import Path

from board_mcp import server as board_server
from core import paths


def test_board_does_not_derive_its_registry_from_dunder_file() -> None:
    """Installed with ``uv tool install``, ``__file__`` resolves inside the
    virtualenv rather than a checkout, and the board silently reads nothing."""
    tree = ast.parse(Path(board_server.__file__).read_text(encoding="utf-8"))
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "__file__" not in referenced


def test_board_reads_the_same_registry_as_everything_else(monkeypatch) -> None:
    """Two registries that disagree is the failure this prevents: the board
    offering a project the Jira server has never heard of, or the reverse."""
    monkeypatch.setenv(paths.ENV_REGISTRY, "/tmp/probe-registry.json")

    assert board_server.registry_path() == str(paths.registry_path())


def test_the_registry_override_is_honoured(monkeypatch, tmp_path) -> None:
    """A container points DRUNKEN_REGISTRY_PATH at a mounted file; resolving it
    once at import time would ignore that."""
    target = tmp_path / "elsewhere.json"
    monkeypatch.setenv(paths.ENV_REGISTRY, str(target))

    assert board_server.registry_path() == str(target)
