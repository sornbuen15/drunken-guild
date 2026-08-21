# Kanban Board MCP Server

`kanban-server.js` is a [Model Context Protocol](https://modelcontextprotocol.io/) server that
exposes the local kanban board as 12 typed, atomically-safe tools. When registered in your
project's Claude Code settings, the LLM calls these tools as native function calls instead of
composing shell commands.

**Requirements:** Node.js v18 or v24 (same as the kanban CLI scripts)

---

## Installation

### 1. Register the MCP server in your project

Copy `templates/mcp-settings.json` from this toolkit and merge it into your project's
`.claude/settings.json`. Replace the placeholder path with the real absolute path to this toolkit.

```json
{
  "mcpServers": {
    "kanban-board": {
      "command": "node",
      "args": ["/ABSOLUTE/PATH/TO/drunken-ai-team/scripts/mcp/kanban-server.js"],
      "env": {
        "KANBAN_BOARD_DIR": ".claude/board",
        "KANBAN_CLAIM_TTL_SECONDS": "1800"
      }
    }
  }
}
```

`KANBAN_BOARD_DIR` is relative to the working directory where Claude Code is launched (your
project root). Change it if your board lives elsewhere.

`KANBAN_CLAIM_TTL_SECONDS` sets how long a claim is valid before it is considered stale and
auto-released on the next `board_summary` call. Default: 1800 seconds (30 minutes).

### 2. Verify the server starts

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}' \
  | KANBAN_BOARD_DIR=.claude/board node scripts/mcp/kanban-server.js
```

Expected response (on one line):
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"kanban-board-server","version":"1.1.0"}}}
```

---

## Tool Reference

| Tool | Arguments | Returns | Purpose |
|---|---|---|---|
| `board_next_id` | — | `{ id, nnn }` | Preview next task ID |
| `board_create_task` | `lane, slug, content` | `{ ok, id, path }` | Atomic task creation |
| `board_claim_task` | `task_id, agent_slug` | `{ ok, claimed_at }` or error | Atomic claim with identity check |
| `board_release_claim` | `task_id, agent_slug` | `{ ok }` | Release stale/abandoned claim |
| `board_move_task` | `task_id, target_lane, agent_slug` | `{ ok, from, to }` | Validated lane transition |
| `board_done_task` | `task_id, agent_slug` | `{ ok, id }` | Complete task |
| `board_get_task` | `task_id` | Task object with frontmatter | Full task data |
| `board_list_lane` | `lane` | Array of task summaries | Single-lane listing |
| `board_summary` | — | Multi-lane snapshot + counts | Full board state |
| `board_orchestrate` | `task_ids[]` | Wave plan | Dependency-resolved execution plan |
| `board_agent_context` | `task_id` | Compact handoff envelope | Token-efficient sub-agent briefing |
| `query_project_context` | `files[], keywords[]` | Matched sections array | Targeted context retrieval from project docs |

---

## Claim Lifecycle

Tasks transition through an intermediate `CLAIMED` state before moving to `in-progress`.
This prevents two concurrent agent sessions from both grabbing the same task.

```
UNCLAIMED (in todo/)
    │
    ▼  board_claim_task(task_id, agent_slug)
    │  Server validates:
    │    1. Task is in todo/
    │    2. assigned_to matches agent_slug
    │    3. claimed_at not already set (or is stale)
    │  Server writes: claimed_at, claimed_by to frontmatter
    ▼
CLAIMED (still in todo/, claimed_at set in file)
    │
    ▼  board_move_task(task_id, "in-progress", agent_slug)
    │  Server validates:
    │    1. claimed_by matches agent_slug
    │    2. No other in-progress/ task assigned to same agent (WIP=1)
    ▼
ACTIVE (in in-progress/)
    │
    ▼  board_done_task(task_id, agent_slug)
    ▼
DONE (in done/)

CLAIMED ──► board_release_claim(task_id, "principal-engineer")
         ──► UNCLAIMED  (PE override for abandoned sessions)
```

