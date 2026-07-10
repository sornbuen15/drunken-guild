# mypy: ignore-errors
import json

import pytest

from jira_mcp.jira_client import JiraClient
from jira_mcp.server import jira_start_task, jira_submit_for_review


@pytest.mark.asyncio  # type: ignore[misc]
@pytest.mark.e2e  # type: ignore[misc]
async def test_sdlc_e2e_pipeline() -> None:
    client = JiraClient()

    # 1. Create a dummy ticket for E2E testing
    create_res = await client.create_issue(
        summary="[E2E TEST] Full SDLC Pipeline",
        description="Automated E2E test ticket to verify the full SDLC pipeline.",
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

        # 3. Simulate work and submit for review
        pr_link = f"https://github.com/drunken-team/repo/pull/{ticket_key}"
        files = "tests/test_full_system_e2e.py"

        review_result_str = await jira_submit_for_review(ticket_key, pr_link, files)
        review_result = json.loads(review_result_str)

        assert review_result["status"] == "In Review"

        # Verify real status in Jira
        issue_data = await client.get_issue(ticket_key)
        real_status = issue_data.get("fields", {}).get("status", {}).get("name")
        assert real_status == "In Review"

        # 4. Simulate QA Validation / Merging to Done
        # In a real scenario, this would be QA or PR merge triggering the webhook
        await client.transition_issue(ticket_key, "Done")

        issue_data = await client.get_issue(ticket_key)
        real_status = issue_data.get("fields", {}).get("status", {}).get("name")
        assert real_status == "Done"

    finally:
        # Cleanup: transition to Done or a terminal state if possible
        try:
            await client.transition_issue(ticket_key, "Done")
        except Exception:
            pass  # Best effort cleanup
