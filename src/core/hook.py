"""PreToolUse hook — the deny floor, and nothing else.

This file used to route the harness's permission prompts to Discord: away mode,
a daemon socket, an approval state machine, and a learned-rules writer that
generalised each 👍 into a standing local rule. All of it is retired (DG-355).
Remote Control is where a session is watched now, and Discord is one-way
notification. What is left is the part that was never about asking anyone.

**A deny rule must hold even when no one can be reached.** That was always the
first step of the old order — evaluated before away mode, before
``bypassPermissions``, before anything — precisely because a remote 👍 must not
be able to authorise ``rm -rf``. With the remote half gone, the floor is the
whole file, and it answers the same two questions it always did:

1. Does a deny rule match this call? Then ``deny``, whatever the mode.
2. Can this call be read at all? A ``Bash`` with no command and a ``Read`` with
   no path match *no* rule — deny rules included — so they are refused rather
   than waved past the floor they were meant to hit (DG-321).

Everything else gets **silence**, which is not the same as ``allow``. Exit 0
with no ``permissionDecision`` means "no opinion", and the harness carries on
exactly as it would have. The hook never widens permission: an allowlisted call
gets silence too, because the harness evaluates that same list and a second
authority saying the same thing is only a second thing to disagree.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Final, Optional

from . import permission_rules as pr

#: The tool families that are meaningless without one input key. A ``Bash``
#: with no command and a ``Read`` with no path are not calls this hook can
#: judge -- they are calls it failed to read.
#:
#: Keyed on :func:`~core.permission_rules.canonical_tool`'s output, not on a
#: tool's own spelling. DG-334: the write side was once guarded under ``Write``
#: and stopped being guarded the day the name it arrived under became ``Edit``,
#: because the guard was keyed on a spelling rather than on the family.
UNREADABLE_KEYS: Final = {
    "Bash": ("command",),
    "Read": pr.PATH_KEYS,
    pr.EDIT_TOOL_CANONICAL: pr.PATH_KEYS,
}

DENIED_BY_RULE = (
    "Blocked by a deny rule in .claude/settings.json. Nothing overrides this "
    "one — if it genuinely needs to happen, raise it with the Boss directly."
)

UNREADABLE = (
    "This call carried no command or path, so no rule could be evaluated "
    "against it — including the deny rules. Refused rather than waved through: "
    "a call the hook cannot read is the one case where silence is the most "
    "dangerous answer it could give."
)


@dataclass(frozen=True)
class Decision:
    """``None`` means "no opinion" — the harness carries on as usual."""

    permission: Optional[str]
    reason: str = ""


def _is_unreadable(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Whether a call arrived without the one field that gives it meaning.

    DG-321. A call whose command or path is missing is not just noise:
    ``.get(name, "")`` yields an empty string, and an empty string matches no
    rule at all. Deny rules are rules. ``is_denied("Bash", {"command": ""},
    rules.deny)`` is ``False``, so the call would fall straight past the floor
    it was meant to hit.

    Narrow on purpose. Only the three tool families in :data:`UNREADABLE_KEYS`
    are checked; a tool that legitimately carries neither a command nor a path
    is not the hook's business, and denying it would break every session to
    close a hole that is not there.
    """
    keys = UNREADABLE_KEYS.get(pr.canonical_tool(tool_name))
    if keys is None:
        return False
    return not any(str(tool_input.get(key, "")).strip() for key in keys)


def decide(payload: dict[str, Any], rules: pr.Rules) -> Decision:
    """Resolve one tool call. Pure.

    Order matters and is asserted in the tests: the floor first, then silence.
    """
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    # 1. Deny, before anything else and regardless of mode.
    if pr.is_denied(tool_name, tool_input, rules.deny):
        return Decision("deny", DENIED_BY_RULE)

    # 2. A call that cannot be read cannot have been checked against the deny
    # list above, so it gets the same treatment rather than the benefit of the
    # doubt. Before `bypassPermissions` for the same reason step 1 is: that mode
    # turns off prompting, not the floor.
    if _is_unreadable(tool_name, tool_input):
        return Decision("deny", UNREADABLE)

    # 3. Everything else is the harness's own business. Silence, not `allow`:
    # the hook has a floor to enforce and no authority to widen anything.
    return Decision(None)


def render(decision: Decision) -> str:
    """Serialise to the documented PreToolUse output shape.

    A ``permissionDecision`` of ``null`` is not silence -- it is an opinion
    the harness has to interpret. When there is no decision the key is absent
    entirely, and only the reason rides along as a system message.
    """
    specific: dict[str, Any] = {"hookEventName": "PreToolUse"}
    if decision.permission is not None:
        specific["permissionDecision"] = decision.permission
        specific["permissionDecisionReason"] = decision.reason
    claude_out: dict[str, Any] = {"hookSpecificOutput": specific}
    if decision.permission is None and decision.reason:
        claude_out["systemMessage"] = decision.reason
    return json.dumps(claude_out)


def main(stdin_text: Optional[str] = None) -> int:
    """Read one hook event, print at most one decision, always exit 0.

    Exit 0 even on failure, deliberately. Exit 2 would block the tool call, and
    a hook that crashes on an input it did not expect must not take an
    unrelated tool call down with it -- principle 8, in the place where
    failing loudly would be worst. Anything this function cannot understand
    becomes silence, and the harness prompts exactly as it did before.
    """
    try:
        raw = sys.stdin.read() if stdin_text is None else stdin_text
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hook payload was not a JSON object")

        cwd = payload.get("cwd") or os.getcwd()
        decision = decide(payload, pr.load_layered_rules(cwd))
    except Exception as exc:  # noqa: BLE001 - see docstring
        decision = Decision(None, f"permission hook stood aside: {exc}")

    print(render(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
