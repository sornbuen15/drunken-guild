# mypy: ignore-errors
"""Pruning a host config this project does not own — DG-324.

`drunken-config` already prunes, and deliberately prunes only its own:
`is_drunken_managed` matches `drunken-*-mcp` and nothing else, because
`config_gen.py` records that keeping foreign entries out of reach is the point.
A generator that removed a server it never wrote would be a generator nobody
could trust with a host's file.

So the foreign half needs a different tool with different manners, and the
manners are the design:

- **It says what it would do and writes nothing.** `--apply` is the only way to
  a write, and a backup lands before the write does.
- **It refuses a `drunken-*-mcp` name outright.** Two tools that can both remove
  the same entry are two tools that can disagree about who removed it. This one
  is not allowed near them.
- **It names servers explicitly.** "Remove everything that does not resolve"
  would have taken Antigravity's own datacloud entries with it, which the host
  regenerates and which are none of our business.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import clean_host_config as clean  # noqa: E402


def _config(path, servers, archived=None):
    document = {"mcpServers": servers}
    if archived is not None:
        document["archivedMcpServers"] = archived
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestItWritesNothingByDefault:
    def test_a_dry_run_leaves_the_file_byte_identical(self, tmp_path, capsys) -> None:
        config = _config(tmp_path / "mcp.json", {"jira-board": {"command": "sh"}})
        before = config.read_bytes()

        clean.main(["--config", str(config), "--drop", "jira-board"])

        assert config.read_bytes() == before
        assert "jira-board" in capsys.readouterr().out

    def test_a_dry_run_creates_no_backup(self, tmp_path) -> None:
        config = _config(tmp_path / "mcp.json", {"jira-board": {"command": "sh"}})
        clean.main(["--config", str(config), "--drop", "jira-board"])
        assert list(tmp_path.glob("*.bak")) == []


class TestApplying:
    def test_a_named_server_is_removed(self, tmp_path) -> None:
        config = _config(
            tmp_path / "mcp.json",
            {"jira-board": {"command": "sh"}, "github": {"command": "sh"}},
        )
        clean.main(["--config", str(config), "--drop", "jira-board", "--apply"])
        assert list(_read(config)["mcpServers"]) == ["github"]

    def test_everything_not_named_survives(self, tmp_path) -> None:
        """The datacloud servers point at versions that are not installed, and
        are still none of our business: Antigravity regenerates them. A pruner
        that removed everything unresolvable would take them too."""
        config = _config(
            tmp_path / "mcp.json",
            {
                "jira-board": {"command": "sh"},
                "notebooks": {"command": "node", "args": ["/gone/bundle.js"]},
            },
        )
        clean.main(["--config", str(config), "--drop", "jira-board", "--apply"])
        assert list(_read(config)["mcpServers"]) == ["notebooks"]

    def test_the_archived_block_goes_only_when_asked(self, tmp_path) -> None:
        config = _config(
            tmp_path / "mcp.json",
            {"github": {"command": "sh"}},
            archived={"board": {"command": "/gone"}},
        )
        clean.main(["--config", str(config), "--drop-archived", "--apply"])
        assert "archivedMcpServers" not in _read(config)

    def test_the_archived_block_survives_an_unrelated_apply(self, tmp_path) -> None:
        config = _config(
            tmp_path / "mcp.json",
            {"jira-board": {"command": "sh"}},
            archived={"board": {"command": "/gone"}},
        )
        clean.main(["--config", str(config), "--drop", "jira-board", "--apply"])
        assert "archivedMcpServers" in _read(config)

    def test_a_backup_exists_before_the_write(self, tmp_path) -> None:
        """The convention already in that tree — `<name>.pre-<TICKET>.bak`, as
        left by DG-277 and DT-246. Recovering by hand needs the file, not a
        memory of what it held."""
        config = _config(tmp_path / "mcp.json", {"jira-board": {"command": "sh"}})
        clean.main(
            [
                "--config",
                str(config),
                "--drop",
                "jira-board",
                "--ticket",
                "DG-324",
                "--apply",
            ]
        )
        backup = tmp_path / "mcp.json.pre-DG-324.bak"
        assert backup.is_file()
        assert list(json.loads(backup.read_text())["mcpServers"]) == ["jira-board"]

    def test_an_existing_backup_is_never_overwritten(self, tmp_path) -> None:
        """A second run must not replace the record of the original state with
        the already-pruned one. That turns a recovery path into a copy of what
        went wrong."""
        config = _config(tmp_path / "mcp.json", {"a": {}, "b": {}})
        clean.main(
            ["--config", str(config), "--drop", "a", "--ticket", "DG-324", "--apply"]
        )
        clean.main(
            ["--config", str(config), "--drop", "b", "--ticket", "DG-324", "--apply"]
        )
        backup = json.loads((tmp_path / "mcp.json.pre-DG-324.bak").read_text())
        assert sorted(backup["mcpServers"]) == ["a", "b"]


class TestItStaysOutOfDrunkenConfigsWay:
    @pytest.mark.parametrize("name", ["drunken-jira-mcp", "drunken-board-mcp"])
    def test_a_drunken_managed_server_is_refused(self, tmp_path, name) -> None:
        """Two tools that can both remove the same entry are two tools that can
        disagree about who removed it. `drunken-config` owns this prefix and
        prunes it on every regeneration; this script is not allowed near it."""
        config = _config(tmp_path / "mcp.json", {name: {"command": "x"}})
        with pytest.raises(SystemExit):
            clean.main(["--config", str(config), "--drop", name, "--apply"])
        assert list(_read(config)["mcpServers"]) == [name]

    def test_the_refusal_names_the_tool_that_owns_it(self, tmp_path) -> None:
        """ "Refused" on its own sends the operator looking for a workaround.
        Naming the tool that does own the entry ends the question instead."""
        config = _config(tmp_path / "mcp.json", {"drunken-jira-mcp": {}})
        with pytest.raises(SystemExit) as exit_info:
            clean.main(["--config", str(config), "--drop", "drunken-jira-mcp"])
        assert "drunken-config" in str(exit_info.value)


class TestWhenTheFileIsNotWhatWasExpected:
    def test_a_missing_config_is_an_error_not_a_new_file(self, tmp_path) -> None:
        """Creating one would leave a config the host reads and nobody wrote."""
        missing = tmp_path / "nope.json"
        with pytest.raises(SystemExit):
            clean.main(["--config", str(missing), "--drop", "x", "--apply"])
        assert not missing.exists()

    def test_invalid_json_is_refused_rather_than_rewritten(self, tmp_path) -> None:
        config = tmp_path / "mcp.json"
        config.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit):
            clean.main(["--config", str(config), "--drop", "x", "--apply"])
        assert config.read_text(encoding="utf-8") == "{not json"

    def test_a_name_that_is_not_there_is_reported_not_silently_ignored(
        self, tmp_path, capsys
    ) -> None:
        """ "Done" on a no-op reads as "removed", and the operator moves on
        believing a server is gone that is still being launched."""
        config = _config(tmp_path / "mcp.json", {"github": {"command": "sh"}})
        clean.main(["--config", str(config), "--drop", "jira-board", "--apply"])
        assert "not present" in capsys.readouterr().out
