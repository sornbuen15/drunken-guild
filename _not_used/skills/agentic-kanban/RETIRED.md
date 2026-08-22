# Retired — `agentic-kanban`

**Retired:** 2026-08-22 · **Was:** `skills/kanban/agentic-kanban/` · **Replaced by:**
`issue-intake` and `spec-to-backlog` for the triage half; nothing for the orchestration half.

## Why

Two jobs lived in one skill, and only one of them survives the move to Jira.

**Triage — kept, elsewhere.** "A bug arrives, classify it, write it down" is still real work.
It is done by `skills/kanban/issue-intake` (`/issue`) for a reported problem and
`skills/kanban/spec-to-backlog` (`/init-project`) for a spec, both of which were moved onto
`jira_create_issue` in `eaf5947`. Its "no immediate coding — triage first" rule and its
read-only pre-flight investigation for bugs both survive in `issue-intake`.

**Orchestration — cancelled.** Deciding which agent runs when, and promoting tasks through
lanes on their behalf, was a board concept. On Jira the **assignee** says whose work a ticket is
and the **status** says where it is; `jira_assign` sets the first and `jira_start_task` /
`jira_submit_for_review` / `jira_transition_issue` set the second. Nothing needs a skill to
route between them.

Its lane promotions were also a literal `board_move_task`, which does not translate: in Jira,
board-vs-backlog membership and status are two separate axes, and `jira_move_to_backlog` changes
membership only.
