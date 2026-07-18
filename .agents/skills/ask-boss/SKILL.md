---
name: "ask-boss"
description: "Actively asks the Boss for permission or clarification via Discord using a blocking approval call."
---

# Skill: Ask Boss for Permission / Clarification
**Version:** 3.1.0

## First, ask yourself: can the Boss see this conversation right now?
If you're in a live, interactive session and the Boss is reading your
responses directly — just ask them here, plainly, like normal conversation.
Don't reach for Discord at all in that case; it's extra friction for no
reason. `request_boss_approval` exists for when they're **not** watching
this conversation (a dispatched/background task, or they've stepped away)
and you need a channel that reaches them anyway.

Not every setup even has Discord configured, or has the daemon running at
that moment — the tool handles that gracefully and tells you to fall back
to asking directly here. That fallback is not "skip approval"; it's "get
approval a different way."

## When to use `request_boss_approval` specifically:
- You are running unattended (dispatched, no one reading this conversation
  live) and need to reach the Boss anyway.
- You are about to run a potentially dangerous command but want explicit
  approval, and you don't know whether anyone's watching right now.
- The Boss has asked to be notified via Discord specifically, even while
  you're in an interactive session.

## How to use:
Call the `request_boss_approval` MCP tool directly:

```
request_boss_approval(
  action="npm run destroy",
  reason="Clearing the staging DB before the migration test.",
  ticket_key="DT-123",
)
```

- `ticket_key` is required — it's how an escalation gets commented onto the
  right Jira ticket and how the pre-commit safety net knows what to block.
- **This call blocks.** It does not return until the Boss has answered, or
  the request is auto-escalated after 2 unanswered reminders. Do NOT call
  `schedule` and end your turn to "check back later" — that pattern is
  retired. Just call the tool and wait for its return value like any other
  tool call.
- Do NOT write directly to `.agents/discord_outbox.json` or read
  `.agents/discord_inbox.json` yourself — those are internal daemon state,
  not an API. Always go through the tool.

## What the return value means:
- `"Approved by Boss."` — proceed.
- `"Rejected by Boss."` — stop; do not take the action.
- `"No response after 2 reminders — task stopped..."` — the daemon has
  already killed this task, commented on the Jira ticket, and notified the
  Boss on Discord. Treat this as a hard stop: do not continue, do not retry,
  do not commit anything.
- `"Discord approval is unavailable right now..."` — the daemon isn't
  running or isn't set up. Do not treat this as "skip approval" and do not
  treat it as a dead end either: if you're in an interactive session, ask
  the Boss directly in this conversation instead. Only stop outright if you
  are genuinely unattended with no one to ask at all.
