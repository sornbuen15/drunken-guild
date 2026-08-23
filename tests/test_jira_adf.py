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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jira_mcp.jira_client import JiraClient, from_adf, to_adf

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
    ctx = MagicMock()
    ctx.require_jira.return_value.url = "https://example.atlassian.net"
    ctx.require_jira.return_value.email = "someone@example.com"
    ctx.require_jira.return_value.token.reveal.return_value = "token"
    ctx.require_jira.return_value.project_key = "DG"
    return JiraClient(ctx)


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_add_comment_splits_real_newlines(
    make_request: AsyncMock, client: JiraClient
) -> None:
    make_request.return_value = {"id": "1"}

    await client.add_comment("DG-1", "first line\nsecond line\nthird line")

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

    await client.add_comment("DG-1", f"path is C:{LITERAL_BACKSLASH_N}ame")

    payload = make_request.call_args.kwargs["payload"]
    assert _paragraph_texts(payload["body"]) == [f"path is C:{LITERAL_BACKSLASH_N}ame"]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_create_issue_splits_real_newlines(
    make_request: AsyncMock, client: JiraClient
) -> None:
    make_request.return_value = {"key": "DG-2", "self": "https://example/2"}

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

    await client.add_comment("DG-1", "first\n\n   \nsecond")

    payload = make_request.call_args.kwargs["payload"]
    assert _paragraph_texts(payload["body"]) == ["first", "second"]


@pytest.mark.asyncio
@patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
async def test_create_issue_passes_through_prebuilt_adf(
    make_request: AsyncMock, client: JiraClient
) -> None:
    """A caller that already has ADF must not have it re-processed as text."""
    make_request.return_value = {"key": "DG-3", "self": "https://example/3"}
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


class TestTheWriterCanProduceWhatTheReaderAlreadyUnderstands:
    """DG-279. `to_adf` turned every line into a paragraph.

    Headings, bullets and code blocks were impossible to express, so every
    ticket this project files rendered as an undifferentiated wall — including
    the FINDING / SCOPE / ACCEPTANCE headings the `jira-tickets` skill
    mandates, which arrived as ordinary sentences.

    The asymmetry is the tell: `_ADF_BLOCKS` already lists `heading`,
    `codeBlock` and `listItem`, so the reader half of the pair handled shapes
    the writer half could not produce.
    """

    @staticmethod
    def _types(adf: dict[str, Any]) -> list[str]:
        return [node["type"] for node in adf["content"]]

    @pytest.mark.parametrize(
        ("line", "level"), [("# One", 1), ("## Two", 2), ("### Three", 3)]
    )
    def test_a_hash_prefix_becomes_a_heading(self, line: str, level: int) -> None:
        node = to_adf(line)["content"][0]

        assert node["type"] == "heading", (
            f"{line!r} must become a heading, not a paragraph that happens to "
            "start with a hash"
        )
        assert node["attrs"]["level"] == level

    def test_a_hash_without_a_space_is_not_a_heading(self) -> None:
        """`#DG-279` is a reference, not a title. Guarding the boundary because
        ticket bodies are full of them."""
        assert self._types(to_adf("#notaheading")) == ["paragraph"]

    def test_consecutive_dashes_become_one_list(self) -> None:
        adf = to_adf("- first\n- second\n- third")

        assert self._types(adf) == ["bulletList"], (
            "three items are one list, not three — a list per item renders as "
            "three separate bullets with gaps between them"
        )
        assert len(adf["content"][0]["content"]) == 3

    def test_a_star_marks_a_bullet_too(self) -> None:
        assert self._types(to_adf("* only")) == ["bulletList"]

    def test_a_paragraph_after_a_list_closes_it(self) -> None:
        assert self._types(to_adf("- item\nprose")) == ["bulletList", "paragraph"]

    def test_a_fence_becomes_a_code_block(self) -> None:
        adf = to_adf("```\nuv run pytest\n```")

        assert self._types(adf) == ["codeBlock"]
        assert adf["content"][0]["content"][0]["text"] == "uv run pytest"

    def test_markup_inside_a_fence_stays_literal(self) -> None:
        """The case that matters for this repository: ticket bodies quote shell
        and diffs, and `# comment` inside a fence is a comment."""
        adf = to_adf("```\n# not a heading\n- not a bullet\n```")

        assert self._types(adf) == ["codeBlock"]
        assert adf["content"][0]["content"][0]["text"] == (
            "# not a heading\n- not a bullet"
        )

    def test_an_ordinary_line_is_still_a_paragraph(self) -> None:
        """The behaviour everything else depends on, pinned so this change
        cannot quietly widen."""
        assert self._types(to_adf("just prose")) == ["paragraph"]

    @pytest.mark.parametrize(
        "text",
        [
            "# Heading",
            "## Heading",
            "- one\n- two",
            "```\ncode here\n```",
            "plain paragraph",
        ],
    )
    def test_it_round_trips_through_the_reader(self, text: str) -> None:
        """`from_adf` is what an agent reads a ticket back through. If the pair
        does not round-trip, a ticket written with structure is read without
        it, which is the same wall by a longer route."""
        assert from_adf(to_adf(text)) == text
