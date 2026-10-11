"""Discord, reduced to a notice board.

What this replaces asked a question and waited for the answer: a daemon, a
socket, an approval state machine, and a hook that blocked a tool call until a
👍 arrived. The 2.0.0 target keeps none of that — Remote Control is where a
Claude session is watched, and Jira plus pull requests are the shared screen for
everything else. What Discord is still good at is being the place a phone
buzzes: **PR ready, today's MVP, the gaps an audit found, an agent that needs a
decision.** Four events, one direction, each carrying a link.

Three properties, and each of them is the opposite of how the approval path
behaved:

**Nothing waits on this.** A notification that cannot be sent is not a reason to
fail a build, stall a hook, or raise into a caller that was doing something
else. Every path here returns a :class:`Notification` instead of raising.

**A failure stays visible.** Nobody is blocked when a notification goes
missing, which is exactly why silence is dangerous: ``sent=False`` always
carries a ``reason``. "Could not send" and "nothing to send" are different
answers — collapsing them is how a board read as empty for months (S4).

**The URL is a credential.** Anyone holding a webhook URL can post as the bot,
so it arrives as a *reference* (``env://…``, ``file://…#key``) and is registered
for redaction the moment it resolves. That matters most on the failure path:
``urllib`` builds the full URL into ``HTTPError``'s own string form, so the
obvious ``str(exc)`` reason would publish the token the first time Discord
answers 404.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from typing import Final, Optional

from . import secrets
from .errors import DrunkenError
from .http import open_url, validate_url
from .redact import redact

#: Explicit and named, which is why it wins over the registry — it is how a
#: container or a CI job passes a different room in. Holds a *reference*, not a
#: URL: the value is a credential wherever it is written down.
ENV_WEBHOOK: Final = "DRUNKEN_DISCORD_WEBHOOK"

#: Short. A notification is never on the critical path, and a hook holding a
#: socket open for a minute costs more than the message is worth.
TIMEOUT_SECONDS: Final = 10

NO_WEBHOOK = (
    "No Discord webhook is configured, so nothing was sent. Set {env} to a "
    "reference (for example 'env://DISCORD_WEBHOOK_URL'), or give the project "
    "a 'discord.webhook' reference in the registry. Notifications are optional: "
    "a project with none is not misconfigured."
)

NO_LINK = (
    "Refused to send: the notification carries no link. Every event this is "
    "for — a pull request, today's MVP, an audit, a decision — is only "
    "actionable because it points somewhere."
)


@dataclass(frozen=True)
class Notification:
    """What happened to one message. Never an exception."""

    sent: bool
    reason: str = ""


def webhook_reference(registry_ref: Optional[str] = None) -> Optional[str]:
    """Which reference to resolve, by the project's fixed config precedence.

    Environment variable, then the registry. Nothing discovers a file by
    climbing the tree, and there is no third source — the ``.env`` that used to
    arrive disguised as rule 1 is exactly what that precedence exists to stop.

    ``None`` means no webhook is configured, which is a supported state rather
    than an error: notifications are optional.
    """
    explicit = os.environ.get(ENV_WEBHOOK, "").strip()
    if explicit:
        return explicit
    return registry_ref or None


def notify(
    headline: str,
    link: str,
    webhook_ref: Optional[str] = None,
    timeout: float = TIMEOUT_SECONDS,
) -> Notification:
    """Post one line and its link to Discord. Never raises.

    *webhook_ref* is a secret reference; when omitted it is resolved through
    :func:`webhook_reference`.
    """
    reference = webhook_ref or webhook_reference()
    if not reference:
        return Notification(False, NO_WEBHOOK.format(env=ENV_WEBHOOK))

    if not link.strip():
        return Notification(False, NO_LINK)

    try:
        # Resolving registers the value for redaction (core.redact.Secret does
        # it in its constructor), which is what makes the `redact` calls below
        # able to mask a URL they never saw.
        url = secrets.resolve(reference).reveal()
        validate_url(url)
        request = urllib.request.Request(  # nosec B310 - scheme checked above
            url,
            data=json.dumps({"content": f"{headline}\n{link}"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with open_url(request, timeout):
            pass
    except DrunkenError as exc:
        remediation = getattr(exc, "remediation", "") or ""
        return Notification(False, redact(f"{exc} {remediation}".strip()))
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        return Notification(False, redact(f"Could not send the notification: {exc}"))

    return Notification(True)


def main(argv: Optional[list[str]] = None) -> int:
    """``python -m core.notify`` — what CI and the hooks call.

    **Always exits 0.** A notification that did not arrive is worth reporting
    and is not worth failing a pipeline over; the reason goes to stderr where a
    job log keeps it.
    """
    parser = argparse.ArgumentParser(
        prog="python -m core.notify",
        description="Send one Discord notification. One line, one link, no reply.",
    )
    parser.add_argument("headline", help="One line saying what happened.")
    parser.add_argument("--link", required=True, help="Where to go to act on it.")
    parser.add_argument(
        "--webhook",
        default=None,
        help=f"Webhook reference. Defaults to ${ENV_WEBHOOK}.",
    )
    args = parser.parse_args(argv)

    result = notify(args.headline, args.link, webhook_ref=args.webhook)
    if result.sent:
        print("Notification sent.")
    else:
        print(f"Notification not sent: {result.reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
