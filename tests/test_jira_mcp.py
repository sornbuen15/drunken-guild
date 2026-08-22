# mypy: ignore-errors
import json
from unittest.mock import AsyncMock, patch

import pytest

from jira_mcp.jira_client import JiraClient
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


# --- DG-235: the server must not die before it can explain itself ----------


def test_startup_without_project_does_not_kill_the_server() -> None:
    """A missing --project must not be an argparse exit.

    `--project` was declared required=True, so launching the server without
    it exited with code 2 before the MCP handshake — the host saw a process
    that vanished, with nothing to read. Checkpoint principle 8: anything
    that can fail must fail inside a tool call.
    """
    from jira_mcp.server import parse_project_arg

    assert parse_project_arg([]) is None
    assert parse_project_arg(["--project", "dg"]) == "dg"


def test_tool_without_a_context_explains_the_fix() -> None:
    """The failure has to arrive as words the agent can act on."""
    import jira_mcp.server as srv
    from core.errors import DrunkenError

    original = srv.ctx
    srv.ctx = None
    srv.jira = None
    try:
        with pytest.raises(DrunkenError) as excinfo:
            srv.get_client()
    finally:
        srv.ctx = original

    err = excinfo.value
    assert err.remediation, "an error with no next step leaves the agent stuck"
    assert "--project" in err.remediation


# --- DG-234: a ticket with nowhere to appear ------------------------------
#
# TWA (39 issues) and ISAC (131) are business-type Jira projects. They cannot
# have an agile board at all, so work filed there succeeds, returns a key,
# and is then invisible. Nothing errors -- which is exactly the silent
# failure mode that produced §1.1 and DG-235.


class _FakeClient(JiraClient):
    """JiraClient with only the board lookup stubbed.

    Deliberately does not call super().__init__: that wants a real
    ProjectContext with resolved credentials, and none of it is involved in
    the behaviour under test.
    """

    def __init__(self, boards, fail: bool = False) -> None:
        self.base_url = "https://x.atlassian.net"
        self.email = "e@x"
        self.token = "t"  # noqa: S105
        self.project_key = "TWA"
        # DG-251 replaced the two warning-specific caches with one board
        # profile; the warning is now derived from it. What this class stubs,
        # and what the tests below assert, are unchanged.
        self._profile = None
        self._boards = boards
        self._fail = fail
        self.calls = 0

    async def _fetch_boards(self):
        self.calls += 1
        if self._fail:
            raise RuntimeError("agile API unreachable")
        return self._boards

    async def _probe_backlog(self, board_id):
        """Stubbed out: the warning does not depend on it, and a real probe
        here would reach the network from a unit test."""
        return None


@pytest.mark.asyncio
async def test_warns_when_the_project_has_no_board() -> None:
    client = _FakeClient(boards=[])
    warning = await client.board_warning()

    assert warning is not None
    assert "TWA" in warning
    assert "board" in warning.lower()


@pytest.mark.asyncio
async def test_silent_when_a_board_exists() -> None:
    """Zero added tokens on the healthy path."""
    client = _FakeClient(boards=[{"id": 72, "name": "Drunken-Guild (DG)"}])
    assert await client.board_warning() is None


@pytest.mark.asyncio
async def test_looks_up_once_and_remembers() -> None:
    client = _FakeClient(boards=[])
    await client.board_warning()
    await client.board_warning()
    await client.board_warning()
    assert client.calls == 1


@pytest.mark.asyncio
async def test_an_advisory_check_never_breaks_the_real_work() -> None:
    """If the agile API is unavailable, say nothing and carry on.

    This check exists to add a warning. Letting it fail a create would make
    the cure worse than the disease.
    """
    client = _FakeClient(boards=None, fail=True)
    assert await client.board_warning() is None


@pytest.mark.asyncio
@patch("jira_mcp.server.get_client", autospec=True)
async def test_create_issue_carries_the_warning(mock_get_client: AsyncMock) -> None:
    from jira_mcp.server import jira_create_issue

    mock_client = AsyncMock()
    mock_client.create_issue.return_value = {"ok": True, "key": "TWA-40"}
    mock_client.board_warning.return_value = "TWA has no agile board"
    mock_get_client.return_value = mock_client

    result = await jira_create_issue("summary", "description")

    assert "TWA-40" in result
    assert "no agile board" in result


@pytest.mark.asyncio
@patch("jira_mcp.server.get_client", autospec=True)
async def test_create_issue_is_unchanged_when_healthy(
    mock_get_client: AsyncMock,
) -> None:
    from jira_mcp.server import jira_create_issue

    mock_client = AsyncMock()
    mock_client.create_issue.return_value = {"ok": True, "key": "DG-40"}
    mock_client.board_warning.return_value = None
    mock_get_client.return_value = mock_client

    result = await jira_create_issue("summary", "description")

    assert json.loads(result) == {"ok": True, "key": "DG-40"}
