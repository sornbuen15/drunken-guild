# mypy: ignore-errors
"""DG-425: the issue resource and `jira_create_issue`'s `parent` were the two
places left unscoped after DG-422 (PR #122) -- found by that PR's own worker.

`jira://project/{project}/issue/{issue_key}` (``get_issue_details``) read any
issue the shared credential could reach, keyed only by the URI's ``project``,
never compared against the key inside ``issue_key``. `jira_create_issue`'s
optional ``parent`` went straight into the create payload with no comparable
check, so a call scoped to one registry project could attach a new issue to
an Epic or Story belonging to another.

Both now go through the same ``backlog.scope_keys(key, client.project_key)``
helper and refusal DG-422 put on every per-issue tool. An empty ``parent``
is unaffected -- it was never sent before and still is not.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.errors import ValidationError
from jira_mcp import server


def _fake_client(project_key: str = "DG") -> MagicMock:
    fake = MagicMock()
    fake.project_key = project_key
    fake.get_issue = AsyncMock(return_value={"key": "DG-1", "fields": {}})
    fake.create_issue = AsyncMock(return_value={"ok": True, "key": "DG-40"})
    fake.board_warning = AsyncMock(return_value=None)
    return fake


#: Odd shapes beyond a plain foreign key -- same set DG-422's own test file
#: (test_jira_mcp_scope.py) uses for the tools it covered.
ODD_FOREIGN_KEYS = [
    ("lowercase", "beta-5"),
    ("surrounding whitespace", "  BETA-5  "),
    ("lookalike prefix", "DGX-1"),
    ("path characters", "DG-1/../BETA-5"),
    ("query characters", "DG-1?x=BETA-5"),
]


# --- the resource -----------------------------------------------------------


@pytest.mark.asyncio
async def test_resource_foreign_key_is_refused_before_any_request() -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        with pytest.raises(ValidationError) as exc_info:
            await server.get_issue_details("drunken-guild", "BETA-5")

    assert "BETA-5" in str(exc_info.value)
    fake.get_issue.assert_not_called()


@pytest.mark.asyncio
async def test_resource_same_project_key_still_works() -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await server.get_issue_details("drunken-guild", "DG-1")

    result = json.loads(out)
    assert result["key"] == "DG-1"
    fake.get_issue.assert_awaited_once_with("DG-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape, bad_key", ODD_FOREIGN_KEYS, ids=[s for s, _ in ODD_FOREIGN_KEYS]
)
async def test_resource_odd_shaped_keys_are_refused_before_any_request(
    shape: str, bad_key: str
) -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        with pytest.raises(ValidationError):
            await server.get_issue_details("drunken-guild", bad_key)

    fake.get_issue.assert_not_called(), f"resource accepted a {shape} key: {bad_key!r}"


# A reviewer on PR #124 found that every test above uses the one fixture
# project, "DG", so a check that compared against the hardcoded string "DG"
# instead of `client.project_key` would read as correct: every "foreign" key
# in ODD_FOREIGN_KEYS happens to not start with "DG", and the one "same
# project" case happens to be a literal "DG" key. These two pin the project
# key itself as a variable, with a second registered project ("ALPHA") whose
# own key is accepted and whose look of "DG-1" is refused -- a hardcoded "DG"
# constant fails both.
@pytest.mark.asyncio
async def test_resource_accepts_a_key_of_a_different_registered_project() -> None:
    fake = _fake_client("ALPHA")
    fake.get_issue.return_value = {"key": "ALPHA-1", "fields": {}}
    with patch.object(server, "get_client", return_value=fake):
        out = await server.get_issue_details("some-other-project", "ALPHA-1")

    result = json.loads(out)
    assert result["key"] == "ALPHA-1"
    fake.get_issue.assert_awaited_once_with("ALPHA-1")


@pytest.mark.asyncio
async def test_resource_refuses_a_dg_prefixed_key_when_the_project_is_alpha() -> None:
    fake = _fake_client("ALPHA")
    with patch.object(server, "get_client", return_value=fake):
        with pytest.raises(ValidationError) as exc_info:
            await server.get_issue_details("some-other-project", "DG-1")

    assert "DG-1" in str(exc_info.value)
    fake.get_issue.assert_not_called()


# --- jira_create_issue's `parent` -------------------------------------------


@pytest.mark.asyncio
async def test_foreign_parent_is_refused_before_any_request() -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_create_issue(
            "drunken-guild", "summary", "description", parent="BETA-5"
        )

    result = json.loads(out)
    assert result["ok"] is False
    assert "BETA-5" in json.dumps(result)
    fake.create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_same_project_parent_still_works() -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_create_issue(
            "drunken-guild", "summary", "description", parent="DG-9"
        )

    result = json.loads(out)
    assert result.get("ok") is True
    fake.create_issue.assert_awaited_once_with(
        "summary",
        "description",
        "Task",
        parent="DG-9",
        duedate=None,
        start_date=None,
        labels=None,
    )


@pytest.mark.asyncio
async def test_empty_parent_stays_allowed() -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_create_issue(
            "drunken-guild", "summary", "description", parent=""
        )

    result = json.loads(out)
    assert result.get("ok") is True
    fake.create_issue.assert_awaited_once_with(
        "summary",
        "description",
        "Task",
        parent=None,
        duedate=None,
        start_date=None,
        labels=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape, bad_key", ODD_FOREIGN_KEYS, ids=[s for s, _ in ODD_FOREIGN_KEYS]
)
async def test_odd_shaped_parents_are_refused_before_any_request(
    shape: str, bad_key: str
) -> None:
    fake = _fake_client("DG")
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_create_issue(
            "drunken-guild", "summary", "description", parent=bad_key
        )

    result = json.loads(out)
    assert result["ok"] is False, (
        f"jira_create_issue accepted a {shape} parent: {bad_key!r}"
    )
    fake.create_issue.assert_not_called()


# Same pin as the resource's: the fixture project varies, so a hardcoded "DG"
# constant in the parent check fails both of these too.
@pytest.mark.asyncio
async def test_parent_of_a_different_registered_project_is_accepted() -> None:
    fake = _fake_client("ALPHA")
    fake.create_issue.return_value = {"ok": True, "key": "ALPHA-40"}
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_create_issue(
            "some-other-project", "summary", "description", parent="ALPHA-9"
        )

    result = json.loads(out)
    assert result.get("ok") is True
    fake.create_issue.assert_awaited_once_with(
        "summary",
        "description",
        "Task",
        parent="ALPHA-9",
        duedate=None,
        start_date=None,
        labels=None,
    )


@pytest.mark.asyncio
async def test_a_dg_prefixed_parent_is_refused_when_the_project_is_alpha() -> None:
    fake = _fake_client("ALPHA")
    with patch.object(server, "get_client", return_value=fake):
        out = await server.jira_create_issue(
            "some-other-project", "summary", "description", parent="DG-1"
        )

    result = json.loads(out)
    assert result["ok"] is False
    assert "DG-1" in json.dumps(result)
    fake.create_issue.assert_not_called()
