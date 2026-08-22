# Retired — the `board/` fixtures from examples 01 and 02

**Retired:** 2026-08-22 · **Was:** `examples/01-spec-to-backlog/board/`,
`examples/02-backlog-refinement/board/` · **Replaced by:** the Jira ticket examples now written
directly into each stage's `README.md`.

Unlike examples 04 and 05, the skills these belonged to survive — `spec-to-backlog` and
`backlog-refinement` both run on Jira now. Only the recorded output was wrong: it showed
`.claude/board/<lane>/TASK-NN.md` files, which is the local board `CLAUDE.md` forbids.

The fixtures themselves are kept because they are the concrete record of the old task-file
format — the YAML frontmatter with `priority`, `assigned_to`, `depends_on` and `blocks` — and
three of those four fields have no equivalent in the Jira the project actually has:

- `priority` cannot be set on a team-managed project. Urgency is a **label** now.
- `depends_on` / `blocks` fed `board_orchestrate`, the wave scheduler, which is retired and was
  deliberately not rebuilt. A real prerequisite goes in the ticket's SCOPE as prose.
- `assigned_to` was set at creation. In Jira the **assignee** means "who is working this now",
  so a newly created ticket has none; the intended specialist rides along as an
  `agent:<slug>` label until someone actually picks it up.

Reading these next to the new stage READMEs is the shortest way to see what changed and why.
