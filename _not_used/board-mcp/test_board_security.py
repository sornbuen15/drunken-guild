# mypy: ignore-errors
"""S1 and S2 — the two findings left open in board_mcp.

Both sat on `develop` for weeks while DG-225 said IN REVIEW, on a branch that
was never merged. Every surface agreed they were fixed. So each of these was
run red before the fix existed, and each assertion carries the reason it is
here rather than just the expectation.

**S1 — path traversal.** `query_project_context` took any absolute path and
opened it. Not a traversal bug in the usual sense; there was no containment
check of any kind to traverse *around*.

**S2 — `project` is a lookup key, not a boundary.** Every tool resolves the
project through the registry and then serves it, whatever the server was
launched to serve. `main()` said so out loud: "--project (ignored by board,
kept for compat)".

Neither is remotely reachable today, because everything is local stdio. DG-226
is precisely the change that would alter that, which is why it waits on these.
"""

from __future__ import annotations

import pytest

from board_mcp.board import BoardManager


@pytest.fixture()  # type: ignore[misc]
def project(tmp_path):
    """A project root with one readable context file, and a secret outside it."""
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "SPEC.md").write_text(
        "# Overview\nthe keyword lives here\n", encoding="utf-8"
    )
    (tmp_path / "secret.txt").write_text(
        "# Secrets\nthe keyword lives here too\n", encoding="utf-8"
    )
    return root, tmp_path


class TestS1Containment:
    def test_an_absolute_path_outside_the_project_is_refused(self, project) -> None:
        """The finding itself. `if os.path.isabs(file_path): resolved = file_path`
        opened anything the process could read — every other project's board,
        a private key, /etc/passwd — and returned its matching lines."""
        root, outside = project
        result = BoardManager(str(root / ".claude" / "board")).query_project_context(
            str(root), [str(outside / "secret.txt")], ["keyword"]
        )
        assert result["total_matches"] == 0, "content from outside the project leaked"
        assert result["results"][0]["error"] == "access_denied_path_traversal"

    def test_a_relative_path_climbing_out_is_refused(self, project) -> None:
        """The other spelling. Containment has to be judged after normalising,
        or `../../secret.txt` walks straight past a check on the raw string."""
        root, _ = project
        result = BoardManager(str(root / ".claude" / "board")).query_project_context(
            str(root), ["../secret.txt"], ["keyword"]
        )
        assert result["results"][0]["error"] == "access_denied_path_traversal"

    def test_a_symlink_pointing_out_of_the_project_is_refused(self, project) -> None:
        """A path can be inside the project and still resolve outside it. Only
        comparing the *resolved* path catches this, which is why the fix
        resolves both sides rather than comparing strings."""
        root, outside = project
        (root / ".claude" / "escape.md").symlink_to(outside / "secret.txt")
        result = BoardManager(str(root / ".claude" / "board")).query_project_context(
            str(root), ["escape.md"], ["keyword"]
        )
        assert result["total_matches"] == 0, "a symlink walked out of the project"

    def test_a_legitimate_file_still_reads(self, project) -> None:
        """The fix has to keep the tool useful. A containment check that
        refuses everything passes the tests above and helps nobody."""
        root, _ = project
        result = BoardManager(str(root / ".claude" / "board")).query_project_context(
            str(root), ["SPEC.md"], ["keyword"]
        )
        assert result["total_matches"] >= 1
        assert "error" not in result["results"][0]

    def test_a_missing_file_is_still_reported_as_missing(self, project) -> None:
        """`file_not_found` and `access_denied_path_traversal` are different
        answers and must stay that way — collapsing them into one would make a
        typo look like an attack, and an attack look like a typo."""
        root, _ = project
        result = BoardManager(str(root / ".claude" / "board")).query_project_context(
            str(root), ["NOPE.md"], ["keyword"]
        )
        assert result["results"][0]["error"] == "file_not_found"

    def test_an_error_row_is_not_counted_as_a_match(self, project) -> None:
        """`total_matches` counted every row, errors included, so a refused
        path answered `total_matches: 1` — which reads as "you got something"
        at the exact moment the answer is "you got nothing, and here is why"."""
        root, outside = project
        result = BoardManager(str(root / ".claude" / "board")).query_project_context(
            str(root), [str(outside / "secret.txt"), "SPEC.md"], ["keyword"]
        )
        assert result["total_matches"] == 1, "only the legitimate file is a match"
        assert len(result["results"]) == 2, "the refusal is still reported"


class TestS2ProjectIsABoundary:
    """`project` was a lookup key. A key opens whatever it names.

    `main()` said it out loud — "--project (ignored by board, kept for compat)"
    — so a board server launched to serve one project would happily serve any
    other registered one on request. The registry lookup was authentication
    with no authorisation behind it.
    """

    def test_a_server_bound_to_one_project_refuses_another(
        self, tmp_path, monkeypatch
    ) -> None:
        from board_mcp import server
        from core.errors import DrunkenError

        monkeypatch.setenv(server.ENV_BOARD_PROJECT, "drunken-team")
        with pytest.raises(DrunkenError) as caught:
            server._get_manager("isac")
        assert "isac" in str(caught.value)

    def test_the_bound_project_itself_still_resolves(
        self, tmp_path, monkeypatch
    ) -> None:
        """The boundary must not break the thing it protects."""
        from board_mcp import server

        registry = tmp_path / "projects.json"
        registry.write_text(
            '{"version": 2, "projects": {"mine": {"path": "%s"}}}' % tmp_path,
            encoding="utf-8",
        )
        monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry))
        monkeypatch.setenv(server.ENV_BOARD_PROJECT, "mine")
        manager, root = server._get_manager("mine")
        assert root == str(tmp_path)

    def test_an_unbound_server_refuses_everything(self, monkeypatch) -> None:
        """Default deny. An unbound board server has no way to know which
        project it is entitled to serve, and guessing is what S2 was.

        This is a behaviour change: before, no `--project` meant "serve them
        all". The repo's own `.mcp.json` relied on that and is updated in the
        same commit. Antigravity's config already passed `--project`.
        """
        from board_mcp import server
        from core.errors import DrunkenError

        monkeypatch.delenv(server.ENV_BOARD_PROJECT, raising=False)
        with pytest.raises(DrunkenError) as caught:
            server._get_manager("anything")
        # Checked on `.remediation`, not on str(): the project's own rule is
        # that every error carries the concrete next step, because "unknown
        # project" on its own only tells an agent to give up.
        assert "--project" in (caught.value.remediation or "")

    def test_any_config_that_does_wire_the_board_binds_it(self) -> None:
        """DG-250 retired the board and no config here declares it any more, so
        this asserts the conditional rather than the fact: *if* a config wires
        the board server, it must bind it to a project.

        Kept rather than deleted because the S2 finding does not expire. The
        server still exists on disk and can still be run; an unbound one serves
        whatever it is asked for, and that stays true whether or not this repo
        happens to declare it today.
        """
        import json
        from pathlib import Path

        config = json.loads(
            (Path(__file__).resolve().parents[1] / ".mcp.json").read_text(
                encoding="utf-8"
            )
        )
        entry = config["mcpServers"].get("drunken-board-mcp")
        if entry is None:
            return  # retired here, which is the expected state after DG-250
        assert "--project" in entry["args"], "a wired board server must be bound"
