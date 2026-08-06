# Drunken-Team: AI Integration Guide

This guide is for connecting a local AI coding tool (Claude Code, Cursor, Aider) to Drunken-Team, so it can read and update Jira directly and hand off to the Discord daemon instead of you doing it by hand.

---

## 1. The MCP Servers

Drunken-Team exposes two separate MCP servers -- there is no single combined server or `drunken-mcp` binary.

### `drunken-jira-mcp` -- Jira operations
- **Tools:** `jira_search_issues(jql)`, `jira_create_issue(summary, description)`, `jira_transition_issue(issue_key, target_status)`, `jira_add_comment(issue_key, comment)`, `jira_start_task(issue_key)` (transition to In Progress + the git branch command to run), `jira_submit_for_review(issue_key, pr_link, files_changed)` (transition to In Review + comment the PR link).
- **Resources:** `jira://board`, `jira://issue/{issue_key}`, `jira://project/{project_key}/board`.
- **Prompts:** `jira_daily_standup`, `init_project`, `refinement`, `sprint_planning`, `review_retro`.
- Full reference: [`src/jira_mcp/README.md`](./src/jira_mcp/README.md).

### `drunken-discord-mcp` -- approvals
- **Tool:** `request_boss_approval(action, reason, ticket_key)`. Blocks until the Boss reacts 👍/👎 on Discord and returns the result directly -- there is no file-polling or "end your turn and wait" step involved.

Both are registered for you already in `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "drunken-discord-mcp": { "command": "uv", "args": ["run", "--directory", "/path/to/drunken-team", "drunken-discord-mcp", "--workspace", "/path/to/your-project"] },
    "drunken-jira-mcp": { "command": "uv", "args": ["run", "--directory", "/path/to/drunken-team", "drunken-jira-mcp", "--workspace", "/path/to/your-project"] },
    "drunken-board-mcp": { "command": "uv", "args": ["run", "--directory", "/path/to/drunken-team", "drunken-board-mcp", "--workspace", "/path/to/your-project"] }
  }
}
```

If your tool auto-discovers project-level `.mcp.json`, you're done. Otherwise, point it at the same two commands manually (Section 4 below has a worked example for Cursor).

---

## 2. Local AI Configuration Templates

`.guild_templates/` holds rulebook templates for each tool, meant to be copied into a project's root:

| File | Tool | What it enforces |
|---|---|---|
| `CLAUDE.md` | Claude Code | Check Jira before starting work, never push to `main`, call `request_boss_approval` instead of executing destructive commands unasked, run `pytest`/`mypy`/`pre-commit` before finishing. |
| `.cursorrules` | Cursor | Same rules, phrased for Cursor's MCP integration. |
| `CONVENTIONS.md` | Aider | Same rules, plus commit-message and mocking (`autospec=True`) conventions Aider should follow. |
| `SESSION_CHECKPOINT.md` | All | A blank template for cross-session context handoff -- read at the start of a session, updated before ending one. |

None of these describe Drunken-Team's own internals in depth; they just tell the local AI which Jira/MCP calls to make and when to ask for approval instead of acting.

---

## 3. Workflow Handoff

The collaboration between your local AI tool and the Guild's Discord daemon follows the same lifecycle either from the CLI or via MCP:

1. **Intake:** Call `jira_start_task(issue_key)` (or `jira_bridge.py transition <key> "In Progress"`) to claim a ticket and get the branch name to check out.
2. **Execution:** Write code and tests against that ticket's acceptance criteria. Call `request_boss_approval` before any destructive or merge-worthy action.
3. **Handoff:** Push the branch, open a PR, then call `jira_submit_for_review(issue_key, pr_link, files_changed)` to move the ticket to In Review with the PR linked.
4. **Validation:** The round-integration QA gate (`scripts/qa_automation.py`, triggerable from Discord with `/qa`) picks up every In Review ticket, reruns the full suite with all of them merged together, and transitions to Done (or back to In Progress with a failure report) accordingly.

---

## 4. Integrating an Existing (Non-Drunken-Team) Project

To bring an existing project under this same workflow:

### Step 1: Install Drunken-Team's CLI tools

```bash
git clone https://github.com/sornbuen15/drunken-team.git
cd drunken-team
uv tool install .
```

This installs four commands globally: `drunken-listen` (run the Discord daemon), `drunken-register` (provision a project), `drunken-jira-mcp` and `drunken-discord-mcp` (the two MCP servers).

### Step 2: Register the project

```bash
cd /path/to/existing-project
drunken-register .
```

You'll be prompted for the Jira URL, email, project key, and API token, plus the Discord bot token and channel ID (it reuses drunken-team's own Discord config if found). This writes `.agents/jira.json` and `.agents/discord_config.json` in the target project.

Then add the project to Drunken-Team's own registry so `/project <name>` in Discord can target it (see [Drunken-Team-Guide.md, Section 7](./Drunken-Team-Guide.md#7-multi-project-orchestration)):

```json
// drunken-team/.agents/projects.json
{
  "existing-project": { "path": "/path/to/existing-project", "description": "..." }
}
```

### Step 3: Copy the AI templates

```bash
cp /path/to/drunken-team/.guild_templates/CLAUDE.md .
cp /path/to/drunken-team/.guild_templates/.cursorrules .
cp /path/to/drunken-team/.guild_templates/CONVENTIONS.md .
cp /path/to/drunken-team/.guild_templates/SESSION_CHECKPOINT.md .
```

### Step 4: Point your tool's MCP config at the two servers

For Cursor: **Settings > Features > MCP > Add New Server**, type `command`, and set the command to `uv run --directory /path/to/drunken-team drunken-jira-mcp --workspace /path/to/your-project` and a second entry the same way for `discord_mcp`. For Claude Code, copying `.mcp.json` from drunken-team's root into the existing project (adjusting the paths to point to drunken-team and your project's workspace) is usually simplest.

From here, your local AI reads `CLAUDE.md`/`.cursorrules`, checks Jira via the MCP tools, writes code, and hands off through the same lifecycle described in Section 3.

---
*This document covers integration and handoff only. For Drunken-Team's own architecture and day-to-day Discord commands, see [Drunken-Team-Guide.md](./Drunken-Team-Guide.md).*
