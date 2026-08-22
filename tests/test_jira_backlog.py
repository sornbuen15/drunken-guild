# mypy: ignore-errors
"""Moving work between the board and the backlog — DG-251.

Until now `jira_mcp` touched `/rest/agile/1.0` in exactly one place: a lookup
asking whether a board exists at all, so `jira_create_issue` could warn on a
business-type project (DG-234). It never read what the board *is* and never
asked what it can *do*.

Two things make that worth fixing rather than guessing at. First, `type` does
not predict capability: surveyed on 2026-08-16, board 68 is `kanban` and has no
backlog, while the three `simple` boards do — and a team-managed project can
switch sprints on without its type changing. Second, and this is what these
tests are mostly about, **the agile endpoints accept any issue key from any
project with no scoping whatsoever.** `POST /rest/agile/1.0/backlog/{id}/issue`
does not care that the server was launched for DG. That is S8 in a new place,
and it gets the same answer: make the scope structural instead of trusting the
caller.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.errors import DrunkenError, ValidationError
from jira_mcp import backlog
from jira_mcp.jira_client import BoardProfile, JiraClient


class TestKeysAreConfinedToTheProject:
    """The guard that stops one project's server moving another's tickets."""

    def test_a_key_from_this_project_is_accepted(self) -> None:
        assert backlog.scope_keys("DG-251", "DG") == ["DG-251"]

    def test_a_key_from_another_project_is_refused(self) -> None:
        """The whole point. Nothing upstream would have stopped this: Jira
        accepts the key, moves the issue, and reports success."""
        with pytest.raises(ValidationError) as caught:
            backlog.scope_keys("ISAC-5", "DG")
        assert "ISAC-5" in str(caught.value)
        assert caught.value.remediation, "an error with no next step is a dead end"

    def test_one_foreign_key_refuses_the_whole_batch(self) -> None:
        """Not "move the valid ones and mention the rest". A partial move is
        the hardest kind to undo, because nothing records which half went."""
        with pytest.raises(ValidationError) as caught:
            backlog.scope_keys("DG-251, ISAC-5, DG-250", "DG")
        assert "ISAC-5" in str(caught.value)

    def test_a_project_key_that_merely_starts_the_same_is_refused(self) -> None:
        """`DGX-1` starts with `DG`. A prefix comparison would let it through,
        and it belongs to a different project entirely."""
        with pytest.raises(ValidationError):
            backlog.scope_keys("DGX-1", "DG")

    def test_case_is_normalised_rather_than_refused(self) -> None:
        """Jira keys are uppercase; a human typing `dg-251` means DG-251."""
        assert backlog.scope_keys("dg-251", "DG") == ["DG-251"]

    def test_keys_may_be_separated_by_commas_or_whitespace(self) -> None:
        assert backlog.scope_keys("DG-1, DG-2  DG-3", "DG") == ["DG-1", "DG-2", "DG-3"]

    def test_something_that_is_not_a_key_at_all_is_refused(self) -> None:
        """Guarding on shape as well as on project: `DG` alone, or a summary
        pasted in by mistake, must not reach the API as if it were a key."""
        for junk in ("DG", "DG-", "-251", "251", "DG-251-x"):
            with pytest.raises(ValidationError):
                backlog.scope_keys(junk, "DG")

    def test_no_keys_at_all_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            backlog.scope_keys("   ", "DG")

    def test_more_than_fifty_is_refused_before_the_call(self) -> None:
        """Jira's own limit. Sending 51 returns a partial result that has to be
        reconciled afterwards; refusing costs nothing and stays reconcilable."""
        keys = ", ".join(f"DG-{n}" for n in range(1, 52))
        with pytest.raises(ValidationError) as caught:
            backlog.scope_keys(keys, "DG")
        assert "50" in str(caught.value)

    def test_exactly_fifty_is_accepted(self) -> None:
        keys = ", ".join(f"DG-{n}" for n in range(1, 51))
        assert len(backlog.scope_keys(keys, "DG")) == 50


class _FakeClient(JiraClient):
    """JiraClient with the two agile lookups stubbed and nothing else.

    Same reasoning as `_FakeClient` in test_jira_mcp: `super().__init__` wants a
    real ProjectContext with resolved credentials, none of which is involved in
    what is under test here.
    """

    def __init__(self, boards, backlog_probe=True) -> None:
        self.base_url = "https://x.atlassian.net"
        self.email = "e@x"
        self.token = "t"  # noqa: S105
        self.project_key = "DG"
        self._profile = None
        self._boards = boards
        self._backlog_probe = backlog_probe
        self.board_calls = 0
        self.probe_calls = 0

    async def _fetch_boards(self):
        self.board_calls += 1
        if isinstance(self._boards, Exception):
            raise self._boards
        return self._boards

    async def _probe_backlog(self, board_id: int):
        self.probe_calls += 1
        if isinstance(self._backlog_probe, Exception):
            raise self._backlog_probe
        return self._backlog_probe


BOARD = [{"id": 72, "name": "DG board", "type": "simple"}]


class TestTheBoardProfile:
    """Capability is probed, never inferred from `type`."""

    @pytest.mark.asyncio
    async def test_a_board_with_a_backlog_reports_one(self) -> None:
        profile = await _FakeClient(BOARD, backlog_probe=True).board_profile()
        assert profile.id == 72
        assert profile.type == "simple"
        assert profile.backlog is True

    @pytest.mark.asyncio
    async def test_a_board_without_a_backlog_reports_none(self) -> None:
        """Board 68 on the live site: type `kanban`, and Jira answers
        `Backlogs are not supported on this board`."""
        kanban = [{"id": 68, "name": "Drunken-Guild", "type": "kanban"}]
        profile = await _FakeClient(kanban, backlog_probe=False).board_profile()
        assert profile.type == "kanban"
        assert profile.backlog is False

    @pytest.mark.asyncio
    async def test_a_project_with_no_board_is_known_rather_than_unknown(self) -> None:
        """A business-type project (TWA, ISAC) confirmed to have no board is a
        different answer from a lookup that failed, and the two must not
        collapse into each other — one is a fact, the other is ignorance."""
        profile = await _FakeClient([]).board_profile()
        assert profile.known is True
        assert profile.id is None

    @pytest.mark.asyncio
    async def test_a_failed_lookup_is_admitted_not_guessed(self) -> None:
        profile = await _FakeClient(
            RuntimeError("agile API unreachable")
        ).board_profile()
        assert profile.known is False
        assert profile.id is None

    @pytest.mark.asyncio
    async def test_a_failed_backlog_probe_still_yields_the_board(self) -> None:
        """The board is real and known even when the second question could not
        be asked. Losing the whole profile over the optional half of it would
        make the cure worse than the disease."""
        client = _FakeClient(BOARD, backlog_probe=RuntimeError("timeout"))
        profile = await client.board_profile()
        assert profile.id == 72
        assert profile.backlog is None

    @pytest.mark.asyncio
    async def test_it_is_looked_up_once_and_remembered(self) -> None:
        """Cached for the life of the process, healthy answer included — same
        shape as board_warning() and the secrets resolver."""
        client = _FakeClient(BOARD)
        for _ in range(3):
            await client.board_profile()
        assert (client.board_calls, client.probe_calls) == (1, 1)

    @pytest.mark.asyncio
    async def test_the_no_board_warning_still_comes_from_the_same_lookup(self) -> None:
        """DG-234's warning is now derived from the profile rather than from a
        second cache. It must not have changed what it says."""
        client = _FakeClient([])
        client.project_key = "TWA"
        warning = await client.board_warning()
        assert warning is not None
        assert "TWA" in warning and "board" in warning.lower()

    @pytest.mark.asyncio
    async def test_a_failed_lookup_still_warns_about_nothing(self) -> None:
        """Advisory only: this exists to add a warning, so it must never turn a
        working create into a failure."""
        client = _FakeClient(RuntimeError("agile API unreachable"))
        assert await client.board_warning() is None


class TestTheProbeItself:
    """`_probe_backlog` is where capability stops being a guess, so it is
    tested against the answers Jira actually gives rather than through a stub.

    The three responses below were all observed live on 2026-08-16 (boards 72
    and 68), which is the only reason the classification can be trusted.
    """

    def _client(self) -> JiraClient:
        client = JiraClient.__new__(JiraClient)
        client.base_url = "https://x.atlassian.net"
        client.email = "e@x"
        client.token = "t"  # noqa: S105
        client.project_key = "DG"
        client._profile = None
        return client

    @pytest.mark.asyncio
    async def test_a_board_that_answers_has_a_backlog(self, monkeypatch) -> None:
        async def ok(*args, **kwargs):
            return {"total": 0, "issues": []}

        monkeypatch.setattr("jira_mcp.jira_client.make_request", ok)
        assert await self._client()._probe_backlog(72) is True

    @pytest.mark.asyncio
    async def test_jiras_own_400_is_read_as_no_backlog(self, monkeypatch) -> None:
        from jira_mcp.jira_client import JiraHTTPError

        async def refuse(*args, **kwargs):
            raise JiraHTTPError(
                400,
                "Jira API Request failed: HTTP Error 400: Bad Request "
                '{"errorMessages":["Backlogs are not supported on this board"]}',
            )

        monkeypatch.setattr("jira_mcp.jira_client.make_request", refuse)
        assert await self._client()._probe_backlog(68) is False

    @pytest.mark.asyncio
    async def test_some_other_400_is_not_read_as_no_backlog(self, monkeypatch) -> None:
        """A 400 saying something else is not evidence about the backlog. The
        status code alone would classify it wrongly, and confidently."""
        from jira_mcp.jira_client import JiraHTTPError

        async def refuse(*args, **kwargs):
            raise JiraHTTPError(
                400, "Jira API Request failed: board id must be a number"
            )

        monkeypatch.setattr("jira_mcp.jira_client.make_request", refuse)
        assert await self._client()._probe_backlog(68) is None

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_unknown_not_absent(self, monkeypatch) -> None:
        async def boom(*args, **kwargs):
            raise RuntimeError("connection reset")

        monkeypatch.setattr("jira_mcp.jira_client.make_request", boom)
        assert await self._client()._probe_backlog(72) is None


class TestTheMoveTools:
    @pytest.mark.asyncio
    async def test_a_board_without_a_backlog_is_refused_with_the_reason(self) -> None:
        from jira_mcp.server import jira_move_to_backlog

        client = AsyncMock()
        client.project_key = "DG"
        client.board_profile.return_value = BoardProfile(
            id=68, name="Drunken-Guild", type="kanban", backlog=False, known=True
        )
        with patch("jira_mcp.server.get_client", return_value=client):
            result = await jira_move_to_backlog("DG-251")

        assert '"ok": false' in result.lower()
        assert "backlog" in result.lower()
        client.move_to_backlog.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_project_with_no_board_is_refused_with_the_reason(self) -> None:
        from jira_mcp.server import jira_move_to_backlog

        client = AsyncMock()
        client.project_key = "DG"
        client.board_profile.return_value = BoardProfile(known=True)
        with patch("jira_mcp.server.get_client", return_value=client):
            result = await jira_move_to_backlog("DG-251")

        assert '"ok": false' in result.lower()
        client.move_to_backlog.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_foreign_key_never_reaches_the_api(self) -> None:
        """The guard runs before the request, not after Jira has already moved
        somebody else's ticket."""
        from jira_mcp.server import jira_move_to_backlog

        client = AsyncMock()
        client.project_key = "DG"
        client.board_profile.return_value = BoardProfile(
            id=72, name="DG board", type="simple", backlog=True, known=True
        )
        with patch("jira_mcp.server.get_client", return_value=client):
            result = await jira_move_to_backlog("ISAC-5")

        assert "ISAC-5" in result
        client.move_to_backlog.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_successful_move_says_what_did_not_change(self) -> None:
        """Backlog membership is not status. An agent reading "moved to
        backlog" must not conclude the ticket is no longer In Progress — that
        would be a second surface disagreeing with the first, which is the
        failure DG-250 spent a session curing."""
        from jira_mcp.server import jira_move_to_backlog

        client = AsyncMock()
        client.project_key = "DG"
        client.board_profile.return_value = BoardProfile(
            id=72, name="DG board", type="simple", backlog=True, known=True
        )
        client.move_to_backlog.return_value = {"ok": True, "moved": ["DG-251"]}
        with patch("jira_mcp.server.get_client", return_value=client):
            result = await jira_move_to_backlog("DG-251")

        assert "DG-251" in result
        assert "status" in result.lower()
        client.move_to_backlog.assert_awaited_once_with(72, ["DG-251"])

    @pytest.mark.asyncio
    async def test_the_way_back_exists_and_is_scoped_the_same(self) -> None:
        """A tool that can only move work out of sight is a one-way door: the
        way back would be a human in the Jira UI."""
        from jira_mcp.server import jira_move_to_board

        client = AsyncMock()
        client.project_key = "DG"
        client.board_profile.return_value = BoardProfile(
            id=72, name="DG board", type="simple", backlog=True, known=True
        )
        client.move_to_board.return_value = {"ok": True, "moved": ["DG-251"]}
        with patch("jira_mcp.server.get_client", return_value=client):
            assert "ISAC-5" in await jira_move_to_board("ISAC-5")
            result = await jira_move_to_board("DG-251")

        client.move_to_board.assert_awaited_once_with(72, ["DG-251"])
        assert "DG-251" in result

    @pytest.mark.asyncio
    async def test_an_unknown_backlog_is_attempted_rather_than_refused(self) -> None:
        """`None` means the probe could not answer. Jira is then the authority,
        and its own 400 is what the agent should read."""
        from jira_mcp.server import jira_move_to_backlog

        client = AsyncMock()
        client.project_key = "DG"
        client.board_profile.return_value = BoardProfile(
            id=72, name="DG board", type="simple", backlog=None, known=True
        )
        client.move_to_backlog.return_value = {"ok": True, "moved": ["DG-251"]}
        with patch("jira_mcp.server.get_client", return_value=client):
            await jira_move_to_backlog("DG-251")

        client.move_to_backlog.assert_awaited_once_with(72, ["DG-251"])


