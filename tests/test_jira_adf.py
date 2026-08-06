# mypy: ignore-errors
"""Regression tests for Atlassian Document Format (ADF) paragraph splitting.

Jira's v3 API takes rich text as ADF, so multi-line prose has to be split into
one paragraph node per line before it is sent. `JiraClient` did that with
``text.split("\\n")`` — which in Python source is the two characters backslash
and ``n``, not a line break. The behaviour was therefore inverted: genuine
multi-line text collapsed into a single paragraph, while text that happened to
contain a literal backslash-n got split apart.

These tests pin the intended contract: real newlines split, and a literal
backslash-n is just text.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from jira_mcp.jira_client import JiraClient

# Two characters: backslash, n. Written this way so the intent survives anyone
# reformatting the file.
LITERAL_BACKSLASH_N = chr(92) + "n"


def _paragraph_texts(adf: dict[str, Any]) -> list[str]:
    """Flatten an ADF doc node down to the text of each paragraph."""
    texts = []
    for node in adf["content"]:
        assert node["type"] == "paragraph"
        texts.append("".join(part["text"] for part in node["content"]))
    return texts


@pytest.fixture  # type: ignore[misc]
def client() -> JiraClient:
    with patch("jira_mcp.jira_client.get_jira_config", autospec=True) as cfg:
        cfg.return_value = {
            "jira_url": "https://example.atlassian.net",
            "jira_email": "someone@example.com",
            "jira_token": "token",
            "project_key": "DT",
        }
        return JiraClient()


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_add_comment_splits_real_newlines(
    make_request: AsyncMock, client: JiraClient
) -> None:
    make_request.return_value = {"id": "1"}

    await client.add_comment("DT-1", "first line\nsecond line\nthird line")

    payload = make_request.call_args.kwargs["payload"]
    assert _paragraph_texts(payload["body"]) == [
        "first line",
        "second line",
        "third line",
    ]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_add_comment_does_not_split_literal_backslash_n(
    make_request: AsyncMock, client: JiraClient
) -> None:
    make_request.return_value = {"id": "1"}

    await client.add_comment("DT-1", f"path is C:{LITERAL_BACKSLASH_N}ame")

    payload = make_request.call_args.kwargs["payload"]
    assert _paragraph_texts(payload["body"]) == [f"path is C:{LITERAL_BACKSLASH_N}ame"]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_create_issue_splits_real_newlines(
    make_request: AsyncMock, client: JiraClient
) -> None:
    make_request.return_value = {"key": "DT-2", "self": "https://example/2"}

    await client.create_issue("summary", "para one\npara two")

    payload = make_request.call_args.kwargs["payload"]
    assert _paragraph_texts(payload["fields"]["description"]) == [
        "para one",
        "para two",
    ]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_blank_lines_are_dropped_not_emitted_as_empty_paragraphs(
    make_request: AsyncMock, client: JiraClient
) -> None:
    """Blank lines are separators, not content — an empty ADF paragraph node
    with an empty text child is rejected by the Jira API."""
    make_request.return_value = {"id": "1"}

    await client.add_comment("DT-1", "first\n\n   \nsecond")

    payload = make_request.call_args.kwargs["payload"]
    assert _paragraph_texts(payload["body"]) == ["first", "second"]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_create_issue_passes_through_prebuilt_adf(
    make_request: AsyncMock, client: JiraClient
) -> None:
    """A caller that already has ADF must not have it re-processed as text."""
    make_request.return_value = {"key": "DT-3", "self": "https://example/3"}
    adf = {
        "version": 1,
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "already adf"}]}
        ],
    }

    await client.create_issue("summary", adf)

    payload = make_request.call_args.kwargs["payload"]
    assert payload["fields"]["description"] == adf