**Rejection reasons from `board_claim_task`:**

| `reason` | Meaning |
|---|---|
| `assignee_mismatch` | `assigned_to` does not match the requesting agent |
| `already_claimed_by: @agent at <ISO>` | Another session holds a live claim |
| `wrong_lane: <lane>` | Task is not in `todo/` |

**WIP rejection from `board_move_task`:**

| `reason` | Meaning |
|---|---|
| `not_claimed` | No prior `board_claim_task` call |
| `claim_owned_by: @agent` | Claimant and requester differ |
| `wip_limit_exceeded: TASK-NNN` | Agent already has a task in `in-progress/` |

---

## Orchestration Protocol

When the Principal Engineer needs to schedule a set of tasks, call `board_orchestrate` with
the list of `todo/` task IDs. The server reads each task's `depends_on` field, builds a
dependency graph, and returns a wave plan:

```json
{
  "total_tasks": 3,
  "waves": [
    {
      "wave": 1,
      "mode": "parallel",
      "depends_on_wave": null,
      "agent_conflict": false,
      "rationale": "2 tasks, 2 different agents, no mutual dependencies.",
      "tasks": [
        { "id": "TASK-003", "assigned_to": "@security-engineer", "title": "...", "priority": "HIGH" },
        { "id": "TASK-004", "assigned_to": "@qa-engineer", "title": "...", "priority": "HIGH" }
      ]
    },
    {
      "wave": 2,
      "mode": "sequential",
      "depends_on_wave": 1,
      "agent_conflict": false,
      "rationale": "Single task in this wave.",
      "tasks": [
        { "id": "TASK-005", "assigned_to": "@devops-engineer", "title": "...", "priority": "MEDIUM" }
      ]
    }
  ]
}
```

Tasks with `agent_conflict: true` in their wave require sub-sequencing within the wave —
the same agent cannot hold two `in-progress` tasks simultaneously.

---

## Context Retrieval Protocol

`query_project_context` lets agents pull only the relevant sections from project documentation
files instead of reading whole files upfront. This prevents "Lost in the Middle" recall
degradation caused by loading large context files early in the session.

**Arguments:**

| Argument | Type | Description |
|---|---|---|
| `files` | `string[]` | One or more filenames. Short names (e.g. `'POLICY.md'`) are resolved to `.claude/` automatically. |
| `keywords` | `string[]` | Keywords to match against Markdown section headings and body text. |

**Returns:**

```json
{
  "results": [
    {
      "file": "POLICY.md",
      "section_title": "## Rate Limiting Rules",
      "content": "...",
      "line_start": 42,
      "truncated": false
    }
  ],
  "total_matches": 1
}
```

Up to 60 lines of content are returned per matched section. If no section heading matches,
the tool falls back to returning the ±3 lines surrounding each keyword occurrence.

**Recommended call patterns:**

```js
// Phase 1: Load compliance gates before any analysis
query_project_context({ files: ['POLICY.md'], keywords: ['rule', 'constraint', 'required', 'forbidden'] })

// Phase 2: Load architecture rules only when checking layering
query_project_context({ files: ['ARCHITECTURE.md'], keywords: ['layer', 'dependency', 'module', 'boundary'] })

// Phase 3: Load feature spec only when a specific feature is under review
query_project_context({ files: ['PROJECT_SPEC.md'], keywords: ['payment', 'checkout'] })
```

---

## Fallback: CLI Scripts

The MCP server is the primary board interface. The kanban CLI scripts
(`scripts/kanban/kanban_read.sh`, `kanban_write.sh`, and their `.ps1` equivalents) remain
available as a fallback for CI pipelines, debugging, or non-Claude-Code environments.
Both interfaces share the same `BOARD_DIR` and the same `.kanban.lock` file, so they are
safe to use interchangeably.
