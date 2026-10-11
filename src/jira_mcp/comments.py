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

    ``bool`` is rejected even though Python's own ``int(True) == 1`` would
    happily accept it: ``True`` is not a count, and ``int()`` on its own
    cannot tell the two apart. A non-integral float is rejected the same
    way -- ``int(3.7)`` silently truncates to 3, which is not what "3.7
    comments" could have meant. An integral float such as ``3.0`` *is*
    accepted: it names a whole number exactly, just spelled with a decimal
    point, and asking for "3.0 comments" has only one sensible reading.
    """
    if isinstance(limit, bool):
        raise ValidationError(
            f"{limit!r} is not a number.",
            remediation=f"Pass an integer between 1 and {MAX_COMMENTS}.",
        )

    if isinstance(limit, float) and not limit.is_integer():
        raise ValidationError(
            f"{limit!r} is not a whole number.",
            remediation=(
                f"Pass a whole number between 1 and {MAX_COMMENTS} -- "
                "comments cannot be read in fractions."
            ),
        )

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
