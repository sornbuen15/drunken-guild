# Drunken Jira MCP Server

This is a Model Context Protocol (MCP) server for integrating Jira into AI Agent workflows. It exposes tools and resources that allow AI agents to securely query, create, and transition Jira issues.

## Prerequisites

- Python 3.10+
- A Jira Cloud account with an API Token.

## Installation

If you are using this within the `drunken-guild` project, the dependencies are already managed via `pyproject.toml`.
To install the server and its command-line shortcut into your environment:

```bash
pip install -e .
```

This will make the `drunken-jira-mcp` command available in your terminal.

## Configuration

The server reads its Jira connection from the **project registry** under `$DRUNKEN_HOME`, selected
by the project id **each tool call names** — the server itself is started with no project at all
(DG-341). It reads no `.env` and no per-project JSON file. Register a project once with
`drunken-init`; the credential is a reference (`file://…#key`, `env://VAR`, …), never the token
itself:

```bash
drunken-init --project my-project --jira-url https://your-domain.atlassian.net \
  --jira-email you@example.com --jira-project-key XYZ \
  --jira-credential 'file://~/.drunken/secrets.json#jira.default'
uv run python scripts/set_secret.py jira.default     # the token, at a hidden prompt
drunken-doctor --project my-project                   # proves it authenticates
```

The full walk-through, including why a reference and not a token, is
[Drunken-Guild-Guide.md §3.3](../../Drunken-Guild-Guide.md#33-configure-credentials).

## How to Run & Test (Human Developer)

You can test the MCP server visually using the official MCP Inspector.

**If you have installed the package (`pip install -e .`):**
```bash
npx @modelcontextprotocol/inspector drunken-jira-mcp
```

**If you want to run it directly without installing:**
```bash
PYTHONPATH=src npx @modelcontextprotocol/inspector python -m jira_mcp.server
```

Once the inspector starts, open the provided localhost URL in your browser, click "Connect", and you will be able to test the Jira tools and resources interactively.

## Connecting to an AI Agent

To use this server with an AI assistant (Claude Code, Claude Desktop, Cursor, …), add it to that assistant's MCP configuration file (e.g., `.mcp.json` or `claude_desktop_config.json`).

Example configuration:
```json
{
  "mcpServers": {
    "drunken-jira-mcp": { "command": "drunken-jira-mcp" }
  }
}
```

**The same entry works for every project, and that is deliberate.** Each tool takes the registry
project id as its first argument, so nothing here decides which Jira is reached. It used to: a
config carrying `--project` registered at *user* scope reached every session on the machine and gave
them all one project's board while reporting success (DG-341). A missing or unknown id is refused
with the registered ids named, never guessed.

## Available Features for Agents

Once connected, the AI Agent will automatically discover the following capabilities:

### Tools (Actions)
- `jira_search_issues`: Query issues dynamically using JQL.
- `jira_create_issue`: Create new tickets on the board.
- `jira_transition_issue`: Move a ticket's status (e.g., 'To Do' -> 'In Progress').
- `jira_add_comment`: Add a comment to an existing ticket.
- `jira_edit_labels`: Add and/or remove labels on one ticket, leaving the others. Sent as add/remove operations, never as a replacement set, so two agents cannot drop each other's label (DG-368).
- `jira_edit_issue`: Correct the summary and/or description of one ticket. Only the fields passed are sent; an empty argument is left unchanged, never cleared (DG-367).
- `jira_start_task`: Pick up an issue and transition it to 'In Progress' in one call.
- `jira_submit_for_review`: Transition an issue to 'In Review' and attach a PR link.
- `jira_assign`: Set or clear an issue's assignee. With the local board retired (DG-250), this is how an agent says "this one is mine".
- `jira_board_info`: What this project's board is and what it can do -- id, name, type, and whether it has a backlog. Capability is **probed, not inferred from type**: a `kanban` board may have no backlog while a team-managed `simple` board has one.
- `jira_move_to_backlog`: Move active issues off the board and into its backlog.
- `jira_move_to_board`: The way back out of the backlog.

The two move tools accept several keys at once (comma- or space-separated, at
most 50 per call, which is Jira's limit) and refuse a key from any other
project before sending anything -- the underlying `/rest/agile/1.0` endpoints
take any key from any project and would move it without complaint.

**Neither move changes status.** An issue parked in the backlog keeps the
status it had; only where it appears changes. Use `jira_transition_issue` for
status.

### Resources (Context Reading)
- `jira://board`: Instantly fetches the active board (To Do, In Progress, In Review) for the configured default project.
- `jira://issue/{issue_key}`: Fetches deep JSON details of a specific ticket.
- `jira://project/{project_key}/board`: Same as `jira://board`, but for a specific project key instead of the configured default.

### Prompts

Each prompt names the skill that owns its process and says to stop if that skill is not
installed. None of them describes the process itself — that was five more places for a rule to be
written differently, and they were (DG-339). `tests/test_jira_mcp_prompts.py` holds every prompt to
it, including any added later.

| prompt | owned by |
|---|---|
| `jira_daily_standup` | `audit` (`/audit`) |
| `init_project` | `prd` (`/prd`), the first step of the flow |
| `refinement` | `jira-tickets` — which tickets move onto the board is the Boss's decision, not a skill's |
| `sprint_planning` | `breakdown` (`/breakdown`) |
| `review_retro` | `audit` (`/audit`) |
