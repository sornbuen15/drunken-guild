import json

import pytest
from jira_mcp.jira_client import JiraClient
from jira_mcp.server import jira_start_task, jira_submit_for_review


# Mark as e2e so it doesn't run on standard unit test runs unless requested,
# but we will run it explicitly here.
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_jira_mcp_workflow() -> None:
    client = JiraClient()

    # 1. Create a dummy ticket for E2E testing
    create_res = await client.create_issue(
        summary="[E2E TEST] Jira MCP Integration Test",
        description="Automated E2E test ticket to verify the FastMCP workflow.",
    )

    assert create_res.get("ok") is True
    ticket_key = create_res.get("key")
    assert ticket_key is not None

    try:
        # 2. Test jira_start_task (MCP Tool)
        start_result_str = await jira_start_task(ticket_key)
        start_result = json.loads(start_result_str)

        assert start_result["status"] == "In Progress"
        assert f"git checkout -b feature/{ticket_key}" in start_result["instruction"]

        # Verify real status in Jira
        issue_data = await client.get_issue(ticket_key)
        real_status = issue_data.get("fields", {}).get("status", {}).get("name")
        assert real_status == "In Progress"

        # 3. Test jira_submit_for_review (MCP Tool)
        pr_link = "https://github.com/drunken-team/repo/pull/test"
        files = "tests/test_jira_e2e.py"

        review_result_str = await jira_submit_for_review(ticket_key, pr_link, files)
        review_result = json.loads(review_result_str)

        assert review_result["status"] == "In Review"

        # Verify real status in Jira
        issue_data = await client.get_issue(ticket_key)
        real_status = issue_data.get("fields", {}).get("status", {}).get("name")
        assert real_status == "In Review"

    finally:
        # Cleanup: transition to Done or a terminal state if possible
        try:
            await client.transition_issue(ticket_key, "Done")
        except Exception:
            pass  # Best effort cleanup
