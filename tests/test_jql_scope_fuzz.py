# mypy: ignore-errors
"""DG-428: a generated-input test for the JQL scope wrapper.

`scope_to_project` wraps a caller's clause as `project = "KEY" AND
(<clause>)`. The whole guarantee is that the clause stays trapped inside that
`AND (...)` — so the thing worth fuzzing is not "does it crash" but "can the
output ever be parsed as a top-level OR that escapes the wrap".

The checker here is deliberately **not** `jira_mcp.jql`, and deliberately not
shaped like it either. An adversarial review of the first version of this
file (PR #125) found that `_independent_split_order_by` copied the same
backslash-*blind* quote-toggle loop as production's own `_split_order_by` —
right down to the shape of the loop — so it could never catch the one
disagreement the ticket is about: a splitter that gets escaping wrong and a
balance checker that gets it right, drifting apart on the same input. Grading
production's output with a checker that shares production's bug proves only
that the two agree with each other, not that either is correct.

This version is built a different way on purpose: Atlassian's own rule —
*a backslash inside a quoted string escapes the next character; only `'` and
`"` delimit a string; nothing is special about a backslash outside one* — is
stated directly as a regex (`"(?:\\.|[^"\\])*"`, and the same for `'`) rather
than as a hand-rolled loop that has to re-derive the rule one character at a
time. Finding real string literals is a single `re.sub` pass that masks them
out; everything downstream (paren balance, ORDER BY, top-level `OR`) runs on
text that is already free of quotes, as a fold over regex matches rather than
an index-stepping walk. No function here has the same control-flow shape as
anything in `jira_mcp.jql`.

For every generated clause, one of two things must be true:
* `scope_to_project` refuses it (`ValidationError`, nothing else — an
  unhandled exception here is itself a bug, not a safe refusal), or
* it returns a string that the independent parser confirms is sound (parens
  balanced, no string left open, ORDER BY — if any — correctly outside the
  parens) **and** has no top-level `OR` before it — which is exactly the
  shape that would let a clause escape the `AND (...)` wrap.
"""

from __future__ import annotations

import random
import re

import pytest

from core.errors import ValidationError
from jira_mcp.jql import _split_order_by, scope_to_project

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


# --- the independent parser -------------------------------------------------
#
# Two phases, each doing one thing:
#
# 1. `_mask_strings` finds every well-formed JQL string literal — via the
#    Atlassian escaping rule spelled out as a regex, not a loop — and blanks
#    it out with same-length filler. A quote left over afterwards can only
#    mean one that was never closed.
# 2. `_fold` reads what is left (now free of quotes) for parens and `OR`,
#    as a fold over regex matches rather than a character-by-character scan.
#
# Neither phase tracks an open/close quote as mutable state the way
# `jira_mcp.jql._check_balanced` and `_split_order_by` both do; that shared
# shape is exactly what let the first version of this file miss the bug the
# ticket is about.

#: `"(?:\.|[^"\\])*"` reads as: a quote, then any number of (an escaped
#: character, or any character that is not a bare quote or backslash), then
#: the matching quote. That *is* the escaping rule, not an approximation of
#: it — a backslash always takes the next character with it, so a `\"` can
#: never be mistaken for the literal's end.
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"' r"|'(?:\\.|[^'\\])*'", re.DOTALL)

_RELEVANT = re.compile(r"\(|\)|\bOR\b", re.IGNORECASE)
_ORDER_BY_TOKEN = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)


def _mask_strings(text: str) -> tuple[str, bool]:
    """(text with every real string literal blanked out, a stray quote was
    left over).

    Filler is the same length as what it replaces, so an index found in the
    masked text is still valid against the original — needed by
    :func:`_independent_split_order_by`. A `'` or `"` surviving the
    substitution did not belong to a literal the regex could close, which
    only happens when one was opened and never finished.
    """
    masked = _STRING_LITERAL.sub(lambda m: "\x00" * len(m.group()), text)
    stray_quote = "'" in masked or '"' in masked
    return masked, stray_quote


def _fold(text: str) -> tuple[bool, bool]:
    """(sound, has_top_level_or), folding over the parens and `OR` keywords
    left in *text* once :func:`_mask_strings` has already removed anything
    those could mean inside a value."""
    depth = 0
    has_or = False
    went_negative = False
    for token in _RELEVANT.finditer(text):
        matched = token.group()
        if matched == "(":
            depth += 1
        elif matched == ")":
            depth -= 1
            went_negative = went_negative or depth < 0
        elif depth == 0:
            has_or = True
    sound = not went_negative and depth == 0
    return sound, has_or


