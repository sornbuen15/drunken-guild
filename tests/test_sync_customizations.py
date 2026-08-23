# mypy: ignore-errors
"""DG-276. The sync must not decide where it writes by climbing the tree.

`find_workspace_root()` walked `os.getcwd()` up through `os.path.dirname` until
some `.agents/` existed, and `main()` used the result as the **write** target
for the synced skills and agents. Finding none, it fell back to
`~/.gemini/config` without saying so.

This is the discovery-by-climbing pattern DG-254 removed from config loading
and DG-275 removed from both Jira bridges. It is worse here than the checkpoint
recorded: the climbed directory is not resolved and read, it is written into.
Where an install lands was decided by whatever the current directory happened
to be.

`CLAUDE.md` says to grep for the signature rather than reason about it —
`os.getcwd()` plus a loop over `os.path.dirname` — so one of these tests does
exactly that.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import sync_customizations as sync

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_customizations.py"


class TestNothingClimbs:
    def test_the_climbing_helper_is_gone(self) -> None:
        assert not hasattr(sync, "find_workspace_root"), (
            "find_workspace_root() resolved a write target by walking up from "
            "the current directory — the pattern DG-254 and DG-275 removed "
            "everywhere else"
        )

    def test_the_signature_is_absent_from_the_source(self) -> None:
        """The grep CLAUDE.md asks for, as a test so it runs every time.

        Over the AST rather than the text: the prose in this file and in the
        script both have to name `os.getcwd()` to explain why it is banned, and
        a substring search cannot tell an explanation from a call.
        """
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "getcwd"
        ]

        assert not calls, (
            "os.getcwd() plus a dirname loop is the banned signature; a target "
            f"comes from an argument or it does not come at all. Called on line "
            f"{[c.lineno for c in calls]}"
        )


class TestTheTargetIsAlwaysNamed:
    def test_no_flag_refuses_instead_of_guessing(self) -> None:
        with pytest.raises(SystemExit):
            sync.resolve_target(global_target=False, workspace=None)

    def test_the_refusal_names_both_flags(self, capsys) -> None:
        """A refusal that does not say what to type instead is a wall."""
        with pytest.raises(SystemExit):
            sync.resolve_target(global_target=False, workspace=None)

        message = capsys.readouterr().err
        assert "--global" in message and "--workspace" in message, (
            f"the error has to carry the remedy. Got: {message!r}"
        )

    def test_an_explicit_workspace_is_used_verbatim(self, tmp_path) -> None:
        kind, path = sync.resolve_target(global_target=False, workspace=str(tmp_path))

        assert (kind, Path(path)) == ("workspace", tmp_path)

    def test_global_still_resolves_to_the_gemini_config(self) -> None:
        kind, path = sync.resolve_target(global_target=True, workspace=None)

        assert kind == "global" and path.endswith("/.gemini/config")


class TestADecoyUpTheTreeIsNotFound:
    def test_a_run_from_a_nested_directory_writes_nothing(self, tmp_path) -> None:
        """The ticket's acceptance. Before the fix this run found the decoy by
        climbing and synced into it; now it refuses because no target was
        named."""
        decoy = tmp_path / ".agents"
        decoy.mkdir()
        nested = tmp_path / "one" / "two"
        nested.mkdir(parents=True)

        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=nested,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "with no target named, the sync must refuse rather than pick one "
            f"off the path. stdout: {result.stdout!r}"
        )
        assert list(decoy.iterdir()) == [], (
            f"the decoy .agents/ up the tree was written into: "
            f"{[p.name for p in decoy.iterdir()]}"
        )
