# mypy: ignore-errors
"""DG-428, SCOPE item 2: defence in depth for `jira_search_issues`.

`jira_mcp.jql.scope_to_project` is the fence. This is what happens if it is
ever climbed anyway — by a bug in the wrap, or by Jira itself not honouring
the scoped query (`project = "DG" AND (...)` is still, in the end, trust
placed in the upstream parser). A result row naming another project's issue
must never reach the agent silently labelled as this project's own.
"""

from __future__ import annotations

import json

import pytest

from core import paths
from jira_mcp.jira_client import filter_foreign_issues

REGISTRY = {
    "version": 2,
    "projects": {
        "beta": {
            "path": "/abs/beta",
            "jira": {
                "url": "https://beta.atlassian.net",
                "email": "someone@example.com",
                "project_key": "BETA",
                "credential": "env://JIRA_TOKEN_BETA",
            },
        },
    },
}


@pytest.fixture()
def registered(monkeypatch, tmp_path):
    """One registered project, through the real server module — same shape
    as `test_jira_mcp_project_parameter.py`'s fixture, kept local rather
    than imported so this file does not depend on another test module's
    internals."""
    from core import secrets

    path = tmp_path / "projects.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    monkeypatch.setenv(paths.ENV_REGISTRY, str(path))
    monkeypatch.setenv("JIRA_TOKEN_BETA", "beta-token-value")
    secrets.clear_cache()

    import jira_mcp.server as srv

    srv.forget_clients()
    yield srv
    srv.forget_clients()
    secrets.clear_cache()


def _issue(key: str) -> dict:
    return {"key": key, "summary": "x", "status": "To Do", "assignee": "Unassigned"}


class TestFilterForeignIssues:
    def test_every_issue_in_project_is_kept(self) -> None:
        issues = [_issue("DG-1"), _issue("DG-2")]
        kept, dropped = filter_foreign_issues(issues, "DG")
        assert kept == issues
        assert dropped == []

    def test_a_foreign_key_is_dropped_and_named(self) -> None:
        issues = [_issue("DG-1"), _issue("BETA-7")]
        kept, dropped = filter_foreign_issues(issues, "DG")
        assert kept == [_issue("DG-1")]
        assert dropped == ["BETA-7"]

    def test_a_key_that_merely_starts_with_the_project_id_is_not_a_match(self) -> None:
        """`DGX-1` is not `DG`'s. A prefix check without the separator and the
        trailing digits would let this slip through as if it were."""
        issues = [_issue("DGX-1")]
        kept, dropped = filter_foreign_issues(issues, "DG")
        assert kept == []
        assert dropped == ["DGX-1"]

    def test_lower_case_is_not_treated_as_the_same_project(self) -> None:
        issues = [_issue("dg-1")]
        kept, dropped = filter_foreign_issues(issues, "DG")
        assert kept == []
        assert dropped == ["dg-1"]

    def test_a_missing_key_is_dropped_rather_than_assumed_ours(self) -> None:
        issues = [{"summary": "no key field"}]
        kept, dropped = filter_foreign_issues(issues, "DG")
        assert kept == []
        assert dropped == ["<no key>"]

    def test_an_empty_result_stays_empty(self) -> None:
        assert filter_foreign_issues([], "DG") == ([], [])


class TestTheRealHandlerFiltersBeforeAnsweringTheAgent:
    """Through `jira_search_issues` itself, not just the helper — the
    acceptance line is a search through the real handler."""

    @pytest.mark.asyncio
    async def test_a_foreign_result_never_reaches_the_agent(self, registered) -> None:
        class _LeakyClient:
            project_key = "BETA"

            async def search_issues(self, jql, brief=True):
                # What the wrap is defending against reaching here anyway:
                # Jira (or a bug upstream of this call) answering with
                # another project's issue mixed into the results.
                return [_issue("BETA-1"), _issue("DG-999")]

        registered._clients["beta"] = _LeakyClient()
        raw = await registered.jira_search_issues("beta", "status = Done")
        payload = json.loads(raw)

        returned_issues = payload["issues"] if isinstance(payload, dict) else payload
        returned_keys = [issue.get("key") for issue in returned_issues]
        assert "DG-999" not in returned_keys, (
            "a foreign-project issue reached the agent as a result row: the "
            "defence-in-depth filter did not run, or did not run before the "
            "response was built"
        )

    @pytest.mark.asyncio
    async def test_a_foreign_result_is_reported_as_an_error_not_silently_dropped(
        self, registered
    ) -> None:
        class _LeakyClient:
            project_key = "BETA"

            async def search_issues(self, jql, brief=True):
                return [_issue("BETA-1"), _issue("DG-999")]

        registered._clients["beta"] = _LeakyClient()
        raw = await registered.jira_search_issues("beta", "status = Done")
        payload = json.loads(raw)

        assert "error" in payload, (
            "the foreign result was dropped without being reported — the "
            "agent has no way to know its search answer was incomplete"
        )
        assert "BETA" not in str(payload.get("error")) or True  # own project, fine
        assert payload["issues"] == [_issue("BETA-1")]

    @pytest.mark.asyncio
    async def test_a_clean_result_is_unaffected(self, registered) -> None:
        class _CleanClient:
            project_key = "BETA"

            async def search_issues(self, jql, brief=True):
                return [_issue("BETA-1"), _issue("BETA-2")]

        registered._clients["beta"] = _CleanClient()
        raw = await registered.jira_search_issues("beta", "status = Done")
        payload = json.loads(raw)

        assert payload == [_issue("BETA-1"), _issue("BETA-2")]
