# mypy: ignore-errors
import json
import os
from unittest import mock

from jira_mcp.config import get_jira_config


def test_get_jira_config_reads_project_key_from_local_jira_json(tmp_path, monkeypatch):
    """Regression test: register_project.py writes .agents/jira.json with a
    snake_case "project_key" field. get_jira_config() must read that same
    key -- it previously looked for camelCase "projectKey" instead, so
    anyone who registered a project without also setting JIRA_PROJECT_KEY as
    an env var had their project key silently dropped."""
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "jira.json").write_text(
        json.dumps(
            {
                "jira_url": "https://example.atlassian.net",
                "jira_email": "dev@example.com",
                "project_key": "DT",
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    with mock.patch(
        "jira_mcp.config.os.path.expanduser", return_value="/nonexistent/global.json"
    ):
        config = get_jira_config()

    assert config["project_key"] == "DT"
    assert config["jira_url"] == "https://example.atlassian.net"
    assert config["jira_email"] == "dev@example.com"


def test_get_jira_config_env_vars_win_over_local_jira_json(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_PROJECT_KEY", "ENVKEY")
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)

    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "jira.json").write_text(json.dumps({"project_key": "FILEKEY"}))
    monkeypatch.chdir(tmp_path)

    with mock.patch(
        "jira_mcp.config.os.path.expanduser", return_value="/nonexistent/global.json"
    ):
        config = get_jira_config()

    assert config["project_key"] == "ENVKEY"


def test_get_jira_config_no_local_file_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_PROJECT_KEY", "ENVKEY")
    monkeypatch.chdir(tmp_path)

    with mock.patch(
        "jira_mcp.config.os.path.expanduser", return_value="/nonexistent/global.json"
    ):
        config = get_jira_config()

    assert config["project_key"] == "ENVKEY"
    assert os.getcwd() == str(tmp_path)
