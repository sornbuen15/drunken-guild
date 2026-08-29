---
name: "ask-boss"
description: "Ask the Boss for permission without stopping: submit the question, park the task, keep working on what isn't blocked, and collect the answer at the next task boundary."
---

# Skill: Ask the Boss for Permission
**Version:** 4.1.0

## First, can the Boss see this conversation right now?

If you're in a live session and the Boss is reading your responses, just ask
them here. Plainly, like normal conversation. Everything below is for when
they are **not** watching — a dispatched run, or they've stepped out.

## The rule that matters most

**Asking must not stop you working.**

Waiting for the Boss to be free is not a failure, and it must not cost the
other tasks that were ready to run. If you take one thing away from this
skill: never sit and wait for an answer.

## The loop

There is no local board (DG-265) — nothing here reads or writes one, and no `board_*` tool
exists to call. "Parking" a task means exactly what it sounds like: don't perform the action, say
in your own output that it's waiting on an answer, and move to whatever else is available. Jira's
own status/assignee is the only record of what's in flight; there is no second one to keep in sync.

1. **Ask** with `request_boss_approval_async(action, reason, ticket_key)`.
   It returns a `req_id` immediately.
2. **Don't perform the action you just asked about.** Note the `req_id` and move on — there is
   nothing to call to mark the task blocked; you're simply not doing that step yet.
3. **Pick up the next thing** — the next unblocked ticket, or whatever else the current task
   doesn't depend on. Nothing here hands you one; choose it the way you normally would.
4. **Finish what you started.** An answer arriving is never a reason to
   abandon work half-done — see below.
5. **Collect answers at the boundary** with `check_approvals([req_id, ...])`
   when a task finishes, and at the start of every session.
   - `approved` → do exactly the approved action.
   - `rejected` → leave it and respect the reason. Do not re-ask the
     same question hoping for a different answer.
   - `pending` → leave it, carry on with something else.
   - `stale` → it was approved against different code. Ask again.
   - `unknown` → never submitted, or lost. Re-submit; do not guess.
6. **Nothing available?** Say which `req_id`s are still outstanding and what
   they're waiting on, then **end your turn**. Do not poll in a loop. Do not
   schedule a wake-up just to check. The next session picks it up at step 5.

## Check at task boundaries — never mid-task

Collect answers when you *finish* something, not when one happens to arrive.
Interrupting yourself to act on an approval leaves the current task
half-done, and half-done work is how a repository ends up in a state nobody
can reason about. Finish, then collect, then choose what's next.

## There is no timeout, and nothing gets killed

Unanswered requests stay pending for as long as it takes. The Boss is
reminded at a decreasing rate — 15 minutes, an hour, then daily. A question
they haven't got to yet is not an error condition, and the work is never
thrown away for it.

## An approval covers the code it was granted for

Approvals are bound to the commit that was current when you asked. If the
code has moved on, `check_approvals` reports `stale` rather than `approved`.
That is deliberate: a yes given this morning must not silently authorise
this evening's different change. Ask again.

## Some things no approval can grant

Force-push, hard reset, `rm -rf`, and reading `.env` are refused by the
permission layer regardless of what comes back over Discord. Do not attempt
to route around that — if one of those is genuinely needed, it is a
conversation to have with the Boss directly, not a tool call to retry.

## When Discord isn't there

If the tools report the daemon is unreachable, that is **not** permission to
skip approval. Ask the Boss directly in the conversation if you're in one.
If you are genuinely unattended with no way to reach them, park the task and
say so — the request is preserved and picked up next session.

## Still blocking, still supported

`request_boss_approval` (the original, blocking call) still works and still
escalates after two unanswered reminders. Prefer the async pair. Reach for
the blocking one only when there is genuinely nothing else you could be
doing and the answer decides whether the session continues at all.

## Never touch the internals

Do not read or write the daemon's approval state directly. It lives at
`$DRUNKEN_HOME/approvals-<project>.json` (default `~/.drunken/`), one file per project since
DG-318 -- the daemons share a state directory, so a machine-wide file let whichever wrote last
erase the others' answers.
It is daemon state, not an API — go through the tools. The pre-DG-232/DG-243 equivalent,
`.agents/discord_outbox.json`, is retired <!-- drift-ok: the prohibition has to name what it prohibits -->; if you find one in an older
project, it is not read by anything current.