def _independent_scan(text: str) -> tuple[bool, bool]:
    """(sound, has_top_level_or) for *text*, built from scratch for this
    test: mask real string literals out, then fold what remains."""
    masked, stray_quote = _mask_strings(text)
    sound, has_or = _fold(masked)
    return sound and not stray_quote, has_or


def _independent_split_order_by(text: str) -> tuple[str, str]:
    """Where a *correctly* quote-and-escape-aware reading of *text* would
    put its ORDER BY split — found by masking real string literals out
    (same-length filler keeps every index valid) and then searching the
    masked text for the first `ORDER BY` outside one. The split itself is
    taken from the *original* text, so quoted content comes back untouched.

    This is the independent counterpart to `jira_mcp.jql._split_order_by` —
    answering the same question, but by regex substitution and search rather
    than by a hand-rolled quote-toggle loop, and honouring the escaping rule
    that loop does not.
    """
    masked, _ = _mask_strings(text)
    match = _ORDER_BY_TOKEN.search(masked)
    if not match:
        return text, ""
    return text[: match.start()], text[match.start() :]


class TestTheIndependentParserAgreesWithKnownShapes:
    """The checker is new code too — proven against known-good and
    known-bad shapes before it is trusted to grade thousands of generated
    ones."""

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

    def test_an_escaped_quote_does_not_end_the_literal_early(self) -> None:
        """`"a\\"b)c"` is one literal containing `a"b)c`; the `)` must not
        be seen at all, masked or not."""
        sound, has_or = _independent_scan('summary ~ "a\\"b)c" AND (x)')
        assert sound and not has_or

    def test_order_by_inside_a_quoted_value_is_not_a_split_point(self) -> None:
        body, tail = _independent_split_order_by('summary ~ "order by total"')
        assert body == 'summary ~ "order by total"'
        assert tail == ""

    def test_order_by_after_an_escaped_quote_is_still_found(self) -> None:
        """The exact shape of the bug this file exists to catch: an escaped
        quote must not be mistaken for the end of the string, which would
        leave a *real* top-level ORDER BY looking like it is still inside
        one."""
        body, tail = _independent_split_order_by('summary ~ "a\\"b" ORDER BY x')
        assert body == 'summary ~ "a\\"b" '
        assert tail == "ORDER BY x"


def _assert_scope_holds(wrapped: str) -> None:
    body, order_by_tail = _independent_split_order_by(wrapped)

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
    tail_sound, _ = _independent_scan(order_by_tail)
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


# --- proving the independent parser actually catches the named bug ---------
#
# An adversarial review of PR #125 found the first version of this file
# vacuous for exactly the disagreement DG-428 is about: it copied
# `_split_order_by`'s own backslash-blind quote loop, so when production's
# splitter and its (corrected) balance checker drifted apart on the same
# input, the test's splitter drifted the same way and "agreed" with the
# mistake. `_independent_split_order_by` above is not that loop — this class
# proves it, by rebuilding a scratch copy of the *old*, backslash-blind
# splitter (never touching `src/`) and pairing it with the real, corrected
# `jira_mcp.jql._check_balanced`, to show the new parser catches what the
# old one could not.


def _scratch_blind_split_order_by(jql: str) -> tuple[str, str]:
    """A pinned, scratch-only copy of `jira_mcp.jql._split_order_by`'s
    algorithm — quote-aware, but blind to `\\`-escaping, exactly as it reads
    on `develop` today. Defined here, not imported, and used only to build
    the one adversarial example below; it is not the independent parser."""
    quote: str | None = None
    order_by = re.compile(r"\border\s+by\b", re.IGNORECASE)
    for index, char in enumerate(jql):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if order_by.match(jql, index):
            return jql[:index].strip(), jql[index:].strip()
    return jql.strip(), ""


def _scratch_wrap_with_blind_split(jql: str, project_key: str) -> str:
    """`scope_to_project`, but with the scratch blind splitter standing in
    for the real one and the real `_check_balanced` otherwise unchanged —
    "a deliberately backslash-blind scratch variant of production's
    splitter paired with the correct balance check"."""
    from jira_mcp.jql import _check_balanced

    scope = f'project = "{project_key}"'
    condition, order_by = _scratch_blind_split_order_by(jql)
    _check_balanced(condition)
    _check_balanced(order_by)
    if not condition:
        return f"{scope} {order_by}".strip()
    if not order_by:
        return f"{scope} AND ({condition})"
    return f"{scope} AND ({condition}) {order_by}"


