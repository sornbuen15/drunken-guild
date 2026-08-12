# mypy: ignore-errors
import json
from unittest.mock import AsyncMock, patch

import pytest

from jira_mcp.server import jira_start_task, jira_submit_for_review


@pytest.mark.asyncio
@patch("jira_mcp.server.get_client", autospec=True)
async def test_jira_start_task(mock_get_client: AsyncMock) -> None:
    mock_client = AsyncMock()
    mock_get_client.return_value = mock_client

    result_json = await jira_start_task("DAGY-29")
    result = json.loads(result_json)

    mock_client.transition_issue.assert_called_once_with("DAGY-29", "In Progress")
    assert result["status"] == "In Progress"
    assert "git checkout -b feature/DAGY-29" in result["instruction"]


@pytest.mark.asyncio
@patch("jira_mcp.server.get_client", autospec=True)
async def test_jira_submit_for_review(mock_get_client: AsyncMock) -> None:
    mock_client = AsyncMock()
    mock_get_client.return_value = mock_client

    result_json = await jira_submit_for_review(
        "DAGY-29", "http://github.com/pr/1", "src/server.py"
    )
    result = json.loads(result_json)

    mock_client.transition_issue.assert_called_once_with("DAGY-29", "In Review")
    mock_client.add_comment.assert_called_once()
    assert result["status"] == "In Review"


# --- DT-235: the server must not die before it can explain itself ----------


def test_startup_without_project_does_not_kill_the_server() -> None:
    """A missing --project must not be an argparse exit.

    `--project` was declared required=True, so launching the server without
    it exited with code 2 before the MCP handshake — the host saw a process
    that vanished, with nothing to read. Checkpoint principle 8: anything
    that can fail must fail inside a tool call.
    """
    from jira_mcp.server import parse_project_arg

    assert parse_project_arg([]) is None
    assert parse_project_arg(["--project", "dt"]) == "dt"


def test_tool_without_a_context_explains_the_fix() -> None:
    """The failure has to arrive as words the agent can act on."""
    import jira_mcp.server as srv
    from core.errors import DrunkenError

    original = srv.ctx
    srv.ctx = None
    srv.jira = None
    try:
        with pytest.raises(DrunkenError) as excinfo:
            srv.get_client()
    finally:
        srv.ctx = original

    err = excinfo.value
    assert err.remediation, "an error with no next step leaves the agent stuck"
    assert "--project" in err.remediation
