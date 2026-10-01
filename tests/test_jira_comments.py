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

from core.errors import ValidationError
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
    fake.project_key = "DG"
    fake.get_comments = AsyncMock(return_value=[])
    with patch.object(server, "get_client", return_value=fake):
        await server.jira_get_comments("drunken-guild", "DG-417", limit=3)

    fake.get_comments.assert_awaited_once_with("DG-417", 3)


# --- DG-417 review: S8 scoping -------------------------------------------
#
# jira_edit_issue and jira_edit_labels refuse a key from another project
# before building a request (DG-225 S8). jira_get_comments reads the issue
# key straight into a URL the same way those tools' payloads did, so it needs
# the same refusal.


@pytest.mark.asyncio
async def test_the_tool_refuses_a_key_from_another_project() -> None:
    from jira_mcp import server

    fake = MagicMock()
    fake.project_key = "DG"
    fake.get_comments = AsyncMock()
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_get_comments("drunken-guild", "BETA-1")

    assert "BETA-1" in out
    fake.get_comments.assert_not_called()


# --- DG-417 review: bounding `limit` --------------------------------------
#
# No upstream cap exists to lean on here (comments.py's own docstring says
# why); the bound is this tool's own, enforced the same way scope_keys bounds
# MAX_ISSUES -- a ValidationError with a remediation, not a bare exception.


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_a_limit_of_zero_is_refused(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    with pytest.raises(ValidationError):
        await client.get_comments("DG-417", limit=0)
    mock_request.assert_not_called()


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_a_limit_above_the_cap_is_refused(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    with pytest.raises(ValidationError) as caught:
        await client.get_comments("DG-417", limit=21)
    assert "20" in str(caught.value)
    mock_request.assert_not_called()


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_a_limit_at_the_cap_is_accepted(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    mock_request.return_value = {"comments": []}
    assert await client.get_comments("DG-417", limit=20) == []


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_a_non_numeric_limit_is_refused(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    with pytest.raises(ValidationError):
        await client.get_comments("DG-417", limit="five")
    mock_request.assert_not_called()


# --- DG-417 second review: bool and non-integral float ---------------------
#
# int(limit) alone cannot be trusted with these: int(True) == 1 silently
# accepts a bool as if it were a count, and int(3.7) == 3 silently truncates
# a fraction rather than refusing it. Both must be refused explicitly, not
# merely coerced.


def test_a_limit_of_true_is_refused() -> None:
    from jira_mcp import comments

    with pytest.raises(ValidationError):
        comments.validate_limit(True)


def test_a_limit_of_false_is_refused() -> None:
    from jira_mcp import comments

    with pytest.raises(ValidationError):
        comments.validate_limit(False)


def test_a_fractional_float_limit_is_refused() -> None:
    from jira_mcp import comments

    with pytest.raises(ValidationError):
        comments.validate_limit(3.7)


def test_an_integral_float_limit_is_accepted() -> None:
    """3.0 names a whole number exactly; it is accepted, as 3."""
    from jira_mcp import comments

    assert comments.validate_limit(3.0) == 3


# --- DG-417 review: a comment with nothing in its body --------------------


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_a_missing_body_key_reads_as_an_empty_string(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    mock_request.return_value = {
        "comments": [{"author": {"displayName": "Someone"}, "created": "2026-10-01"}]
    }

    comments = await client.get_comments("DG-417")

    assert comments == [{"author": "Someone", "created": "2026-10-01", "body": ""}]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_an_empty_adf_doc_reads_as_an_empty_string(
    mock_request: AsyncMock, client: JiraClient
) -> None:
    mock_request.return_value = {
        "comments": [
            {
                "author": {"displayName": "Someone"},
                "created": "2026-10-01",
                "body": {"type": "doc", "version": 1, "content": []},
            }
        ]
    }

    comments = await client.get_comments("DG-417")

    assert comments == [{"author": "Someone", "created": "2026-10-01", "body": ""}]
