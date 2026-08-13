# mypy: ignore-errors
"""Assigning a Jira issue — the tool that had to exist before Jira could
replace the local board.

The board is retired. Jira is the one coordination surface: the **assignee**
says whose work it is and the **status** says where it is. That only works if
an agent can actually set an assignee, and until now nothing could. `assignee`
came back in search results and no code path ever wrote it, so "assign it to
Antigravity" was a sentence with no tool behind it.

Jira does not accept a name here. `PUT /rest/api/3/issue/{key}/assignee` takes
an `accountId`, so a human-typed name or email has to be resolved first — and
the resolution is the part with sharp edges, because a wrong match silently
assigns the wrong person.
"""

from __future__ import annotations

import pytest

from jira_mcp import assign


class TestResolution:
    def test_me_resolves_through_the_identity_endpoint(self) -> None:
        """`/rest/api/3/myself` is the only endpoint that reliably identifies
        the caller, and it is already how core.context verifies a credential."""
        assert assign.is_self_reference("me") is True
        assert assign.is_self_reference("ME") is True
        assert assign.is_self_reference("@me") is True

    def test_a_real_name_is_not_a_self_reference(self) -> None:
        assert assign.is_self_reference("Jakkawan") is False
        assert assign.is_self_reference("sornbuen15@gmail.com") is False

    def test_unassign_is_expressed_as_none_not_as_a_name(self) -> None:
        """Jira unassigns on an explicit null accountId. Spelling it as the
        string "none" would search for a user called none and find nobody."""
        assert assign.is_unassign("none") is True
        assert assign.is_unassign("unassigned") is True
        assert assign.is_unassign("") is True
        assert assign.is_unassign("Noel") is False


class TestPickingTheRightUser:
    CANDIDATES = [
        {
            "accountId": "a1",
            "displayName": "Jakkawan R",
            "emailAddress": "sornbuen15@gmail.com",
        },
        {
            "accountId": "a2",
            "displayName": "Jak Other",
            "emailAddress": "other@example.com",
        },
    ]

    def test_an_exact_email_match_wins(self) -> None:
        """Email is the only unambiguous identifier a human is likely to type."""
        assert (
            assign.pick_user(self.CANDIDATES, "sornbuen15@gmail.com")["accountId"]
            == "a1"
        )

    def test_an_exact_display_name_match_wins(self) -> None:
        assert assign.pick_user(self.CANDIDATES, "Jak Other")["accountId"] == "a2"

    def test_matching_is_case_insensitive(self) -> None:
        assert assign.pick_user(self.CANDIDATES, "JAKKAWAN R")["accountId"] == "a1"

    def test_an_ambiguous_partial_match_is_refused_rather_than_guessed(self) -> None:
        """ "Jak" matches both. Assigning the wrong person is worse than
        refusing: the work goes quiet on someone else's board and nobody is
        told. So it raises, and the message names every candidate."""
        with pytest.raises(ValueError) as caught:
            assign.pick_user(self.CANDIDATES, "Jak")
        assert "Jakkawan R" in str(caught.value)
        assert "Jak Other" in str(caught.value)

    def test_a_unique_partial_match_is_accepted(self) -> None:
        assert assign.pick_user(self.CANDIDATES, "Other")["accountId"] == "a2"

    def test_no_match_at_all_raises_with_the_candidates_listed(self) -> None:
        """An agent that gets "not found" and nothing else can only give up.
        The error carries who *is* assignable, so it can try again."""
        with pytest.raises(ValueError) as caught:
            assign.pick_user(self.CANDIDATES, "Somebody Else")
        assert "Jakkawan R" in str(caught.value)

    def test_an_empty_candidate_list_says_so_clearly(self) -> None:
        """Distinct from "no match": nobody is assignable on this project at
        all, which is a permissions problem rather than a typo."""
        with pytest.raises(ValueError) as caught:
            assign.pick_user([], "anyone")
        assert "assignable" in str(caught.value).lower()


class TestThePayload:
    def test_assigning_sends_an_account_id(self) -> None:
        assert assign.payload_for("a1") == {"accountId": "a1"}

    def test_unassigning_sends_an_explicit_null(self) -> None:
        """Not an omitted field — Jira reads a missing accountId as "no change",
        so unassigning has to say null out loud."""
        assert assign.payload_for(None) == {"accountId": None}


class TestArrayResponses:
    """`/rest/api/3/user/assignable/search` answers with a JSON **array**.

    The request helper ended `return dict(json.loads(body))`, which force-cast
    every response to a dict. Every caller before this one happened to receive
    an object, so the limitation was invisible until the first array arrived —
    and then it surfaced as `dictionary update sequence element #0 has length
    10; 2 is required`, which says nothing about the actual cause.

    Found by running it against live Jira, not by the suite: the tests above
    cover the resolution logic and never make a request.
    """

    def test_an_object_response_is_returned_as_a_mapping(self) -> None:
        from jira_mcp.jira_client import parse_response

        assert parse_response('{"accountId": "a1"}') == {"accountId": "a1"}

    def test_an_array_response_survives_instead_of_being_cast(self) -> None:
        from jira_mcp.jira_client import parse_response

        parsed = parse_response('[{"accountId": "a1"}, {"accountId": "a2"}]')
        assert isinstance(parsed, list)
        assert [u["accountId"] for u in parsed] == ["a1", "a2"]

    def test_an_empty_body_reads_as_an_empty_mapping(self) -> None:
        """A 204 on a successful PUT has no body. Assigning returns one."""
        from jira_mcp.jira_client import parse_response

        assert parse_response("") == {}
