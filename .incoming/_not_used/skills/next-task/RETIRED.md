# Retired — `next-task`

**Retired:** 2026-08-22 · **Was:** `skills/kanban/next-task/` · **Replaced by:**
`jira_daily_standup` + `jira_start_task`, called directly.

## Why

The skill did three things. One is gone, one is a single MCP call, and one belongs to the agent
anyway.

**Atomic claim — gone, and this is the one real loss.** `board_claim_task` took a lease that the
server released after 1800s, so an agent that died did not strand a task. A Jira assignee never
expires: if an agent stops mid-ticket, the ticket stays assigned until a human reassigns it. That
is a ten-second fix, accepted deliberately in exchange for removing a second surface that could
disagree with Jira.

**Priority pick — one call.** `jira_daily_standup` returns the working set; CRITICAL/HIGH/
MEDIUM/LOW now live as **labels**, because `priority` cannot be set on a team-managed project.
Then `jira_start_task`.

**WIP = 1 — not a skill.** It was enforced by the board server rejecting a second
`board_move_task` into in-progress. Jira does not enforce it and should not learn to; an agent
finishing what it started is a working habit, not a lane rule.

Also note its flow ran in-progress → done. `CLAUDE.md` says in bold to never skip `IN REVIEW`,
including for your own work, so the flow was wrong independently of the board.
