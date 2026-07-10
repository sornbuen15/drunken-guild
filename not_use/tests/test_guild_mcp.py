import os
import subprocess
from unittest import mock

import pytest
from service.guild_mcp import get_jira_config, get_jira_todo, transition_issue


@mock.patch("service.guild_mcp.jira_bridge.get_jira_token", autospec=True)
@mock.patch.dict(
    os.environ,
    {
        "JIRA_URL": "http://jira.test",
        "JIRA_EMAIL": "test@test.com",
        "JIRA_PROJECT_KEY": "PROJ",
    },
)
def test_get_jira_config(mock_get_token):
    mock_get_token.return_value = "secret_token"
    config = get_jira_config()
    assert config == {
        "jira_url": "http://jira.test",
        "jira_email": "test@test.com",
        "project_key": "PROJ",
        "jira_token": "secret_token",
    }


@mock.patch("service.guild_mcp.jira_bridge.get_jira_token", autospec=True)
def test_get_jira_config_no_token(mock_get_token):
    mock_get_token.return_value = None
    with pytest.raises(ValueError, match="JIRA_TOKEN not found"):
        get_jira_config()


@mock.patch("service.guild_mcp.jira_bridge.search_issues", autospec=True)
@mock.patch("service.guild_mcp.get_jira_config", autospec=True)
def test_get_jira_todo_found(mock_get_config, mock_search):
    mock_get_config.return_value = {"project_key": "PROJ"}
    mock_search.return_value = [
        {"key": "PROJ-1", "summary": "Task 1", "status": "To Do", "priority": "High"},
        {"key": "PROJ-2", "summary": "Task 2", "status": "Backlog", "priority": "Low"},
    ]
    result = get_jira_todo()
    assert "[PROJ-1] Task 1 (Status: To Do, Priority: High)" in result
    assert "[PROJ-2] Task 2 (Status: Backlog, Priority: Low)" in result
    mock_search.assert_called_once()


@mock.patch("service.guild_mcp.jira_bridge.search_issues", autospec=True)
@mock.patch("service.guild_mcp.get_jira_config", autospec=True)
def test_get_jira_todo_empty(mock_get_config, mock_search):
    mock_get_config.return_value = {"project_key": "PROJ"}
    mock_search.return_value = []
    result = get_jira_todo()
    assert result == "No tasks found in To Do or Backlog."


@mock.patch("service.guild_mcp.subprocess.run", autospec=True)
def test_transition_issue_success(mock_run):
    mock_proc = mock.MagicMock(autospec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = "Success!"
    mock_run.return_value = mock_proc

    result = transition_issue("PROJ-1", "Done")
    assert "Successfully transitioned PROJ-1 to Done" in result
    mock_run.assert_called_once()


@mock.patch("service.guild_mcp.subprocess.run", autospec=True)
def test_transition_issue_fail(mock_run):
    mock_proc = mock.MagicMock(autospec=subprocess.CompletedProcess)
    mock_proc.returncode = 1
    mock_proc.stderr = "Error!"
    mock_run.return_value = mock_proc

    result = transition_issue("PROJ-1", "Done")
    assert "Failed to transition PROJ-1 to Done" in result
    mock_run.assert_called_once()


@mock.patch("service.guild_mcp.subprocess.run", autospec=True)
def test_transition_issue_exception(mock_run):
    mock_run.side_effect = Exception("System error")
    result = transition_issue("PROJ-1", "Done")
    assert "Error executing jira_bridge.py: System error" in result


@mock.patch("service.guild_mcp.mcp.run", autospec=True)
def test_main(mock_run):
    from service.guild_mcp import main

    main()
    mock_run.assert_called_once_with(transport="stdio")
