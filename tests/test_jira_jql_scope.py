# mypy: ignore-errors
"""S8 — `jira_search_issues` passed raw JQL straight through.

`--project` named which project the server was for, and then did nothing to
keep a query inside it. `project = OTHER AND ...` reached whatever the
credential could reach, and the credential reaches DG, TWA and ISAC.

The fix does not try to *validate* JQL. Parsing a query language to decide
whether it is safe is the same losing game as matching shell commands by
prefix (see `core/permission_rules.py`, which says so about itself). Instead
the query is **wrapped**: whatever the caller wrote becomes a sub-clause of
`project = <KEY> AND (...)`, which constrains the result regardless of what
it says. There is nothing to get right about the caller's syntax.

The one piece of parsing that cannot be avoided is ORDER BY, because it has to
stay outside the parentheses or the query is not valid JQL.
"""

from __future__ import annotations

import pytest

from jira_mcp.jql import scope_to_project


class TestScoping:
    def test_a_plain_query_is_wrapped(self) -> None:
        assert (
            scope_to_project("status = Done", "DG")
            == 'project = "DG" AND (status = Done)'
        )

    def test_a_query_naming_another_project_cannot_escape(self) -> None:
        """The finding. The wrapped form is `project = "DG" AND (project =
        ISAC ...)`, which matches nothing — the caller is constrained by
        conjunction rather than by us understanding their query."""
        scoped = scope_to_project("project = ISAC AND status = Done", "DG")
        assert scoped.startswith('project = "DG" AND (')
        assert "ISAC" in scoped, "the clause is kept, not silently rewritten"

    def test_an_empty_query_becomes_the_project_alone(self) -> None:
        assert scope_to_project("", "DG") == 'project = "DG"'
        assert scope_to_project("   ", "DG") == 'project = "DG"'

    def test_an_or_clause_cannot_widen_the_scope(self) -> None:
        """Without the parentheses, `project = "DG" AND a OR b` binds as
        `(project = DG AND a) OR b` and the OR escapes the scope entirely.
        This is the reason the wrap is parenthesised and not concatenated."""
        scoped = scope_to_project("status = Done OR project = ISAC", "DG")
        assert scoped == 'project = "DG" AND (status = Done OR project = ISAC)'


class TestOrderBy:
    def test_order_by_is_lifted_outside_the_parentheses(self) -> None:
        """`project = "DG" AND (x ORDER BY y)` is not valid JQL. The sort has
        to be hoisted or every ordered query breaks."""
        assert (
            scope_to_project("status = Done ORDER BY created DESC", "DG")
            == 'project = "DG" AND (status = Done) ORDER BY created DESC'
        )

    def test_order_by_is_matched_case_insensitively(self) -> None:
        scoped = scope_to_project("status = Done order by created", "DG")
        assert scoped == 'project = "DG" AND (status = Done) order by created'

    def test_a_bare_order_by_query_still_works(self) -> None:
        assert (
            scope_to_project("ORDER BY created", "DG")
            == 'project = "DG" ORDER BY created'
        )

    def test_order_by_inside_a_quoted_value_is_not_treated_as_a_sort(self) -> None:
        """A ticket summary can contain the words "order by". Hoisting that
        out of the query would corrupt the search rather than scope it."""
        scoped = scope_to_project('summary ~ "order by total" AND status = Done', "DG")
        assert (
            scoped
            == 'project = "DG" AND (summary ~ "order by total" AND status = Done)'
        )


class TestTheKeyIsQuoted:
    @pytest.mark.parametrize("key", ["DG", "TWA", "ISAC"])
    def test_every_real_project_key_scopes(self, key: str) -> None:
        assert scope_to_project("status = Done", key).startswith(
            f'project = "{key}" AND'
        )

    def test_a_key_containing_a_quote_is_rejected_rather_than_escaped(self) -> None:
        """The project key comes from the registry, not from the caller, so
        this is defence in depth rather than a live injection path. Rejecting
        beats escaping: there is no legal Jira key with a quote in it, so a key
        that has one means the registry is wrong and should say so."""
        with pytest.raises(ValueError):
            scope_to_project("status = Done", 'DG" OR project = "ISAC')
