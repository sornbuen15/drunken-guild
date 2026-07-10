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
