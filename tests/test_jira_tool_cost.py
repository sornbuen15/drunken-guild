# mypy: ignore-errors
"""DG-255. What the Jira tools return, and what it costs to return it.

Named "tool_cost" rather than anything containing "token", which .gitignore
excludes as a credential-hygiene rule. That rule silently swallowed the first
version of this file: `git add -A` skipped it, the commit succeeded, pre-commit
passed, and the local suite stayed green because the file was still on disk --
so a PR claiming 21 new tests shipped with none of them. Fails as success, the
same shape as every other defect in this project's history.

Measured on 2026-08-17, not estimated: a six-issue search cost 5,697 tokens and
95% of that was raw Atlassian Document Format. ``minify_issues`` was named for a
promise it did not keep -- it passed ADF through verbatim, and ADF wraps one
sentence in roughly four times its length.

The other half of the ticket is the write path. ``create_issue`` sent four
fields and stopped, so nothing could set a parent, which is why this project's
Timeline was empty: an Epic with no children has nothing to draw.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jira_mcp import server as jira_server
from jira_mcp.jira_client import JiraClient, from_adf, minify_issues, to_adf


@pytest.fixture  # type: ignore[misc]
def client() -> JiraClient:
    ctx = MagicMock()
    ctx.require_jira.return_value.url = "https://example.atlassian.net"
    ctx.require_jira.return_value.email = "someone@example.com"
    ctx.require_jira.return_value.token.reveal.return_value = "token"
    ctx.require_jira.return_value.project_key = "DG"
    return JiraClient(ctx)


def _issue(key: str, **overrides):
    fields = {
        "summary": "A summary",
        "status": {"name": "To Do"},
        "priority": {"name": "Medium"},
        "assignee": None,
        "description": to_adf("A sentence."),
    }
    fields.update(overrides)
    return {"key": key, "fields": fields}


class TestAdfFlattensToSomethingWorthReading:
    def test_a_round_trip_returns_the_original_lines(self) -> None:
        assert from_adf(to_adf("First line.\nSecond line.")) == (
            "First line.\nSecond line."
        )

    def test_a_bullet_list_renders_as_bullets(self) -> None:
        """The bullet marker and its text must land on one line. An earlier cut
        emitted "- \\none", because the paragraph inside the listItem opened a
        new line of its own."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "one"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        assert from_adf(adf) == "- one"

    def test_an_unknown_node_type_is_walked_not_dropped(self) -> None:
        """ADF gains node types faster than we will notice. Losing a paragraph
        silently is worse than rendering it plainly: an agent reading a
        truncated post-mortem cannot tell that it was truncated."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "someFutureNode",
                    "content": [{"type": "text", "text": "still here"}],
                }
            ],
        }
        assert "still here" in from_adf(adf)

    def test_a_plain_string_passes_through(self) -> None:
        """Callers should not have to know which shape Jira handed them."""
        assert from_adf("already text") == "already text"

    def test_it_is_substantially_smaller_than_the_adf_it_replaces(self) -> None:
        """The claim the ticket rests on, asserted rather than believed."""
        adf = to_adf("\n".join(f"Line number {n}." for n in range(20)))
        assert len(from_adf(adf)) * 3 < len(str(adf))


class TestBriefIsTheDefault:
    def test_brief_omits_the_description(self) -> None:
        """95% of a six-issue search. Anyone who wants a body asks for one
        issue by key, which is one cheap call rather than five expensive ones."""
        [row] = minify_issues([_issue("DG-1")])

        assert "description" not in row
        assert row["key"] == "DG-1"
        assert row["status"] == "To Do"

    def test_brief_omits_priority_because_it_cannot_be_set(self) -> None:
        """Priority is unsettable on a team-managed project, so every DG issue
        reads Medium. A field with one possible value is not information."""
        [row] = minify_issues([_issue("DG-1")])

        assert "priority" not in row

    def test_brief_still_carries_the_parent(self) -> None:
        """Hierarchy is free here and costs a call per issue otherwise, so
        omitting it to save characters would spend tokens."""
        [row] = minify_issues(
            [
                _issue(
                    "DG-1",
                    parent={"key": "DG-100", "fields": {"summary": "The Epic"}},
                )
            ]
        )

        assert row["parent"] == "DG-100"
        assert row["parent_summary"] == "The Epic"

    def test_an_issue_without_a_parent_says_nothing_about_one(self) -> None:
        """Absent, not null. Two null fields per row across a large search is
        exactly the sort of cost this ticket exists to remove."""
        [row] = minify_issues([_issue("DG-1")])

        assert "parent" not in row and "parent_summary" not in row

    def test_full_returns_the_description_as_text_not_adf(self) -> None:
        [row] = minify_issues([_issue("DG-1")], brief=False)

        assert row["description"] == "A sentence."
        assert row["priority"] == "Medium"

    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_brief_does_not_ask_jira_for_the_description(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        """Requesting ADF and discarding it costs nothing in tokens and
        everything in latency on a large board."""
        make_request.return_value = {"issues": []}

        await client.search_issues("project = DG")

        url = make_request.call_args.args[0]
        assert "description" not in url
        assert "parent" in url


class TestCreateIssueCanFinallySetTheFields:
    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_parent_is_sent(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        make_request.return_value = {"key": "DG-2"}

        await client.create_issue("s", "d", parent="DG-100")

        fields = make_request.call_args.kwargs["payload"]["fields"]
        assert fields["parent"] == {"key": "DG-100"}

    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_duedate_and_labels_are_sent(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        make_request.return_value = {"key": "DG-2"}

        await client.create_issue(
            "s", "d", duedate="2026-09-01", labels=["Critical", "security"]
        )

        fields = make_request.call_args.kwargs["payload"]["fields"]
        assert fields["duedate"] == "2026-09-01"
        assert fields["labels"] == ["Critical", "security"]

    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_start_date_uses_the_id_this_instance_reports(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        """Start date is customfield_10015 on this instance and there is no
        reason to expect it anywhere else. A hardcoded id writes nothing on
        somebody else's site, and writes it without complaining."""
        make_request.side_effect = [
            [{"id": "customfield_99999", "name": "Start date"}],
            {"key": "DG-2"},
        ]

        await client.create_issue("s", "d", start_date="2026-08-20")

        fields = make_request.call_args.kwargs["payload"]["fields"]
        assert fields["customfield_99999"] == "2026-08-20"
        assert "customfield_10015" not in fields

    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_an_instance_without_the_field_still_creates_the_issue(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        """Losing an optional date must not lose the ticket."""
        make_request.side_effect = [[], {"key": "DG-2"}]

        result = await client.create_issue("s", "d", start_date="2026-08-20")

        assert result == {"ok": True, "key": "DG-2"}

    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_omitted_fields_are_absent_from_the_payload(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        """Sending null for an unset optional field is how a create starts
        failing on a project that does not have it."""
        make_request.return_value = {"key": "DG-2"}

        await client.create_issue("s", "d")

        fields = make_request.call_args.kwargs["payload"]["fields"]
        assert set(fields) == {"project", "summary", "description", "issuetype"}

    @pytest.mark.asyncio
    @patch("jira_mcp.jira_client.make_request", new_callable=AsyncMock)
    async def test_it_returns_the_key_and_not_the_self_url(
        self, make_request: AsyncMock, client: JiraClient
    ) -> None:
        """The URL is derivable from the key and nobody ever followed it."""
        make_request.return_value = {
            "key": "DG-2",
            "self": "https://example.atlassian.net/rest/api/3/issue/10917",
        }

        assert await client.create_issue("s", "d") == {"ok": True, "key": "DG-2"}


class TestTheTicketRuleWarnsAndNeverRefuses:
    def test_long_and_parentless_warns(self) -> None:
        warning = jira_server._orphan_warning("word " * 400, parent="")

        assert warning is not None and "no parent" in warning

    def test_long_with_a_parent_is_silent(self) -> None:
        """A long ticket with an Epic to hang context on is the right shape.
        It is the combination that signals context copied instead of linked."""
        assert jira_server._orphan_warning("word " * 400, parent="DG-100") is None

    def test_short_and_parentless_is_silent(self) -> None:
        """The project's own older tickets run about 49 words. A warning that
        fires on ordinary work gets ignored, and then so does the real one."""
        assert jira_server._orphan_warning("word " * 20, parent="") is None

    def test_the_warning_says_how_many_words_it_saw(self) -> None:
        """ "Too long" invites an argument; a number invites a decision."""
        assert "400 words" in jira_server._orphan_warning("word " * 400, parent="")
