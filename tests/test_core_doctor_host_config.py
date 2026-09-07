# mypy: ignore-errors
"""The MCP configs a host reads, which nothing here writes — DG-322.

`drunken-config` manages exactly one file per host and merges into it, so the
servers this project installs are correct by construction. The servers it does
*not* install are the problem, and no check has ever looked at them.

Two facts drove this:

1. **Antigravity merges more than one config.** On its last run it rewrote tool
   descriptors for a `board` server — sixteen of them, including
   `board_claim_task` — while `~/.gemini/antigravity-cli/mcp_config.json`, the
   file `drunken-config` writes, named no such server. The entry was in
   `~/.gemini/config/mcp_config.json`, which nothing in this repository touches.
   The board was retired in DG-265; it was still being launched.
2. **A dead server is indistinguishable from a live one until it is launched.**
   Five of the six servers in that second config cannot start: one runs an npm
   package that returns 404, and four point at extension paths for versions that
   are not installed. Every launch tries all six and fails five, silently.

The check reads paths given to it rather than the developer's home, for the same
reason `_check_deployment` takes an `env_root`: a test that passes or fails
depending on whose laptop runs it is not a test.
"""

from __future__ import annotations

import json

from core import doctor


def _named(report, name):
    return next((c for c in report.checks if c.name == name), None)


def _write(path, servers, archived=None):
    document = {"mcpServers": servers}
    if archived is not None:
        document["archivedMcpServers"] = archived
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class TestNamingWhatCannotStart:
    def test_a_server_pointing_at_a_missing_file_is_named(self, tmp_path) -> None:
        """ "One server is unresolvable" would send the reader back to the shell
        to find out which, and there are six of them."""
        config = _write(
            tmp_path / "mcp_config.json",
            {
                "notebooks": {
                    "command": "node",
                    "args": [str(tmp_path / "extensions" / "gone" / "bundle.js")],
                }
            },
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        check = _named(report, "host_mcp.antigravity.config")
        assert check.status == "warn"
        assert "notebooks" in check.detail

    def test_an_absolute_command_that_does_not_exist_is_named(self, tmp_path) -> None:
        config = _write(
            tmp_path / "mcp_config.json",
            {"board": {"command": str(tmp_path / "bin" / "drunken-board-mcp")}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        check = _named(report, "host_mcp.antigravity.config")
        assert check.status == "warn"
        assert "board" in check.detail

    def test_a_command_that_resolves_is_left_alone(self, tmp_path) -> None:
        binary = tmp_path / "bin" / "drunken-jira-mcp"
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
        config = _write(
            tmp_path / "mcp_config.json",
            {"drunken-jira-mcp": {"command": str(binary), "args": ["--project", "dg"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        assert _named(report, "host_mcp.antigravity.config").status == "ok"

    def test_a_command_found_on_path_is_not_reported_missing(self, tmp_path) -> None:
        """`node`, `npx` and `uv` are named without a path on purpose. Treating
        every bare command as missing would report a healthy config as broken,
        which is how a check gets ignored."""
        config = _write(
            tmp_path / "mcp_config.json",
            {"github": {"command": "sh", "args": ["-c", "true"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        assert _named(report, "host_mcp.antigravity.config").status == "ok"

    def test_an_archived_server_is_not_checked(self, tmp_path) -> None:
        """`archivedMcpServers` is the host's own record of what it stopped
        launching. Reporting it would be reporting a decision as a defect."""
        config = _write(
            tmp_path / "mcp_config.json",
            {},
            archived={"board": {"command": str(tmp_path / "gone" / "board-mcp")}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        assert _named(report, "host_mcp.antigravity.config").status == "ok"


class TestOneJiraSurface:
    def test_a_second_jira_server_is_reported(self, tmp_path) -> None:
        """The founding failure of this repository, in a file nothing here
        writes. Two servers answering "what is on the board" can disagree, and
        the one that is not ours is the one no check covers."""
        config = _write(
            tmp_path / "mcp_config.json",
            {
                "jira-board": {
                    "command": "sh",
                    "args": ["-c", "npx -y @modelcontextprotocol/server-jira"],
                }
            },
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        check = _named(report, "host_mcp.antigravity.config")
        assert check.status == "warn"
        assert "jira-board" in check.detail

    def test_our_own_jira_server_is_not_a_rival(self, tmp_path) -> None:
        config = _write(
            tmp_path / "mcp_config.json",
            {"drunken-jira-mcp": {"command": "sh", "args": ["-c", "true"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        assert _named(report, "host_mcp.antigravity.config").status == "ok"


class TestWhenThereIsNothingToRead:
    def test_an_absent_config_is_a_skip_not_a_failure(self, tmp_path) -> None:
        """A machine with no Antigravity installed legitimately has none."""
        report = doctor.Report()
        doctor._check_host_configs(
            report, roots=(("antigravity.config", tmp_path / "nope.json"),)
        )
        assert _named(report, "host_mcp.antigravity.config").status == "skip"

    def test_unreadable_json_is_a_warning_that_names_the_file(self, tmp_path) -> None:
        config = tmp_path / "mcp_config.json"
        config.write_text("{not json", encoding="utf-8")
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        check = _named(report, "host_mcp.antigravity.config")
        assert check.status == "warn"
        assert str(config) in check.detail


class TestItNeverBreaksTheRun:
    def test_a_warning_does_not_raise_the_exit_code(self, tmp_path) -> None:
        """Drift here is an operator's edit to a file outside this repository.
        Naming it is the job; failing the run over it is not."""
        config = _write(
            tmp_path / "mcp_config.json",
            {"gone": {"command": str(tmp_path / "nope")}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("antigravity.config", config),))
        assert report.failed is False

    def test_the_default_roots_are_both_antigravity_configs(self) -> None:
        """Reading only the file `drunken-config` writes is what let a retired
        board server keep launching from the file it does not."""
        names = [name for name, _ in doctor.HOST_MCP_CONFIGS]
        assert names == ["antigravity.cli", "antigravity.config"]
