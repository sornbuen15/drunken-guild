"""Resolving who an issue should be assigned to.

The local board is retired (DT-250). Jira is the one coordination surface, so
the **assignee** is what says whose work a ticket is and the **status** is what
says where it is. That only works if an agent can set an assignee — and until
this module nothing could. ``assignee`` came back in search results and no code
path ever wrote it.

The awkward part is not the write, it is the lookup. ``PUT
/rest/api/3/issue/{key}/assignee`` takes an ``accountId``, never a name, so
whatever a human or an agent typed has to be resolved against the project's
assignable users first.

**Resolution refuses rather than guesses.** A wrong match is worse than an
error: the ticket lands on someone else's queue, nothing fails, and nobody is
told — the same silent-wrong-answer shape as S4, where a dead credential
returned an empty list instead of an error. So an ambiguous match raises, and
every error names the candidates so the caller can pick instead of giving up.
"""

from __future__ import annotations

from typing import Any, Final, Optional, Sequence

#: Ways a caller says "assign it to whoever I am".
SELF_REFERENCES: Final = frozenset({"me", "@me", "self", "myself"})

#: Ways a caller says "take the assignee off".
UNASSIGN_REFERENCES: Final = frozenset({"", "none", "unassigned", "nobody", "null"})


def is_self_reference(assignee: str) -> bool:
    """Whether *assignee* means the calling identity.

    Resolved through ``/rest/api/3/myself`` by the caller — the one endpoint
    that reliably identifies who a credential belongs to, and already how
    :mod:`core.context` verifies one.
    """
    return assignee.strip().lower() in SELF_REFERENCES


def is_unassign(assignee: str) -> bool:
    """Whether *assignee* means "remove the assignee"."""
    return assignee.strip().lower() in UNASSIGN_REFERENCES


def payload_for(account_id: Optional[str]) -> dict[str, Any]:
    """The request body for the assignee endpoint.

    ``None`` unassigns, and it has to be sent as an explicit null: Jira reads a
    *missing* ``accountId`` as "no change", so omitting the field would silently
    do nothing while reporting success.
    """
    return {"accountId": account_id}


def _describe(candidates: Sequence[dict[str, Any]]) -> str:
    return ", ".join(
        f"{c.get('displayName', '?')} <{c.get('emailAddress', 'no email')}>"
        for c in candidates
    )


def pick_user(candidates: Sequence[dict[str, Any]], wanted: str) -> dict[str, Any]:
    """Choose the one assignable user *wanted* refers to.

    Exact email first, then exact display name, then a unique case-insensitive
    substring. Anything short of unique raises with every candidate named.
    """
    if not candidates:
        raise ValueError(
            f"No assignable users on this project, so {wanted!r} cannot be "
            "assigned to anyone. That is a project permission problem rather "
            "than a typo — check that the account can browse and be assigned "
            "issues here."
        )

    needle = wanted.strip().lower()

    for candidate in candidates:
        if str(candidate.get("emailAddress", "")).lower() == needle:
            return dict(candidate)

    for candidate in candidates:
        if str(candidate.get("displayName", "")).lower() == needle:
            return dict(candidate)

    partial = [
        candidate
        for candidate in candidates
        if needle in str(candidate.get("displayName", "")).lower()
        or needle in str(candidate.get("emailAddress", "")).lower()
    ]
    if len(partial) == 1:
        return dict(partial[0])
    if len(partial) > 1:
        raise ValueError(
            f"{wanted!r} matches more than one assignable user: "
            f"{_describe(partial)}. Refusing rather than picking one — a "
            "ticket assigned to the wrong person goes quiet on someone else's "
            "queue and nothing reports it. Use the full name or the email."
        )

    raise ValueError(
        f"No assignable user matches {wanted!r}. Assignable here: "
        f"{_describe(candidates)}."
    )
