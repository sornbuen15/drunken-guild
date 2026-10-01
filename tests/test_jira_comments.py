# mypy: ignore-errors
"""Reading comments back — DG-417.

`jira_search_issues` with `detail=full` returns the description but no
comments, so a correction made as a comment (DG-392, DG-407, DG-408) was
invisible to the agent that builds the ticket, and so was anything the Boss
typed straight into Jira. `jira_get_comments` is the first way to read one
back; `jira_add_comment` was already the way to write one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jira_mcp.jira_client import JiraClient


def _adf_paragraph(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


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
async def test_a_comment_added_is_the_comment_read_back(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    """The acceptance line, literally: post one, then read it back."""
    mock_request.side_effect = [
        {"id": "9001"},
        {
            "comments": [
                {
                    "id": "9001",
                    "author": {"displayName": "R. Jakkawan"},
                    "created": "2026-10-01T12:00:00.000+0000",
                    "body": _adf_paragraph("Fixed in DG-407."),
                }
            ],
            "total": 1,
        },
    ]

    posted = await client.add_comment("DG-417", "Fixed in DG-407.")
    comments = await client.get_comments("DG-417", limit=5)

    assert posted == {"ok": True, "id": "9001"}
    assert comments == [
        {
            "author": "R. Jakkawan",
            "created": "2026-10-01T12:00:00.000+0000",
            "body": "Fixed in DG-407.",
        }
    ]

    url = mock_request.call_args.args[0]
    assert url == (
        "https://example.atlassian.net/rest/api/3/issue/DG-417/comment"
        "?maxResults=5&orderBy=-created"
    )


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_newest_first_from_jira_comes_back_oldest_first(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    """Jira answers newest-first; the reader wants the conversation in order."""
    mock_request.return_value = {
        "comments": [
            {
                "author": {"displayName": "Newest"},
                "created": "2026-10-02T00:00:00.000+0000",
                "body": _adf_paragraph("second"),
            },
            {
                "author": {"displayName": "Oldest"},
                "created": "2026-10-01T00:00:00.000+0000",
                "body": _adf_paragraph("first"),
            },
        ]
    }

    comments = await client.get_comments("DG-417", limit=5)

    assert [c["author"] for c in comments] == ["Oldest", "Newest"]
    assert [c["body"] for c in comments] == ["first", "second"]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_no_comments_is_an_empty_list(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    mock_request.return_value = {"comments": []}

    assert await client.get_comments("DG-417") == []


@pytest.mark.asyncio
async def test_the_tool_passes_the_limit_through() -> None:
    from jira_mcp import server

    fake = MagicMock()
    fake.get_comments = AsyncMock(return_value=[])
    with patch.object(server, "get_client", return_value=fake):
        await server.jira_get_comments("drunken-guild", "DG-417", limit=3)

    fake.get_comments.assert_awaited_once_with("DG-417", 3)
