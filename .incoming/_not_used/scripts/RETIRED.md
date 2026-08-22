# Retired — the local board implementation

**Retired:** 2026-08-22 · **Was:** `scripts/kanban/`, `scripts/mcp/` · **Replaced by:**
`drunken-jira-mcp`, which lives in `~/Projects/drunken-team` and is declared per project in that
project's `.mcp.json`.

## What is here

| path | was | what it did |
|---|---|---|
| `mcp/kanban-server.js` | `scripts/mcp/kanban-server.js` | JSON-RPC 2.0 MCP server defining all nine `board_*` tools |
| `mcp/README.md` | `scripts/mcp/README.md` | setup guide and tool reference for that server |
| `kanban/kanban_read.sh` · `.ps1` | `scripts/kanban/` | CLI fallback — read board state |
| `kanban/kanban_write.sh` · `.ps1` | `scripts/kanban/` | CLI fallback — create and move tasks |
| `kanban/kanban.js` | `scripts/kanban/` | unified cross-platform CLI (Node 18+) |
| `../templates/mcp-settings.json` | `templates/` | copy-paste registration snippet for the server above |

## Why

A local board sitting next to Jira is a second coordination surface, and two surfaces can
disagree. Jira is now the only one: the **assignee** says whose work a ticket is, the **status**
says where it is, and nothing else tracks either.

What is genuinely lost is **claim expiry**. `board_claim_task` took a lease the server released
after 1800s, so an agent that died did not strand a task. A Jira assignee never expires. That is
a ten-second fix by a human, weighed against a class of silent disagreement that costs weeks.

`templates/mcp-settings.json` goes with them because it exists only to register the server above.
A project needing MCP registration today declares `drunken-jira-mcp` in its own `.mcp.json`; the
server is not authored in this repo and neither is its config.

## Related

- `../skills/kanban-io/RETIRED.md` — the skill that was this code's only supported caller
- Branch `wip/kanban-server-jira-sync`, commit `fc1a93c` — an unmerged 182-line Jira write-through
  for `kanban-server.js`. **Not revived, deliberately.** It made the board primary and Jira its
  mirror, which is the wrong direction; its commit message records the two defects it carries.
