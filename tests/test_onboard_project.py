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
    def test_servers_are_named_not_located(self, onboard) -> None:
        config = onboard.mcp_config("twa")

        serialised = json.dumps(config)
        assert "/Users/" not in serialised and "/home/" not in serialised, (
            "A path here is one developer's machine, written into another "
            "project's repository."
        )
        assert "--directory" not in serialised
        assert "PYTHONPATH" not in serialised

    def test_every_server_is_declared_and_scoped_to_the_project(self, onboard) -> None:
        config = onboard.mcp_config("twa")["mcpServers"]

        assert set(config) == set(onboard.MCP_SERVERS)
        for name, entry in config.items():
            assert entry["command"] == name, (
                "The command is the entry point name, which is what makes it "
                "resolvable without a path once installed."
            )
            assert entry["args"] == ["--project", "twa"], (
                f"{name} is not scoped to a project, so it would act on "
                "whichever one it defaulted to."
            )

    def test_the_removed_workspace_flag_is_not_reintroduced(self, onboard) -> None:
        """What TWA's previous config passed. It was deleted in DT-224, and
        argparse ignores it silently rather than complaining."""
        assert "--workspace" not in json.dumps(onboard.mcp_config("twa"))


class TestTheCredentialIsSharedByReference:
    def test_projects_point_at_one_key_by_default(self, onboard, monkeypatch) -> None:
        monkeypatch.setenv("DRUNKEN_HOME", "/tmp/probe-home")

        for project in ("twa", "isac", "drunken-team"):
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
