# mypy: ignore-errors
"""DG-428: a generated-input test for the JQL scope wrapper.

`scope_to_project` wraps a caller's clause as `project = "KEY" AND
(<clause>)`. The whole guarantee is that the clause stays trapped inside that
`AND (...)` — so the thing worth fuzzing is not "does it crash" but "can the
output ever be parsed as a top-level OR that escapes the wrap".

The checker here is deliberately **not** `jira_mcp.jql`. Re-using the
balance/quote scanner under test to grade its own output would only prove the
two agree with themselves. `_independent_scan` is a second, small,
intentionally separate implementation of the same quote-aware walk, written
only for this test, so a bug shared by both would have to be written twice by
accident rather than once.

For every generated clause, one of two things must be true:
* `scope_to_project` refuses it (`ValidationError`, nothing else — an
  unhandled exception here is itself a bug, not a safe refusal), or
* it returns a string that the independent scanner confirms is sound (parens
  balanced, no string left open) **and** has no top-level `OR` — which is
  exactly the shape that would let a clause escape the `AND (...)` wrap.
"""

from __future__ import annotations

import random
import re

import pytest

from core.errors import ValidationError
from jira_mcp.jql import scope_to_project

_PROJECT_KEY = "DG"

#: Tokens chosen to cover what the ticket names explicitly: both quote
#: characters, parens, the boolean keywords, backslashes (lone and doubled,
#: so an escape and "an escaped escape" both show up), unicode quote
#: look-alikes (not real JQL quote syntax — included to prove they are inert
#: rather than silently treated as one), ORDER BY, and a `--`/`/* */` pseudo
#: comment marker (JQL has no comment syntax, so these are just text).
_TOKENS = [
    '"',
    "'",
    "(",
    ")",
    "OR",
    "AND",
    "NOT",
    "project",
    "ORDER BY",
    "\\",
    "\\\\",
    '\\"',
    "\\'",
    "“",
    "”",
    "‘",
    "’",
    "=",
    "DG",
    "BETA",
    "status",
    "EMPTY",
    "summary",
    "~",
    "123",
    " ",
    "--",
    "/*",
    "*/",
    "a",
    "b",
    ")(",
    "()",
    "\n",
    "\t",
]


def _random_clause(rng: random.Random, max_tokens: int = 24) -> str:
    count = rng.randint(0, max_tokens)
    return "".join(rng.choice(_TOKENS) for _ in range(count))


_OR_WORD = re.compile(r"\bOR\b", re.IGNORECASE)
_ORDER_BY_WORD = re.compile(r"\border\s+by\b", re.IGNORECASE)


def _independent_split_order_by(text: str) -> tuple[str, str]:
    """Where `scope_to_project`'s own sort clause begins, found the same
    quote-aware way but as a second, separate implementation.

    Needed because ORDER BY is not part of the `AND (...)` wrap — it is
    appended after it closes — and JQL's own grammar there accepts a field
    list, not a boolean expression. Garbage after ORDER BY fails the query
    outright rather than executing as logic (the finding calls this out:
    "an ORDER BY lane breaks into a syntax error by accident"), so an `OR`
    sitting in that tail is not the escape the condition portion is checked
    for.
    """
    quote: str | None = None
    for index, char in enumerate(text):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if _ORDER_BY_WORD.match(text, index):
            return text[:index], text[index:]
    return text, ""


def _independent_scan(text: str) -> tuple[bool, bool]:
    """(sound, has_top_level_or) for *text*, scanned from scratch.

    ``sound`` is False if a `)` ever takes the depth below zero, or the text
    ends with an open paren or an open string. ``has_top_level_or`` is True
    if an `OR` keyword appears outside both parentheses and a string literal
    — the one shape that lets a clause fall out of `AND (...)`.
    """
    depth = 0
    quote: str | None = None
    has_or = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if quote is not None:
            if char == "\\" and index + 1 < length:
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth -= 1
            if depth < 0:
                return False, has_or
            index += 1
            continue
        if depth == 0 and _OR_WORD.match(text, index):
            has_or = True
        index += 1
    sound = depth == 0 and quote is None
    return sound, has_or


