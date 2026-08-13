# mypy: ignore-errors
"""`jira_bridge.py --project` — the daemon's route to the registry.

The Discord side picked its project by setting the subprocess working
directory, and `jira_bridge.py` then walked up from there looking for a
``.env``. It never consulted the registry, which is why `/project twa` read an
empty board while the same project answered 39 issues over MCP: TWA's own
``.env`` still held a token that had expired, and a Jira search with a dead
token returns ``200`` and an empty list rather than an error.

Selecting a project by *where a process happens to be standing* was the whole
defect. `--project` names it, and the registry answers.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()  # type: ignore[misc]
def bridge():
    spec = importlib.util.spec_from_file_location(
        "jira_bridge", REPO_ROOT / "scripts" / "jira_bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()  # type: ignore[misc]
def registry(tmp_path, monkeypatch):
    """A registry holding one project, and a secret it can actually resolve."""
    secrets = tmp_path / "secrets.json"
    secrets.write_text(json.dumps({"jira": {"default": "registry-token"}}))

    registry_file = tmp_path / "projects.json"
    registry_file.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {
                    "twa": {
                        "path": str(tmp_path / "twa"),
                        "jira": {
                            "url": "https://example.atlassian.net",
                            "email": "you@example.com",
                            "project_key": "TWA",
                            "credential": f"file://{secrets}#jira.default",
                        },
                    }
                },
            }
        )
    )
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry_file))
    return tmp_path


class TestTheRegistryWinsWhenAProjectIsNamed:
    def test_config_comes_from_the_registry(self, bridge, registry) -> None:
        config = bridge.config_for_project("twa")

        assert config["project_key"] == "TWA"
        assert config["jira_url"] == "https://example.atlassian.net"
        assert config["jira_token"] == "registry-token"

    def test_a_stale_dotenv_beside_the_project_is_ignored(
        self, bridge, registry, monkeypatch
    ) -> None:
        """The actual bug. TWA's checkout carried an expired token in its own
        ``.env``; standing in that directory must no longer change the answer."""
        monkeypatch.setenv("JIRA_TOKEN", "stale-token-from-dotenv")
        monkeypatch.setenv("JIRA_PROJECT_KEY", "WRONG")

        config = bridge.config_for_project("twa")

        assert config["jira_token"] == "registry-token"
        assert config["project_key"] == "TWA"

    def test_an_unknown_project_says_so_and_says_what_to_do(
        self, bridge, registry
    ) -> None:
        """Silence here is what let the empty board pass for a real one."""
        with pytest.raises(SystemExit) as exit_info:
            bridge.config_for_project("no-such-project")

        assert "no-such-project" in str(exit_info.value)
        assert "drunken-init" in str(exit_info.value)

    def test_a_project_with_no_jira_identity_is_an_error_not_an_empty_board(
        self, bridge, registry, tmp_path
    ) -> None:
        (tmp_path / "projects.json").write_text(
            json.dumps({"version": 2, "projects": {"bare": {"path": "/tmp/bare"}}})
        )

        with pytest.raises(SystemExit) as exit_info:
            bridge.config_for_project("bare")

        assert "bare" in str(exit_info.value)


class TestTheShellPathIsUnchanged:
    def test_without_a_project_the_dotenv_route_still_works(
        self, bridge, monkeypatch, tmp_path
    ) -> None:
        """`jira_bridge.py get-todo` from a checkout is how this gets used by
        hand, and breaking that to fix the daemon would be a poor trade."""
        monkeypatch.setenv("JIRA_URL", "https://shell.atlassian.net")
        monkeypatch.setenv("JIRA_EMAIL", "shell@example.com")
        monkeypatch.setenv("JIRA_PROJECT_KEY", "SHELL")
        monkeypatch.setenv("JIRA_TOKEN", "shell-token")
        monkeypatch.chdir(tmp_path)

        config = bridge.config_from_environment()

        assert config["project_key"] == "SHELL"
        assert config["jira_token"] == "shell-token"


class TestTheDaemonNamesTheProject:
    def test_the_router_passes_project_rather_than_relying_on_cwd(self) -> None:
        """cwd still selects where `gh` runs. It must no longer be what decides
        which Jira account answers."""
        source = (REPO_ROOT / "src/service/discord_router.py").read_text(
            encoding="utf-8"
        )

        assert '"--project"' in source, (
            "The router still selects a project by working directory, which is "
            "the bug: jira_bridge resolves .env from wherever it is standing."
        )
