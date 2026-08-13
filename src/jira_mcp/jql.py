"""Keeping a JQL query inside the project the server was launched for.

S8 (DT-225). ``jira_search_issues`` passed the caller's JQL straight to Jira.
``--project`` named which project the server was *for* and then did nothing to
keep a query inside it, so ``project = OTHER AND ...`` reached whatever the
credential could reach — and one credential reaches DT, ALPHA and BETA.

The approach is deliberately not "validate the query". Deciding whether a
query language expression is safe by parsing it is the same losing game as
matching shell commands by prefix, which :mod:`core.permission_rules` already
admits about itself. Here there is a better option, because JQL has boolean
conjunction: **wrap** rather than inspect. Whatever the caller wrote becomes a
sub-clause of ``project = "KEY" AND (...)`` and is constrained by the
conjunction, no matter what it says. Nothing about the caller's syntax has to
be understood, so nothing about it can be got wrong.

Two details carry the whole guarantee:

* The parentheses are not cosmetic. ``project = "DT" AND a OR b`` binds as
  ``(project = "DT" AND a) OR b``, and the ``OR`` escapes the scope entirely.
* ``ORDER BY`` has to be lifted out of the parentheses, because a sort inside
  them is not valid JQL. That is the one piece of parsing that cannot be
  avoided, and it is done quote-aware so a ticket whose summary contains the
  words "order by" is searched rather than mangled.
"""

from __future__ import annotations

import re
from typing import Final

#: Matches a trailing sort clause. Applied only to the parts of the query that
#: sit outside quotes — see :func:`_split_order_by`.
_ORDER_BY: Final = re.compile(r"\border\s+by\b", re.IGNORECASE)


def _split_order_by(jql: str) -> tuple[str, str]:
    """Split *jql* into (condition, trailing ORDER BY clause).

    Quote-aware: `summary ~ "order by total"` is a search term, not a sort, and
    hoisting it would corrupt the query rather than scope it.
    """
    quote: str | None = None
    for index, char in enumerate(jql):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            continue
        match = _ORDER_BY.match(jql, index)
        if match:
            return jql[:index].strip(), jql[index:].strip()
    return jql.strip(), ""


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

    scope = f'project = "{project_key}"'
    condition, order_by = _split_order_by(jql or "")

    if not condition:
        return f"{scope} {order_by}".strip()
    if not order_by:
        return f"{scope} AND ({condition})"
    return f"{scope} AND ({condition}) {order_by}"
