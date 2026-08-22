# mypy: ignore-errors
"""Onboarding another project, and the two decisions inside it.

Both exist because of specific damage:

* **One credential, referenced many times.** TWA had its own copy of the Jira
  token. It expired, and because a Jira search answers a dead credential with
  ``200`` and an empty list, its board simply read as empty — for months, with
  nothing anywhere saying why. Copies drift; a reference cannot.
* **No paths in the generated config.** Another repository's ``.mcp.json`` gets
  a command name and nothing else, so one machine's directory layout never
  ends up committed in someone else's history.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from core import config_gen

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")  # type: ignore[misc]
def onboard():
    spec = importlib.util.spec_from_file_location(
        "onboard_project", REPO_ROOT / "scripts" / "onboard_project.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheGeneratedConfigCarriesNoPaths:
    def test_servers_are_named_not_located(self) -> None:
        config = config_gen.mcp_config("twa")

        serialised = json.dumps(config)
        assert "/Users/" not in serialised and "/home/" not in serialised, (
            "A path here is one developer's machine, written into another "
            "project's repository."
        )
        assert "--directory" not in serialised
        assert "PYTHONPATH" not in serialised

    def test_every_server_is_declared_and_scoped_to_the_project(self) -> None:
        config = config_gen.mcp_config("twa")["mcpServers"]

        assert set(config) == set(config_gen.MCP_SERVERS)
        for name, entry in config.items():
            assert entry["command"] == name, (
                "The command is the entry point name, which is what makes it "
                "resolvable without a path once installed."
            )
            assert entry["args"] == ["--project", "twa"], (
                f"{name} is not scoped to a project, so it would act on "
                "whichever one it defaulted to."
            )

    def test_the_retired_board_server_is_not_wired_in(self) -> None:
        """DG-250 retired the local board and DG-251 wrote down why: a second
        coordination surface can disagree with Jira, which is the failure that
        cost DG-248 and DG-249 whole sessions. CLAUDE.md says do not
        reintroduce it -- and onboarding was declaring it into every project.

        The test above cannot catch this. It asserts the config matches
        MCP_SERVERS, so it agrees with whatever that constant says; this one
        asserts against the decision instead.
        """
        serialised = json.dumps(config_gen.mcp_config("twa"))

        assert "board" not in serialised, (
            "Onboarding declared drunken-board-mcp, a server retired by "
            "DG-250. It costs 2,162 tokens per request and reopens the "
            "two-surfaces problem that retiring it closed."
        )

    def test_the_removed_workspace_flag_is_not_reintroduced(self) -> None:
        """What TWA's previous config passed. It was deleted in DG-224, and
        argparse ignores it silently rather than complaining."""
        assert "--workspace" not in json.dumps(config_gen.mcp_config("twa"))


class TestTheCredentialIsSharedByReference:
    def test_projects_point_at_one_key_by_default(self, onboard, monkeypatch) -> None:
        monkeypatch.setenv("DRUNKEN_HOME", "/tmp/probe-home")

        for project in ("twa", "isac", "drunken-guild"):
            reference = onboard.credential_reference(onboard.SHARED_CREDENTIAL_KEY)
            assert reference.endswith("#jira.default"), (
                f"{project} would get its own copy of the token. That is how "
                "TWA's drifted to a dead value nobody noticed."
            )

    def test_the_reference_uses_a_tilde_not_a_username(
        self, onboard, monkeypatch
    ) -> None:
        """The registry is meant to be readable, shareable and diffable; a
        hardcoded home directory makes it none of those."""
        monkeypatch.delenv("DRUNKEN_HOME", raising=False)

        reference = onboard.credential_reference("default")

        assert reference.startswith("file://~/"), reference

    def test_a_project_may_still_be_given_its_own_key(self, onboard) -> None:
        """Sharing is the default, not a rule — a different Jira account is a
        legitimate reason to diverge."""
        assert onboard.credential_reference("client-x").endswith("#jira.client-x")


class TestAHostConfigIsDifferentFromARepoConfig:
    """The one place a path belongs, and the one place it does not.

    A repository's `.mcp.json` is committed and shared, so it names the command
    and nothing else. A host config — Antigravity's, Cursor's — lives in the
    user's home, is never committed, and is read by an application launched
    from `/Applications` with launchd's minimal PATH. A bare name there
    resolves when you test it in a terminal and fails inside the IDE, which is
    the same trap `setup_daemon_service.py` documents for `uv`.
    """

    def test_the_host_config_names_an_absolute_command(
        self, tmp_path, monkeypatch
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in config_gen.MCP_SERVERS:
            (bin_dir / name).write_text("#!/bin/sh\n")
        monkeypatch.setenv("UV_TOOL_BIN_DIR", str(bin_dir))

        host = tmp_path / "mcp_config.json"
        config_gen.merge_into_host_config(host, "twa")

        entry = json.loads(host.read_text())["mcpServers"]["drunken-jira-mcp"]
        assert entry["command"] == str(bin_dir / "drunken-jira-mcp")

    def test_a_development_virtualenv_is_not_what_gets_written(
        self, tmp_path, monkeypatch
    ) -> None:
        """`uv run` puts the project's own venv first on PATH, so that is what
        `which` answers while developing. It works until the venv is rebuilt."""
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        executable = venv_bin / "drunken-jira-mcp"
        executable.write_text("#!/bin/sh\n")
        executable.chmod(0o755)
        monkeypatch.setenv("UV_TOOL_BIN_DIR", str(tmp_path / "absent"))
        monkeypatch.setenv("PATH", str(venv_bin))

        resolved = config_gen.resolve_command("drunken-jira-mcp")

        assert resolved == str(venv_bin / "drunken-jira-mcp"), (
            "It still has to return something usable — but the warning is the "
            "point, because the failure otherwise arrives weeks later."
        )

    def test_the_hosts_own_servers_survive(self, tmp_path) -> None:
        """Antigravity declares a kanban script and a third-party Jira server.
        Overwriting the file to add ours would take those with it."""
        host = tmp_path / "mcp_config.json"
        host.write_text(
            json.dumps({"mcpServers": {"kanban-board": {"command": "node"}}})
        )

        config_gen.merge_into_host_config(host, "twa")

        servers = json.loads(host.read_text())["mcpServers"]
        assert servers["kanban-board"] == {"command": "node"}
        assert set(config_gen.MCP_SERVERS) <= set(servers)

    def test_merging_twice_changes_nothing_the_second_time(self, tmp_path) -> None:
        host = tmp_path / "mcp_config.json"
        config_gen.merge_into_host_config(host, "twa")

        assert config_gen.merge_into_host_config(host, "twa") == []


class TestSecretsAreWrittenLockedDown:
    def test_the_file_is_never_briefly_readable(self, onboard, monkeypatch, tmp_path):
        """Created with the mode rather than chmod-ed after: in between, the
        token sits on disk at whatever the umask allowed."""
        import stat

        monkeypatch.setenv("DRUNKEN_HOME", str(tmp_path / "state"))
        monkeypatch.setattr(
            onboard.paths, "home", lambda: _Resolved(tmp_path / "state")
        )

        path = onboard.write_secrets({"jira": {"default": "not-a-real-token"}})

        assert stat.S_IMODE(path.stat().st_mode) == 0o600


class _Resolved:
    def __init__(self, path: Path) -> None:
        self.path = path