class TestUpstreamErrorsKeepTheirStatus:
    """The probe has to tell "this board has no backlog" (400) apart from "the
    network is down", and the flattened RuntimeError it used to raise could
    only be told apart by matching on the text of a message."""

    def test_an_http_error_carries_its_status_code(self) -> None:
        from jira_mcp.jira_client import JiraHTTPError

        err = JiraHTTPError(400, "Jira API Request failed: 400 Bad Request")
        assert err.status == 400
        assert isinstance(err, RuntimeError), "existing callers catch RuntimeError"

    def test_a_backlog_400_reads_as_no_backlog_rather_than_as_a_failure(self) -> None:
        assert backlog.is_no_backlog_response(
            "Tried to move to backlog on board without backlog"
        )
        assert backlog.is_no_backlog_response(
            "Backlogs are not supported on this board"
        )
        assert not backlog.is_no_backlog_response("Issue does not exist")


class TestTheErrorsCarryANextStep:
    """core/errors.py's rule, applied here: "unknown project 'twa'" only tells
    an agent to give up."""

    def test_every_refusal_names_what_to_do_instead(self) -> None:
        for raw in ("ISAC-5", "not-a-key", ""):
            try:
                backlog.scope_keys(raw, "DG")
            except DrunkenError as exc:
                assert exc.remediation, f"{raw!r} refused without a next step"
            else:
                pytest.fail(f"{raw!r} should have been refused")
