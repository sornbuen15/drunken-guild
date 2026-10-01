# mypy: ignore-errors
"""S8 scope checks across every per-issue tool — DG-422.

PR #113's review found that `jira_edit_issue` and `jira_edit_labels` refuse a
key from another project before building a request
(`backlog.scope_keys(issue_key, client.project_key)`), but `jira_add_comment`
does not — so a call made with one registry project id can write a comment on
any issue the shared credential can reach. This file audits every per-issue
tool in `jira_mcp.server` for the same gap and holds each one to the same
refusal: the key is rejected, and the client is never asked to do anything
with it.

`jira_edit_issue`, `jira_edit_labels`, `jira_get_comments`, `jira_move_to_backlog`
and `jira_move_to_board` already have their own scope tests (their own test
files, from DG-367/DG-368/DG-417/DG-251) and are not repeated here. This file
covers the five that did not: `jira_add_comment`, `jira_assign`,
`jira_transition_issue`, `jira_start_task`, `jira_submit_for_review`.
"""

from __future__ import annotations

import json
from typing import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jira_mcp import server


def _fake_client(project_key: str = "DG") -> MagicMock:
    fake = MagicMock()
    fake.project_key = project_key
    fake.add_comment = AsyncMock(return_value={"ok": True, "id": "1"})
    fake.assign_issue = AsyncMock(return_value={"ok": True})
    fake.assignable_users = AsyncMock(
        return_value=[{"accountId": "a1", "displayName": "Someone"}]
    )
    fake.my_account_id = AsyncMock(return_value="acc-1")
    fake.transition_issue = AsyncMock(return_value={"ok": True})
    return fake


async def _call_add_comment(key: str) -> str:
    return await server.jira_add_comment("drunken-guild", key, "a comment")


async def _call_assign(key: str) -> str:
    return await server.jira_assign("drunken-guild", key, "me")


async def _call_transition(key: str) -> str:
    return await server.jira_transition_issue("drunken-guild", key, "Done")


async def _call_start_task(key: str) -> str:
    return await server.jira_start_task("drunken-guild", key)


async def _call_submit_for_review(key: str) -> str:
    return await server.jira_submit_for_review(
        "drunken-guild", key, "http://example/pr/1", "src/jira_mcp/server.py"
    )


def _assert_add_comment_called(fake: MagicMock) -> None:
    fake.add_comment.assert_awaited_once_with("DG-1", "a comment")


def _assert_assign_called(fake: MagicMock) -> None:
    fake.assign_issue.assert_awaited_once_with("DG-1", "acc-1")


def _assert_transition_called(fake: MagicMock) -> None:
    fake.transition_issue.assert_awaited_once_with("DG-1", "Done")


def _assert_start_task_called(fake: MagicMock) -> None:
    fake.transition_issue.assert_awaited_once_with("DG-1", "In Progress")


def _assert_submit_for_review_called(fake: MagicMock) -> None:
    fake.transition_issue.assert_awaited_once_with("DG-1", "In Review")
    fake.add_comment.assert_awaited_once()


#: (tool name, the call, the client attrs that must stay untouched on refusal,
#: an assertion that the right-project call actually reached the client)
Call = Callable[[str], Awaitable[str]]
Assert = Callable[[MagicMock], None]

TOOLS: list[tuple[str, Call, list[str], Assert]] = [
    (
        "jira_add_comment",
        _call_add_comment,
        ["add_comment"],
        _assert_add_comment_called,
    ),
    (
        "jira_assign",
        _call_assign,
        ["assign_issue", "assignable_users", "my_account_id"],
        _assert_assign_called,
    ),
    (
        "jira_transition_issue",
        _call_transition,
        ["transition_issue"],
        _assert_transition_called,
    ),
    (
        "jira_start_task",
        _call_start_task,
        ["transition_issue"],
        _assert_start_task_called,
    ),
    (
        "jira_submit_for_review",
        _call_submit_for_review,
        ["transition_issue", "add_comment"],
        _assert_submit_for_review_called,
    ),
]

TOOL_IDS = [name for name, *_ in TOOLS]


@pytest.mark.asyncio
@pytest.mark.parametrize("name, call, untouched, _assert", TOOLS, ids=TOOL_IDS)
async def test_a_key_from_another_project_is_refused_before_any_request(
    name: str, call: Call, untouched: list[str], _assert: Assert
) -> None:
    """The finding, generalised: a foreign key must not reach the client."""
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await call("BETA-5")

    result = json.loads(out)
    assert result["ok"] is False
    assert "BETA-5" in json.dumps(result)
    for attr in untouched:
        getattr(fake, attr).assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name, call, untouched, assert_called", TOOLS, ids=TOOL_IDS)
async def test_a_key_of_the_right_project_still_works(
    name: str, call: Call, untouched: list[str], assert_called: Assert
) -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await call("DG-1")

    result = json.loads(out)
    assert result.get("ok", True) is not False, (
        f"{name} refused a key of its own project"
    )
    assert_called(fake)


#: Odd shapes the scope helper must still refuse, beyond a plain foreign key:
#: lowercase, surrounding whitespace, a lookalike prefix (a different project
#: key that merely starts with this project's), and path/query characters that
#: might otherwise smuggle a second key past a naive check.
ODD_FOREIGN_KEYS = [
    ("lowercase", "beta-5"),
    ("surrounding whitespace", "  BETA-5  "),
    ("lookalike prefix", "DGX-1"),
    ("path characters", "DG-1/../BETA-5"),
    ("query characters", "DG-1?x=BETA-5"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name, call, untouched, _assert", TOOLS, ids=TOOL_IDS)
@pytest.mark.parametrize(
    "shape, bad_key", ODD_FOREIGN_KEYS, ids=[s for s, _ in ODD_FOREIGN_KEYS]
)
async def test_odd_shaped_keys_are_refused_before_any_request(
    name: str,
    call: Call,
    untouched: list[str],
    _assert: Assert,
    shape: str,
    bad_key: str,
) -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await call(bad_key)

    result = json.loads(out)
    assert result["ok"] is False, f"{name} accepted a {shape} key: {bad_key!r}"
    for attr in untouched:
        getattr(fake, attr).assert_not_called()
