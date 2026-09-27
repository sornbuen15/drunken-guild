"""Summary and description edits — DG-367.

Jira's issue edit changes only the fields named in ``fields`` and leaves every
other one as it is. So the one rule here is that an argument left empty is not
sent: empty means "leave it", never "clear it". Labels are not edited here at
all; ``labels.update_payload`` sends them as operations (DG-368).

Nothing is escaped. The finding behind this ticket was summaries created with
``&amp;`` where ``&`` was meant, and Jira stores a summary as plain text.
"""

from __future__ import annotations

from typing import Any, Dict, Final

from core.errors import ValidationError

from .jira_client import to_adf

#: Jira refuses a longer summary; refusing it here names the limit.
SUMMARY_MAX: Final = 255


def fields_payload(summary: str, description: str) -> Dict[str, Any]:
    """The edit body setting whichever of *summary* and *description* is given.

    Raises :class:`~core.errors.ValidationError` when neither is given, or when
    the summary is not one line of at most :data:`SUMMARY_MAX` characters.
    """
    fields: Dict[str, Any] = {}

    summary = summary.strip()
    if summary:
        if "\n" in summary or "\r" in summary:
            raise ValidationError(
                "A summary is one line.",
                remediation="Put the rest in description.",
            )
        if len(summary) > SUMMARY_MAX:
            raise ValidationError(
                f"Summary is {len(summary)} characters; Jira accepts {SUMMARY_MAX}.",
                remediation="Shorten it and move the detail to description.",
            )
        fields["summary"] = summary

    if description.strip():
        fields["description"] = to_adf(description)

    if not fields:
        raise ValidationError(
            "Nothing to change.",
            remediation='Pass summary="..." and/or description="...".',
        )
    return {"fields": fields}
