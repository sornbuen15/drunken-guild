# Workspace Rules for Antigravity

> **This is a template.** Copy it to `~/.gemini/config/AGENTS.md`. It is authored in
> `drunken-guild`'s `templates/AGENTS.md`; the installed copy is the operator's to change.
>
> It is the **global** file, read across every project. It therefore carries as little as
> possible: a global file that states a rule is a global file that can contradict the project
> stating the same rule differently, and the global one is usually read first.

---

## This file defers. It does not decide.

Every project this toolkit reaches carries its own `AGENTS.md` — at the project root or under
`.agents/` — and **that file is the authority** on how to work there: approvals, git, tickets,
what must never be deleted.

When the two disagree, the project's file wins. When this file is silent, that is deliberate.

## Approvals

**Read the project's `AGENTS.md` and the `ask-boss` skill. Do not act from memory here.**

The protocol has changed once already, and the change is exactly the kind a stale global file
keeps alive: approvals used to mean *write a file, schedule a wake-up, and end your turn*. That
is retired. An agent that ends its turn to wait is an agent doing nothing while unblocked work
sits in the backlog.

Two things hold everywhere and are safe to state globally:

- **Never end your turn to wait for an answer.** Submit the question, park that task, take the
  next unblocked one, and collect the answer at a task boundary — never mid-task.
- **A deny rule is not negotiable.** Force-push, hard reset, recursive force-delete and reading
  `.env` are refused by the harness regardless of what any remote approval says. Do not route
  around one; raise it with the Boss.

## Deleting

An agent does not delete. Retired things move aside with a note saying why and what replaced
them, and *marking a thing unused beats removing it*.

Anything that would need a recursive force-delete becomes a **list handed to the Boss to run** —
a markdown table of path and exact command, for a human to execute. An authorisation recorded in
an earlier session is not permission to delete today.

## Permissions

Prefer the narrowest rule that unblocks the work, and anchor it. An allow entry written as a
relative path applies in every working directory, including the one where it means something
very different — `agents skills` names two ordinary directories in most repositories and the
entire deliverable in one of them.

## MCP servers

The servers this toolkit installs are written by `drunken-config` into the host config it
manages. **A server added beside them by hand is unmanaged**: nothing checks that it still
resolves, and nothing notices when it starts answering a question one of ours already answers.

`drunken-doctor` reports both. Read it before assuming a host config is healthy.
