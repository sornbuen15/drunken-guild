"""Bounding how many comments a read can ask for — DG-417.

Mirrors :func:`jira_mcp.backlog.scope_keys`'s shape: a small, fixed grammar
(here, a count rather than a key list) validated at the boundary rather than
trusted, with a :class:`~core.errors.ValidationError` that carries a concrete
next step instead of a bare exception.

There is no upstream limit to defer to here the way ``MAX_ISSUES`` defers to
Jira's own cap — comment pagination accepts any ``maxResults``. The cap below
is this tool's own: an agent reading "the last few comments" has no use for a
page of five hundred, and asking for one would spend tokens finding the one
correction that mattered.
"""

from __future__ import annotations

from typing import Any, Final

from core.errors import ValidationError

#: This tool's own ceiling, not Jira's. See module docstring.
MAX_COMMENTS: Final = 20


def validate_limit(limit: Any) -> int:
    """*limit* as a whole number between 1 and :data:`MAX_COMMENTS`, or a
    :class:`ValidationError` naming what was wrong and what to pass instead.
    """
    try:
        value = int(limit)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{limit!r} is not a number.",
            remediation=f"Pass an integer between 1 and {MAX_COMMENTS}.",
        ) from None

    if not (1 <= value <= MAX_COMMENTS):
        raise ValidationError(
            f"{value} is outside the range comments can be read in (1-{MAX_COMMENTS}).",
            remediation=f"Pass a limit between 1 and {MAX_COMMENTS}.",
        )

    return value
