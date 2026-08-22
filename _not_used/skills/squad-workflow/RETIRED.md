# Retired — `squad-workflow`

**Retired:** 2026-08-22 · **Was:** `skills/workflow/squad-workflow/` · **Replaced by:** the
status ladder in `CLAUDE.md`, and `agents/principal-engineer.md` for sequencing.

## Why

It was a coordination protocol whose gates were board operations. Its phase 1b —
"Orchestration Planning" — ran `board_orchestrate` to compute waves, `board_agent_context` per
task, then per wave `board_claim_task` → spawn → `board_move_task` → `board_done_task`. Every
primitive in that loop is retired, and re-implementing the loop against Jira was considered and
rejected: it would rebuild the second coordination surface this migration exists to remove.

What replaces it is smaller and lives where it is already enforced:

- **Order of states** — `TODO → IN PROGRESS → IN REVIEW → DONE`, never skipping `IN REVIEW`, is
  in `CLAUDE.md` as a FATAL directive. It does not need a skill to restate it.
- **Who does what** — the Jira **assignee**, set by `jira_assign`.
- **Which specialist, in what order** — `agents/principal-engineer.md`, as explicit sequential
  steps rather than a wave planner.

Its `<phase>` gates that were about human judgement rather than board writes — user approves the
task plan before promotion, QA before deploy — are worth re-reading before anyone writes a
successor.
