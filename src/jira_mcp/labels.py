"""Label edits as operations, never as a replacement set — DG-368.

Jira's issue edit takes labels two ways. ``fields.labels`` replaces the set,
which makes every caller a read-modify-write: two agents doing it at once each
write the set they read, and one label silently disappears. ``update.labels``
is a list of ``{"add": ...}`` / ``{"remove": ...}`` operations Jira applies
against the set as it is when the request arrives. Only the second is built
here, so the race cannot be expressed at all.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Final, List

from core.errors import ValidationError

#: Jira labels cannot contain whitespace, so it can safely separate them.
_SEPARATORS: Final = re.compile(r"[,\s]+")


def _parse(raw: str) -> List[str]:
    out: List[str] = []
    for part in _SEPARATORS.split(raw.strip()):
        if part and part not in out:
            out.append(part)
    return out


def update_payload(add: str, remove: str) -> Dict[str, Any]:
    """The edit body for adding *add* and removing *remove*.

    Raises :class:`~core.errors.ValidationError` when there is nothing to do,
    or when one label is both added and removed — the outcome would depend on
    the order Jira happens to apply them in.
    """
    to_add, to_remove = _parse(add), _parse(remove)

    if not to_add and not to_remove:
        raise ValidationError(
            "No labels to add or remove.",
            remediation='Pass add="agent:claude" and/or remove="medium".',
        )

    both = [label for label in to_add if label in to_remove]
    if both:
        raise ValidationError(
            f"Both added and removed: {', '.join(both)}.",
            remediation="Name each label in add or in remove, not both.",
        )

    ops: List[Dict[str, str]] = [{"add": label} for label in to_add]
    ops += [{"remove": label} for label in to_remove]
    return {"update": {"labels": ops}}
