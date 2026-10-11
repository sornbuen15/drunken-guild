# mypy: ignore-errors
"""The MCP configs a host reads, which nothing here writes — DG-322.

Onboarding merges into exactly one file per host, so the servers this project
installs are correct by construction. The servers it does *not* install are the
problem, and no check has ever looked at them.

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
        doctor._check_host_configs(report, roots=(("example.host", config),))
        check = _named(report, "host_mcp.example.host")
        assert check.status == "warn"
        assert "notebooks" in check.detail

    def test_an_absolute_command_that_does_not_exist_is_named(self, tmp_path) -> None:
        config = _write(
            tmp_path / "mcp_config.json",
            {"board": {"command": str(tmp_path / "bin" / "drunken-board-mcp")}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))
        check = _named(report, "host_mcp.example.host")
        assert check.status == "warn"
        assert "board" in check.detail

    def test_a_command_that_resolves_is_left_alone(self, tmp_path) -> None:
        binary = tmp_path / "bin" / "drunken-jira-mcp"
        binary.parent.mkdir(parents=True)
        binary.write_text("", encoding="utf-8")
        # `args` deliberately empty: this test is about the command resolving,
        # and a `--project` here would also trip the stale-project check below,
        # making a passing test depend on two unrelated properties.
        config = _write(
            tmp_path / "mcp_config.json",
            {"drunken-jira-mcp": {"command": str(binary), "args": []}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))
        assert _named(report, "host_mcp.example.host").status == "ok"

    def test_a_command_found_on_path_is_not_reported_missing(self, tmp_path) -> None:
        """`node`, `npx` and `uv` are named without a path on purpose. Treating
        every bare command as missing would report a healthy config as broken,
        which is how a check gets ignored."""
        config = _write(
            tmp_path / "mcp_config.json",
            {"github": {"command": "sh", "args": ["-c", "true"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))
        assert _named(report, "host_mcp.example.host").status == "ok"

    def test_an_archived_server_is_not_checked(self, tmp_path) -> None:
        """`archivedMcpServers` is the host's own record of what it stopped
        launching. Reporting it would be reporting a decision as a defect."""
        config = _write(
            tmp_path / "mcp_config.json",
            # One live server beside it, so "the archived one was ignored" is
            # distinguishable from "there was nothing to read at all" -- with an
            # empty block this now reports `skip`, which would pass for the
            # wrong reason.
            {"drunken-jira-mcp": {"command": "sh", "args": []}},
            archived={"board": {"command": str(tmp_path / "gone" / "board-mcp")}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))
        assert _named(report, "host_mcp.example.host").status == "ok"


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
        doctor._check_host_configs(report, roots=(("example.host", config),))
        check = _named(report, "host_mcp.example.host")
        assert check.status == "warn"
        assert "jira-board" in check.detail

    def test_our_own_jira_server_is_not_a_rival(self, tmp_path) -> None:
        config = _write(
            tmp_path / "mcp_config.json",
            {"drunken-jira-mcp": {"command": "sh", "args": ["-c", "true"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))
        assert _named(report, "host_mcp.example.host").status == "ok"


class TestAStaleProjectIsReported:
    """DG-341 left one thing for a person to do, and this is what tells them.

    The server takes no project now; every tool takes it as an argument. An
    entry still passing `--project` is not broken — verified by handshake: the
    flag is accepted and ignored, so nothing fails. That is exactly why it needs
    saying. It reads like the thing that decides which Jira a session reaches,
    it no longer is, and the user-scope entry carrying it is the one DG-341 asks
    the operator to remove.
    """

    def test_a_drunken_server_still_carrying_a_project_is_named(self, tmp_path) -> None:
        config = _write(
            tmp_path / "mcp_config.json",
            {
                "drunken-jira-mcp": {
                    "command": "sh",
                    "args": ["--project", "drunken-guild"],
                }
            },
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))

        check = _named(report, "host_mcp.example.host")
        assert check.status == "warn"
        assert "--project" in check.detail
        assert "ignores it" in check.detail or "ignores it" in check.remediation

    def test_the_remedy_does_not_break_a_stale_deployment(self, tmp_path) -> None:
        """The first version of this said "drop the args", and that is wrong
        while the installed server predates DG-341: it reads `--project`, and
        without one every tool call answers "started without a project". Proved
        by handshake against the installed binary on 2026-09-13, after the advice
        had already been followed once. Merging is not deploying, and this
        remediation is read by whoever is about to edit the live file.
        """
        config = _write(
            tmp_path / "mcp_config.json",
            {"drunken-jira-mcp": {"command": "sh", "args": ["--project", "dg"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))

        remediation = _named(report, "host_mcp.example.host").remediation
        assert "Reinstall" in remediation, (
            "The order matters: reinstall, confirm, then drop the flag."
        )
        assert "installed" in remediation

    def test_a_foreign_server_carrying_a_project_is_not_our_business(
        self, tmp_path
    ) -> None:
        """`--project` is a perfectly ordinary flag on somebody else's server,
        and a check that fired on it would be noise the operator learns to
        skip."""
        config = _write(
            tmp_path / "mcp_config.json",
            {"some-other-mcp": {"command": "sh", "args": ["--project", "whatever"]}},
        )
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))

        assert _named(report, "host_mcp.example.host").status == "ok"


class TestWhenThereIsNothingToRead:
    def test_an_absent_config_is_a_skip_not_a_failure(self, tmp_path) -> None:
        """A machine with no Antigravity installed legitimately has none."""
        report = doctor.Report()
        doctor._check_host_configs(
            report, roots=(("example.host", tmp_path / "nope.json"),)
        )
        assert _named(report, "host_mcp.example.host").status == "skip"

    def test_unreadable_json_is_a_warning_that_names_the_file(self, tmp_path) -> None:
        config = tmp_path / "mcp_config.json"
        config.write_text("{not json", encoding="utf-8")
        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", config),))
        check = _named(report, "host_mcp.example.host")
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
        doctor._check_host_configs(report, roots=(("example.host", config),))
        assert report.failed is False

    def test_no_default_root_reaches_into_a_retired_host(self) -> None:
        """Both defaults were Antigravity's own configs under `~/.gemini`, and
        DG-349 retired that plumbing — reading a file there is reaching into
        another agent's own state.

        Asserted as "nothing points at ~/.gemini" rather than "there are no
        default roots", which is what it used to say. The tuple being empty was
        a consequence of that removal, not the rule; asserting the consequence
        made the check's own blindness look deliberate (DG-356).
        """
        for _, raw in doctor.HOST_MCP_CONFIGS:
            assert ".gemini" not in raw, (
                f"{raw} is another agent's own state; editing or reading a file "
                "there is an install, and DG-349 retired that plumbing."
            )


class TestItActuallyLooksAtSomething:
    """A check with no roots cannot fire, and passes its own tests forever.

    `HOST_MCP_CONFIGS` was emptied when DG-349 retired the Antigravity plumbing:
    both entries were configs under `~/.gemini`. Every test in this file injects
    its own roots, so the check stayed green while having nothing to read — and
    the stale-project notice added in DG-341 could never reach the one file that
    matters, `~/.claude.json`, where a user-scope entry reaches every session on
    the machine.
    """

    def test_the_default_roots_are_not_empty(self) -> None:
        assert doctor.HOST_MCP_CONFIGS, (
            "No default roots means this check reads nothing in real use. Its "
            "tests would still pass, because they pass their own roots."
        )

    def test_the_claude_host_config_is_among_them(self) -> None:
        named = [raw for _, raw in doctor.HOST_MCP_CONFIGS]
        assert any("claude.json" in raw for raw in named), (
            "~/.claude.json is where a user-scope entry lives, which is the "
            "scope that reaches every session (DG-341)."
        )

    def test_a_config_with_no_servers_is_not_a_warning(self, tmp_path) -> None:
        """`~/.claude.json` holds much more than MCP servers, and a host with
        none declared is ordinary. Reading a missing key as unparseable would
        make the common case look like a fault."""
        path = tmp_path / ".claude.json"
        path.write_text(json.dumps({"someOtherKey": True}), encoding="utf-8")

        report = doctor.Report()
        doctor._check_host_configs(report, roots=(("example.host", path),))

        check = _named(report, "host_mcp.example.host")
        assert check.status in ("ok", "skip"), (
            f"a config declaring no servers reported {check.status}: {check.detail}"
        )
