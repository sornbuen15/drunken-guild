# mypy: ignore-errors
"""Correcting a ticket after it is created — DG-367.

The server could create, comment, assign, transition and move an issue, and
nothing else. A wrong summary or a wrong line in a description stayed wrong from
the agent's side; the only remedy was the Jira web UI. Labels were the first
half of the fix (DG-368, ``jira_edit_labels``); this is the second: summary and
description.

The rule that matters is the one in ACCEPTANCE: updating one field leaves the
others untouched. Jira's edit only changes the fields named in ``fields``, so the
payload must name exactly the ones the caller passed — an empty argument means
"leave it", never "clear it".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.errors import ValidationError
from jira_mcp import edits
from jira_mcp.jira_client import JiraClient


class TestOnlyTheNamedFieldsAreSent:
    def test_a_summary_alone_sends_the_summary_alone(self) -> None:
        payload = edits.fields_payload(summary="Fix & ship", description="")

        assert payload == {"fields": {"summary": "Fix & ship"}}

    def test_a_description_alone_sends_the_description_alone(self) -> None:
        payload = edits.fields_payload(summary="", description="SCOPE\nOne line.")

        assert set(payload["fields"]) == {"description"}
        assert payload["fields"]["description"]["type"] == "doc"

    def test_both_are_sent_together(self) -> None:
        payload = edits.fields_payload(summary="S", description="D")

        assert set(payload["fields"]) == {"summary", "description"}

    def test_labels_are_never_touched_here(self) -> None:
        """Labels go through jira_edit_labels as operations (DG-368)."""
        payload = edits.fields_payload(summary="S", description="D")

        assert "labels" not in payload["fields"]
        assert "update" not in payload

    def test_the_summary_is_sent_as_written(self) -> None:
        """The finding was `&amp;` where `&` was meant: nothing is escaped."""
        payload = edits.fields_payload(summary="  A & B <c>  ", description="")

        assert payload["fields"]["summary"] == "A & B <c>"


class TestRefusals:
    def test_nothing_to_change_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            edits.fields_payload(summary="  ", description="")

    def test_a_summary_on_two_lines_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            edits.fields_payload(summary="one\ntwo", description="")

    def test_a_summary_longer_than_jira_accepts_is_refused(self) -> None:
        with pytest.raises(ValidationError) as caught:
            edits.fields_payload(summary="x" * 256, description="")

        assert "255" in str(caught.value)

    def test_a_summary_at_the_limit_is_accepted(self) -> None:
        payload = edits.fields_payload(summary="x" * 255, description="")

        assert len(payload["fields"]["summary"]) == 255


@pytest.fixture  # type: ignore[misc]
def client() -> JiraClient:
    ctx = MagicMock()
    ctx.require_jira.return_value.url = "https://example.atlassian.net"
    ctx.require_jira.return_value.email = "someone@example.com"
    ctx.require_jira.return_value.token.reveal.return_value = "token"
    ctx.require_jira.return_value.project_key = "DG"
    return JiraClient(ctx)


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_the_client_puts_the_fields_to_the_issue(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    payload = edits.fields_payload(summary="Corrected", description="")

    result = await client.edit_issue("DG-367", payload)

    assert (
        mock_request.call_args.args[0]
        == "https://example.atlassian.net/rest/api/3/issue/DG-367"
    )
    assert mock_request.call_args.kwargs["method"] == "PUT"
    assert mock_request.call_args.kwargs["payload"] == payload
    assert result == {"ok": True, "issue": "DG-367"}


@pytest.mark.asyncio
async def test_the_tool_refuses_a_key_from_another_project() -> None:
    """S8 (DG-225): the issue endpoint accepts any key; the scope is ours."""
    from jira_mcp import server

    fake = MagicMock()
    fake.project_key = "DG"
    fake.edit_issue = AsyncMock()
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_edit_issue("drunken-guild", "BETA-1", summary="S")

    assert "BETA-1" in out
    fake.edit_issue.assert_not_called()


@pytest.mark.asyncio
async def test_the_tool_sends_one_edit_with_only_the_given_field() -> None:
    from jira_mcp import server

    fake = MagicMock()
    fake.project_key = "DG"
    fake.edit_issue = AsyncMock(return_value={"ok": True})
    with patch.object(server, "get_client", return_value=fake):
        await server.jira_edit_issue("drunken-guild", "DG-367", summary="Corrected")

    fake.edit_issue.assert_awaited_once_with(
        "DG-367", {"fields": {"summary": "Corrected"}}
    )