class TestTheIndependentParserCatchesTheBlindSplitterBug:
    #: Found by running the *real* `scope_to_project` (unmodified, as
    #: committed) through 200,000+ generated clauses and grading the result
    #: with `_independent_scan`/`_independent_split_order_by`: production's
    #: own blind `_split_order_by` fails to find this clause's real,
    #: top-level `ORDER BY` — because the escaped quote at index 2-3 closes
    #: its quote tracking one character early, so it treats everything from
    #: index 4 onward (including the literal `ORDER BY`) as still inside an
    #: unterminated string — and returns the whole thing as "condition",
    #: with no ORDER BY split at all.
    ADVERSARIAL_CLAUSE = '\\"\\""\\--ORDER BY'

    def test_the_scratch_blind_splitter_reproduces_the_original_bug(self) -> None:
        """Not a strawman: this is what `jira_mcp.jql._split_order_by`
        itself returned for this input before this same PR made it
        escape-aware — pinned here as a fixed value (rather than compared
        against the live function, which this PR's own fix changes) so the
        scratch copy stays an honest stand-in for the bug being
        demonstrated, independent of whether that bug is still present."""
        assert _scratch_blind_split_order_by(self.ADVERSARIAL_CLAUSE) == (
            self.ADVERSARIAL_CLAUSE,
            "",
        )

    def test_the_real_splitter_no_longer_has_this_bug(self) -> None:
        """The fix, as an assertion: now that `_split_order_by` shares
        `_check_balanced`'s escape rule, it finds the real, top-level
        `ORDER BY` this adversarial clause contains, same as the
        independent parser does."""
        assert _split_order_by(self.ADVERSARIAL_CLAUSE) == (
            '\\"\\""\\--',
            "ORDER BY",
        )

    def test_the_blind_split_traps_a_real_order_by_inside_the_parens(self) -> None:
        """What the blind splitter's mistake produces: `ORDER BY` left
        *inside* `AND (...)`, which `jira_mcp.jql`'s own module docstring
        names as not valid JQL ("a sort inside them is not valid JQL") —
        Jira fails this query outright rather than running it as logic, so
        it is not a live scope escape, but it is a real, silently-accepted
        malformed query that the balance checker alone has no way to catch,
        because it has no opinion about where ORDER BY belongs."""
        wrapped = _scratch_wrap_with_blind_split(self.ADVERSARIAL_CLAUSE, _PROJECT_KEY)
        assert wrapped == 'project = "DG" AND (\\"\\""\\--ORDER BY)'

    def test_the_new_independent_parser_flags_it_as_unsound(self) -> None:
        """The proof the ticket asked for: the rewritten, genuinely
        independent parser — which, unlike the first version of this file,
        correctly closes the string at the real unescaped quote and so finds
        the real top-level `ORDER BY` — reads this output as broken.
        `_assert_scope_holds` is exactly what the generated-input test runs
        against every accepted clause; calling it here, directly, is the
        failure the reviewer asked to see quoted."""
        wrapped = _scratch_wrap_with_blind_split(self.ADVERSARIAL_CLAUSE, _PROJECT_KEY)
        with pytest.raises(AssertionError, match="unsound query"):
            _assert_scope_holds(wrapped)

    def test_the_old_copy_shaped_splitter_would_have_missed_it(self) -> None:
        """What made the first version of this file vacuous for this case:
        a splitter sharing `_split_order_by`'s own blind loop (reproduced
        here, scratch-only, for this one comparison) finds *no* ORDER BY in
        the already-wrapped output either — because the wrap's own opening
        `"DG"` and the clause's escaped quote throw its tracking off the
        same way — so it would have handed the whole wrapped string to the
        balance scanner as one piece, which (having no opinion on ORDER BY
        placement) finds it perfectly balanced and reports no problem at
        all."""
        wrapped = _scratch_wrap_with_blind_split(self.ADVERSARIAL_CLAUSE, _PROJECT_KEY)
        blind_body, _blind_tail = _scratch_blind_split_order_by(wrapped)
        assert blind_body == wrapped, (
            "if this ever stops matching, the scratch copy is no longer "
            "reproducing the blind spot it exists to demonstrate"
        )