class TestTheIndependentScannerAgreesWithKnownShapes:
    """The checker is new code too — proven against known-good and
    known-bad shapes before it is trusted to grade 2,000 generated ones."""

    def test_a_simple_wrap_is_sound_with_no_top_level_or(self) -> None:
        sound, has_or = _independent_scan('project = "DG" AND (status = Done)')
        assert sound and not has_or

    def test_an_unbalanced_close_is_unsound(self) -> None:
        sound, _ = _independent_scan('project = "DG" AND (x) OR y)')
        assert not sound

    def test_a_top_level_or_is_detected(self) -> None:
        sound, has_or = _independent_scan('project = "DG" AND (x) OR y')
        assert sound and has_or

    def test_an_or_inside_parens_is_not_top_level(self) -> None:
        sound, has_or = _independent_scan('project = "DG" AND (x OR y)')
        assert sound and not has_or

    def test_an_or_inside_a_quoted_value_is_not_top_level(self) -> None:
        sound, has_or = _independent_scan('summary ~ "x OR y"')
        assert sound and not has_or


def _assert_scope_holds(wrapped: str) -> None:
    body, _order_by_tail = _independent_split_order_by(wrapped)

    sound, has_top_level_or = _independent_scan(body)
    assert sound, f"scope_to_project returned an unsound query: {wrapped!r}"
    assert not has_top_level_or, (
        f"scope_to_project returned a query with a top-level OR before "
        f"ORDER BY — the project scope can be escaped: {wrapped!r}"
    )
    assert wrapped.startswith(f'project = "{_PROJECT_KEY}"'), (
        f"the project filter is not even where it is supposed to be: {wrapped!r}"
    )

    # The tail is not boolean content in real JQL — ORDER BY takes a field
    # list, so anything else there fails the query outright rather than
    # executing as logic — but it must still be sound: no open string, no
    # paren this wrap's own close did not account for.
    tail_sound, _ = _independent_scan(_order_by_tail)
    assert tail_sound, f"the ORDER BY tail is unsound on its own: {wrapped!r}"


class TestGeneratedClausesCannotEscapeTheScope:
    """2,000 clauses, stdlib `random` with a fixed seed so a failure is
    reproducible without saving the input that caused it."""

    SEED = 1225428
    COUNT = 2000

    def test_every_generated_clause_is_refused_or_provably_scoped(self) -> None:
        rng = random.Random(self.SEED)
        refused = 0
        accepted = 0
        for _ in range(self.COUNT):
            clause = _random_clause(rng)
            try:
                wrapped = scope_to_project(clause, _PROJECT_KEY)
            except ValidationError:
                refused += 1
                continue
            except ValueError:  # pragma: no cover - would mean a key, not a clause
                pytest.fail(
                    "a clause caused the key-quote path, which means the "
                    f"generator or the split is wrong: {clause!r}"
                )
            accepted += 1
            _assert_scope_holds(wrapped)

        # Not a vacuous pass: both branches of the fuzz loop must have fired
        # for 2,000 inputs built from these tokens, or the test is not
        # exercising what it claims to.
        assert refused > 0, "no generated clause was ever refused"
        assert accepted > 0, "no generated clause was ever accepted"

    def test_the_named_reproduction_is_among_the_refused(self) -> None:
        with pytest.raises(ValidationError):
            scope_to_project(
                'status is not EMPTY) OR project = "OTHER" OR (status is not EMPTY',
                _PROJECT_KEY,
            )

    @pytest.mark.parametrize(
        "clause",
        [
            "status = Done",
            "project = BETA AND status = Done",
            "status = Done OR project = BETA",
            "status = Done ORDER BY created DESC",
            'summary ~ "order by total" AND status = Done',
            "",
        ],
    )
    def test_legitimate_clauses_from_the_existing_suite_still_scope(
        self, clause: str
    ) -> None:
        """The same clauses `test_jira_jql_scope.py` already covers, checked
        here by the independent parser instead of an exact string match —
        belt and braces on the same guarantee."""
        _assert_scope_holds(scope_to_project(clause, _PROJECT_KEY))
