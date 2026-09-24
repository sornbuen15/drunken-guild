# mypy: ignore-errors
"""Changing labels after creation — DG-368.

CLAUDE.md requires a ticket an agent is working to carry `agent:<name>`, and
DG-293 chose a label so Assignee could stay the accountable human. Until now no
tool could add one: `jira_create_issue` accepted labels and nothing else touched
them, so every `agent:` label was set at creation or by hand in the web UI.

The shape of the fix matters more than its existence. Jira's issue edit accepts
the whole label set (`fields.labels`) or a list of operations
(`update.labels: [{"add": ...}, {"remove": ...}]`). The first is a
read-modify-write done by the caller: two agents doing it at once each write the
set they read, and the second silently drops the first one's label. The second
is applied by Jira, one operation at a time, against whatever the set is when it
arrives. That is the only form this tool sends.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.errors import ValidationError
from jira_mcp import labels
from jira_mcp.jira_client import JiraClient


class TestThePayloadIsOperationsNeverASet:
    def test_add_and_remove_become_separate_operations(self) -> None:
        payload = labels.update_payload("agent:claude", "medium")

        assert payload == {
            "update": {"labels": [{"add": "agent:claude"}, {"remove": "medium"}]}
        }

    def test_the_whole_set_is_never_sent(self) -> None:
        """`fields.labels` replaces; its presence would reintroduce the race."""
        payload = labels.update_payload("a,b", "")

        assert "fields" not in payload

    def test_several_labels_split_on_commas_and_spaces(self) -> None:
        payload = labels.update_payload("agent:claude, req:REQ-004  high", "")

        assert payload["update"]["labels"] == [
            {"add": "agent:claude"},
            {"add": "req:REQ-004"},
            {"add": "high"},
        ]

    def test_a_label_repeated_in_one_call_is_sent_once(self) -> None:
        payload = labels.update_payload("high,high", "")

        assert payload["update"]["labels"] == [{"add": "high"}]


class TestRefusals:
    def test_nothing_to_do_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            labels.update_payload("", "  ")

    def test_adding_and_removing_the_same_label_is_refused(self) -> None:
        """The outcome would depend on the order Jira applies them in."""
        with pytest.raises(ValidationError) as caught:
            labels.update_payload("high", "medium, high")

        assert "high" in str(caught.value)


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
async def test_the_client_puts_the_operations_to_the_issue(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    payload = labels.update_payload("agent:claude", "")

    result = await client.edit_labels("DG-368", payload)

    url = mock_request.call_args.args[0]
    assert url == "https://example.atlassian.net/rest/api/3/issue/DG-368"
    assert mock_request.call_args.kwargs["method"] == "PUT"
    assert mock_request.call_args.kwargs["payload"] == payload
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_the_tool_refuses_a_key_from_another_project() -> None:
    """S8 (DG-225): the issue endpoint accepts any key; the scope is ours."""
    from jira_mcp import server

    fake = MagicMock()
    fake.project_key = "DG"
    fake.edit_labels = AsyncMock()
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_edit_labels("drunken-guild", "BETA-1", add="high")

    assert "BETA-1" in out
    fake.edit_labels.assert_not_called()


@pytest.mark.asyncio
async def test_the_tool_sends_one_edit_for_one_key() -> None:
    from jira_mcp import server

    fake = MagicMock()
    fake.project_key = "DG"
    fake.edit_labels = AsyncMock(return_value={"ok": True})
    with patch.object(server, "get_client", return_value=fake):
        await server.jira_edit_labels(
            "drunken-guild", "dg-368", add="agent:claude", remove=""
        )

    fake.edit_labels.assert_awaited_once_with(
        "DG-368", {"update": {"labels": [{"add": "agent:claude"}]}}
    )
