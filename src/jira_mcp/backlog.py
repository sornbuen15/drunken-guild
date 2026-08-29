"""Keeping a backlog move inside the project the server was launched for.

DG-251. Everything else in this server runs on ``/rest/api/3`` and takes an
issue key that already belongs to a project, or a JQL query that
:mod:`jira_mcp.jql` wraps into one. The agile move endpoints are different in a
way that matters:

    POST /rest/agile/1.0/backlog/{boardId}/issue   {"issues": ["BETA-5"]}

**takes any issue key from any project and moves it.** The board id constrains
nothing — Jira reads the keys, not the board, when deciding what to move. A
server launched for DG could move BETA's tickets, succeed, and report success.
One credential reaches DG, ALPHA and BETA, so this is the same hole S8 opened in
``jira_search_issues`` and it takes the same answer: make the scope structural
rather than trusting what the caller passed.

Unlike JQL there is nothing to wrap here, so this validates instead — which is
tolerable only because an issue key is a fixed, tiny grammar (``KEY-123``),
not a query language. Validating a grammar this small is a different activity
from deciding whether an arbitrary expression is safe.

Two details are deliberate:

* The project part is compared **whole**, not as a prefix. ``DGX-1`` starts with
  ``DG`` and belongs to somebody else.
* One foreign key refuses the entire batch. Moving the valid half and reporting
  the rest leaves a partial move that nothing recorded, which is the hardest
  state to reason back out of.
"""

from __future__ import annotations

import re
from typing import Final

from core.errors import ValidationError

#: Jira's own cap on a single move. Documented on both agile move endpoints.
MAX_ISSUES: Final = 50

#: ``PROJECT-123``. Project keys start with a letter; the number is the whole
#: rest of the key, so ``DG-251-x`` is not one.
_KEY: Final = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)-([0-9]+)$")

#: Keys may arrive comma-separated, whitespace-separated, or both.
_SEPARATORS: Final = re.compile(r"[,\s]+")

#: What Jira says when a board has no backlog. Both spellings observed live on
#: 2026-08-16: the first from the two move endpoints, the second from
#: ``GET /board/{id}/backlog``. Matched only to *classify* a 400 that has
#: already been identified by its status code — never to detect an error.
_NO_BACKLOG: Final = ("without backlog", "backlogs are not supported")


def is_no_backlog_response(message: str) -> bool:
    """Whether an upstream 400 means "this board has no backlog"."""
    lowered = message.lower()
    return any(phrase in lowered for phrase in _NO_BACKLOG)


def scope_keys(raw: str, project_key: str) -> list[str]:
    """Parse *raw* into issue keys, refusing anything outside *project_key*.

    Returns keys uppercased, in the order given. Raises
    :class:`~core.errors.ValidationError` — never a bare ``ValueError`` — so the
    refusal reaches the agent as a result carrying its next step rather than as
    an internal error.
    """
    candidates = [part for part in _SEPARATORS.split(raw.strip()) if part]

    if not candidates:
        raise ValidationError(
            "No issue keys were given.",
            remediation=(
                f"Pass one or more keys from this project, e.g. "
                f'"{project_key}-123" or "{project_key}-123, {project_key}-124".'
            ),
        )

    if len(candidates) > MAX_ISSUES:
        raise ValidationError(
            f"{len(candidates)} issues were given and Jira moves at most "
            f"{MAX_ISSUES} at once.",
            remediation=(
                f"Split them into batches of {MAX_ISSUES} or fewer. Sending more "
                "returns a partial result that has to be reconciled afterwards."
            ),
        )

    keys: list[str] = []
    for candidate in candidates:
        match = _KEY.match(candidate)
        if not match:
            raise ValidationError(
                f"{candidate!r} is not a Jira issue key.",
                remediation=(
                    f"A key looks like {project_key}-123. Give the key, not a "
                    "summary, a URL or a project key on its own."
                ),
                details={"rejected": candidate},
            )

        if match.group(1).upper() != project_key.upper():
            raise ValidationError(
                f"{candidate.upper()} does not belong to {project_key}, which is "
                "the project this server is bound to.",
                remediation=(
                    f"Move only {project_key} issues from here. To move another "
                    "project's work, run a server bound to that project — the "
                    "binding is what the server was started with, never an "
                    "argument to a tool."
                ),
                details={"rejected": candidate.upper(), "project": project_key},
            )

        keys.append(candidate.upper())

    return keys
