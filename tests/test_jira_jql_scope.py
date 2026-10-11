# mypy: ignore-errors
"""S8 — `jira_search_issues` passed raw JQL straight through.

`--project` named which project the server was for, and then did nothing to
keep a query inside it. `project = OTHER AND ...` reached whatever the
credential could reach, and the credential reaches DG, ALPHA and BETA.

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

from core.errors import ValidationError
from jira_mcp.jql import scope_to_project


class TestScoping:
    def test_a_plain_query_is_wrapped(self) -> None:
        assert (
            scope_to_project("status = Done", "DG")
            == 'project = "DG" AND (status = Done)'
        )

    def test_a_query_naming_another_project_cannot_escape(self) -> None:
        """The finding. The wrapped form is `project = "DG" AND (project =
        BETA ...)`, which matches nothing — the caller is constrained by
        conjunction rather than by us understanding their query."""
        scoped = scope_to_project("project = BETA AND status = Done", "DG")
        assert scoped.startswith('project = "DG" AND (')
        assert "BETA" in scoped, "the clause is kept, not silently rewritten"

    def test_an_empty_query_becomes_the_project_alone(self) -> None:
        assert scope_to_project("", "DG") == 'project = "DG"'
        assert scope_to_project("   ", "DG") == 'project = "DG"'

    def test_an_or_clause_cannot_widen_the_scope(self) -> None:
        """Without the parentheses, `project = "DG" AND a OR b` binds as
        `(project = DG AND a) OR b` and the OR escapes the scope entirely.
        This is the reason the wrap is parenthesised and not concatenated."""
        scoped = scope_to_project("status = Done OR project = BETA", "DG")
        assert scoped == 'project = "DG" AND (status = Done OR project = BETA)'


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
    @pytest.mark.parametrize("key", ["DG", "ALPHA", "BETA"])
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
            scope_to_project("status = Done", 'DG" OR project = "BETA')


# --- DG-428: an unbalanced parenthesis closes the wrapper early ------------
#
# scope_to_project wraps as `project = "KEY" AND (<clause>)`. A clause whose
# parentheses are unbalanced closes that `(` early (or leaves one open), and
# whatever follows escapes the AND it was meant to be trapped inside. Found by
# the reviewer of PR #124, present on develop and in every released version
# since DG-225.


class TestTheWrapperCannotBeEscaped:
    def test_the_reported_reproduction_is_refused(self) -> None:
        """The finding, verbatim. Unpatched, this returns
        `project = "DG" AND (status is not EMPTY) OR project = "OTHER" OR
        (status is not EMPTY)`, which Jira parses as
        `(project = "DG" AND ...) OR project = "OTHER" OR (...)` — every
        project the credential can reach, not just DG."""
        with pytest.raises(ValidationError) as caught:
            scope_to_project(
                'status is not EMPTY) OR project = "OTHER" OR (status is not EMPTY',
                "DG",
            )
        assert caught.value.remediation, "a refusal with no next step is a dead end"

    def test_a_lone_closing_paren_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            scope_to_project(")", "DG")

    def test_a_lone_opening_paren_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            scope_to_project("(", "DG")

    def test_a_close_before_any_open_is_refused_even_when_the_total_balances(
        self,
    ) -> None:
        """Two parens, equal counts, still invalid: ')(' closes before it ever
        opens. A check that only compares counts (weakened balance checking)
        would wrongly accept this."""
        with pytest.raises(ValidationError):
            scope_to_project(")(", "DG")

    def test_an_empty_clause_is_accepted(self) -> None:
        assert scope_to_project("", "DG") == 'project = "DG"'

    def test_a_closing_paren_inside_a_quoted_value_does_not_count(self) -> None:
        """The quote is real JQL syntax; what is inside it is a value, not
        structure. `project = "DG" AND (summary ~ "a)") ` is valid JQL and
        must not be refused."""
        scoped = scope_to_project('summary ~ "a)"', "DG")
        assert scoped == 'project = "DG" AND (summary ~ "a)")'

    def test_an_escaped_quote_inside_a_string_does_not_end_it_early(self) -> None:
        """`\\"` inside the string is an escaped quote, not the end of the
        literal, so the `)` right after it is still inside the string and
        must not be counted. A scanner that is not escape-aware ends the
        string one character too soon, sees the `)` as real, and wrongly
        refuses this legitimate, balanced clause."""
        clause = 'summary ~ "a\\"b)c" AND status = Done'
        scoped = scope_to_project(clause, "DG")
        assert scoped == f'project = "DG" AND ({clause})'

    def test_a_paren_inside_a_pseudo_comment_inside_a_string_does_not_count(
        self,
    ) -> None:
        """JQL has no comment syntax, so `--` is just two characters of a
        value. The `(` right after it sits inside a real string literal and
        must not be treated as an open paren."""
        clause = 'summary ~ "-- (unterminated comment" AND status = Done'
        scoped = scope_to_project(clause, "DG")
        assert scoped == f'project = "DG" AND ({clause})'

    def test_a_backslash_outside_a_string_does_not_hide_a_paren(self) -> None:
        """JQL defines no escaping outside a string literal, so a backslash
        there is an ordinary character and the `(` right after it is a real,
        structural open paren — one this clause never closes."""
        with pytest.raises(ValidationError):
            scope_to_project("status = Done \\( OR project = OTHER", "DG")

    def test_an_unterminated_string_literal_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            scope_to_project('summary ~ "never closed', "DG")

    def test_a_single_quoted_string_is_honoured_too(self) -> None:
        """JQL allows either quote character; a scanner that only recognises
        `"` would miscount a `)` sitting inside a `'...'` value."""
        clause = "summary ~ 'a)b'"
        scoped = scope_to_project(clause, "DG")
        assert scoped == f'project = "DG" AND ({clause})'

    def test_an_unbalanced_order_by_clause_is_refused_too(self) -> None:
        """Validated separately from the condition, per the ticket's scope —
        a stray paren there does not escape the wrapper (it is appended after
        it closes) but it is still not valid JQL and still worth a refusal
        that names the fix rather than an opaque Jira syntax error."""
        with pytest.raises(ValidationError):
            scope_to_project("status = Done ORDER BY (created", "DG")

    def test_a_huge_clause_is_refused_rather_than_scanned(self) -> None:
        """Bounded work: a pathological input is refused outright, not walked
        character by character regardless of length."""
        huge = "status = Done AND (" * 5000
        with pytest.raises(ValidationError):
            scope_to_project(huge, "DG")
