# mypy: ignore-errors
"""DG-309. Every `except Exception` on the board-profile path says why.

`_build_profile` catches `Exception` twice and explains both times why
swallowing is right there. `_probe_backlog`, one call down, caught the same
type with no word beside it — the same decision, made silently. A reader
cannot tell a deliberate swallow from a forgotten one, so the rule is that the
reasoning sits in the handler itself.
"""

import ast
from pathlib import Path

CLIENT = Path(__file__).resolve().parent.parent / "src" / "jira_mcp" / "jira_client.py"
FUNCTIONS = {"_probe_backlog", "_build_profile"}


def _bare_handlers() -> list[tuple[str, int]]:
    source = CLIENT.read_text(encoding="utf-8")
    lines = source.splitlines()
    out = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in FUNCTIONS
        ):
            for handler in ast.walk(node):
                if (
                    isinstance(handler, ast.ExceptHandler)
                    and isinstance(handler.type, ast.Name)
                    and handler.type.id == "Exception"
                ):
                    body_first = handler.body[0].lineno
                    between = lines[handler.lineno : body_first - 1]
                    if not any(line.strip().startswith("#") for line in between):
                        out.append((node.name, handler.lineno))
    return out


def test_the_functions_are_found() -> None:
    source = CLIENT.read_text(encoding="utf-8")
    for name in FUNCTIONS:
        assert f"def {name}(" in source


def test_every_swallow_carries_its_reason() -> None:
    assert not _bare_handlers(), f"except Exception with no reason: {_bare_handlers()}"
