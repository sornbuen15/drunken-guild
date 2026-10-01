"""Keeping a JQL query inside the project the call named.

S8 (DG-225). ``jira_search_issues`` passed the caller's JQL straight to Jira.
The project named the search's *subject* and then did nothing to keep the query
inside it, so ``project = OTHER AND ...`` reached whatever the credential could
reach — and one credential reaches several projects. Since DG-341 the subject
arrives as the tool's own first argument rather than as a flag on the server,
which changes where it comes from and nothing about why wrapping is needed.

The approach is deliberately not "validate the query". Deciding whether a
query language expression is safe by parsing it is the same losing game as
matching shell commands by prefix, which :mod:`core.permission_rules` already
admits about itself. Here there is a better option, because JQL has boolean
conjunction: **wrap** rather than inspect. Whatever the caller wrote becomes a
sub-clause of ``project = "KEY" AND (...)`` and is constrained by the
conjunction, no matter what it says. Nothing about the caller's syntax has to
be understood, so nothing about it can be got wrong.

Two details carry the whole guarantee:

* The parentheses are not cosmetic. ``project = "DG" AND a OR b`` binds as
  ``(project = "DG" AND a) OR b``, and the ``OR`` escapes the scope entirely.
* ``ORDER BY`` has to be lifted out of the parentheses, because a sort inside
  them is not valid JQL. That is the one piece of parsing that cannot be
  avoided, and it is done quote-aware so a ticket whose summary contains the
  words "order by" is searched rather than mangled.
"""

from __future__ import annotations

import re
from typing import Final

from core.errors import ValidationError

#: Matches a trailing sort clause. Applied only to the parts of the query that
#: sit outside quotes — see :func:`_split_order_by`.
_ORDER_BY: Final = re.compile(r"\border\s+by\b", re.IGNORECASE)

#: DG-428. The wrap is `project = "KEY" AND (<clause>)`, so a clause whose
#: parentheses are unbalanced closes that wrapper early — the finding. A
#: linear scan is bounded work regardless of input shape, but an unbounded
#: caller string is still its own problem, so one is refused outright rather
#: than scanned.
_MAX_LENGTH: Final = 10_000


def _split_order_by(jql: str) -> tuple[str, str]:
    """Split *jql* into (condition, trailing ORDER BY clause).

    Quote- and escape-aware, using the same rule and the same
    :func:`_skip_string_literal` as :func:`_check_balanced`: a backslash
    inside a string literal escapes whatever follows it, so an escaped quote
    does not end the literal early. DG-428 follow-up — an adversarial review
    of this ticket's first PR found that this function and
    ``_check_balanced`` used to disagree about where a string ends (this one
    was blind to the escape, that one was not), which could leave a real,
    top-level ``ORDER BY`` sitting *inside* the ``AND (...)`` wrap because
    this function thought it was still inside a string that the escaped
    quote had, in fact, already closed. Both are the same rule now, so there
    is nothing left for the two to disagree about.
    """
    index = 0
    length = len(jql)
    while index < length:
        char = jql[index]
        if char in ("'", '"'):
            index, _closed = _skip_string_literal(jql, index + 1, char)
            continue
        match = _ORDER_BY.match(jql, index)
        if match:
            return jql[:index].strip(), jql[index:].strip()
        index += 1
    return jql.strip(), ""


def _skip_string_literal(text: str, start: int, quote: str) -> tuple[int, bool]:
    """(index just past the literal, whether it was actually closed).

    *start* is the index right after the opening *quote*. A backslash inside
    a literal escapes whatever follows it — quote or not — so ``\\"`` and
    ``\\\\`` both consume two characters rather than letting the second one
    be seen on its own. Reaching the end of *text* without an unescaped
    *quote* means the literal was never closed; the caller treats that as its
    own refusal rather than silently rejoining the scan.
    """
    index = start
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\" and index + 1 < length:
            index += 2
            continue
        if char == quote:
            return index + 1, True
        index += 1
    return length, False


def _refuse_unbalanced(depth: int, position: int) -> None:
    """Raise once *depth* says the clause cannot stay inside the wrapper."""
    if depth < 0:
        raise ValidationError(
            f"JQL has a ')' with no matching '(' (position {position}).",
            remediation=(
                "Balance the parentheses, or drop the stray ')'. An "
                "unbalanced clause can close the project scope early and "
                "reach another project's issues."
            ),
        )


def _check_balanced(text: str) -> None:
    """Refuse *text* unless its parentheses balance outside string literals.

    A quote (``'`` or ``"`` — JQL allows either) opens a string literal that
    runs to the next *unescaped* matching quote (see
    :func:`_skip_string_literal`). Outside a literal a backslash is an
    ordinary character: JQL defines no escaping there, and treating one as
    the start of an escape would be inventing syntax that lets a parenthesis
    hide from the count.

    Raises :class:`~core.errors.ValidationError` — with a remediation line —
    the moment a ``)`` would take the depth below zero, and again at the end
    if depth is still nonzero or a string literal was never closed. Either
    one means the clause does not stay inside the ``project = "KEY" AND
    (...)`` wrapper it is about to be put in.
    """
    depth = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in ("'", '"'):
            index, closed = _skip_string_literal(text, index + 1, char)
            if not closed:
                raise ValidationError(
                    f"JQL has an unterminated {char} string literal.",
                    remediation=(
                        "Close the string with a matching, unescaped quote "
                        "before sending the query."
                    ),
                )
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            _refuse_unbalanced(depth, index)
        index += 1

    if depth != 0:
        raise ValidationError(
            f"JQL has {depth} unmatched '(' with no closing ')'.",
            remediation=(
                "Balance the parentheses. An unbalanced clause can close the "
                "project scope early and reach another project's issues."
            ),
        )


def scope_to_project(jql: str, project_key: str) -> str:
    """Constrain *jql* to *project_key*.

    Raises :exc:`ValueError` if the key contains a quote. That value comes from
    the registry rather than from a caller, so this is defence in depth — but
    no legal Jira key contains a quote, so one that does means the registry is
    wrong and should say so rather than be escaped into working.
    """
    if '"' in project_key or "'" in project_key:
        raise ValueError(
            f"Project key {project_key!r} contains a quote. Jira keys are "
            "alphanumeric; fix the registry entry rather than escaping it."
        )

    raw = jql or ""
    if len(raw) > _MAX_LENGTH:
        raise ValidationError(
            f"JQL is {len(raw)} characters, over the {_MAX_LENGTH} limit.",
            remediation=f"Shorten the query to {_MAX_LENGTH} characters or fewer.",
        )

    scope = f'project = "{project_key}"'
    condition, order_by = _split_order_by(raw)
    # Both parts, separately: a stray ')' in the ORDER BY lane does not close
    # the wrapper (it is appended after it closes), but it is still not valid
    # JQL and still worth refusing with a remediation rather than leaving it
    # to arrive as an opaque syntax error.
    _check_balanced(condition)
    _check_balanced(order_by)

    if not condition:
        return f"{scope} {order_by}".strip()
    if not order_by:
        return f"{scope} AND ({condition})"
    return f"{scope} AND ({condition}) {order_by}"
