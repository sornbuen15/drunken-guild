# Retired — `kanban-io`

**Retired:** 2026-08-22 · **Was:** `skills/kanban/kanban-io/` · **Replaced by:** nothing. Skills
call `drunken-jira-mcp` directly.

## Why

This skill called itself "the required gatekeeper for all board operations" — the only thing
permitted to read or write `.claude/board/`. There is no `.claude/board/` any more. Jira is the
only coordination surface, and the gate it guarded no longer exists.

There is deliberately **no `jira-io` successor**. The gatekeeper existed because the board was a
directory of Markdown files that any skill could corrupt with a stray `mv`; a single typed
interface in front of it was worth the indirection. `drunken-jira-mcp` is already that typed
interface, one layer down. Wrapping it in a second one would buy nothing and give the rules a
second place to drift.

Skills that used to route through here now call the MCP tools themselves — `jira_create_issue`,
`jira_search_issues`, `jira_transition_issue`, and the rest, listed in `CLAUDE.md`.

## What it referenced that is also retired

`scripts/mcp/kanban-server.js`, `scripts/kanban/kanban_read.sh`, `scripts/kanban/kanban_write.sh`,
`templates/mcp-settings.json`. All nine `board_*` tools were defined by that server.
