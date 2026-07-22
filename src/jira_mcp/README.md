# Drunken Jira MCP Server

This is a Model Context Protocol (MCP) server for integrating Jira into AI Agent workflows. It exposes tools and resources that allow AI agents to securely query, create, and transition Jira issues.

## Prerequisites

- Python 3.10+
- A Jira Cloud account with an API Token.

## Installation

If you are using this within the `drunken-team` project, the dependencies are already managed via `pyproject.toml`.
To install the server and its command-line shortcut into your environment:

```bash
pip install -e .
```

This will make the `drunken-jira-mcp` command available in your terminal.

## Configuration

Before running the server, you **must** configure your Jira credentials. The server looks for configuration in the following order:

1. **Environment Variables** (or a local `.env` file in your project root)
2. **Local JSON config**: `.agents/jira.json`
3. **Global JSON config**: `~/.gemini/config/jira_config.json`

### Option A: Using a `.env` file (Recommended)
Copy the repo-root `.env.example` template (`cp .env.example .env`) and fill it in, or create a `.env` file at the root of your project with these variables directly:

```env
JIRA_URL="https://your-domain.atlassian.net"
JIRA_EMAIL="your-email@example.com"
JIRA_API_TOKEN="your-jira-api-token"
JIRA_PROJECT_KEY="DT"
```
*(Note: You can also use `JIRA_TOKEN` instead of `JIRA_API_TOKEN`)*

### Option B: Using `.agents/jira.json`
Create a `.agents/jira.json` file in your project with the following structure:

```json
{
  "jira_url": "https://your-domain.atlassian.net",
  "jira_email": "your-email@example.com",
  "project_key": "DT"
}
```
*(The API Token will still be read from the environment variables or the global config for security reasons).*

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

To use this server with an AI Assistant (like Antigravity or Claude Desktop), you need to add it to your agent's MCP configuration file (e.g., `mcp.json` or `claude_desktop_config.json`).

Example configuration:
```json
{
  "mcpServers": {
    "jira-mcp": {
      "command": "python",
      "args": ["-m", "jira_mcp.server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/drunken-team/src"
      }
    }
  }
}
```

## Available Features for Agents

Once connected, the AI Agent will automatically discover the following capabilities:

### Tools (Actions)
- `jira_search_issues`: Query issues dynamically using JQL.
- `jira_create_issue`: Create new tickets on the board.
- `jira_transition_issue`: Move a ticket's status (e.g., 'To Do' -> 'In Progress').
- `jira_add_comment`: Add a comment to an existing ticket.
- `jira_start_task`: Pick up an issue and transition it to 'In Progress' in one call.
- `jira_submit_for_review`: Transition an issue to 'In Review' and attach a PR link.

### Resources (Context Reading)
- `jira://board`: Instantly fetches the active board (To Do, In Progress, In Review) for the configured default project.
- `jira://issue/{issue_key}`: Fetches deep JSON details of a specific ticket.
- `jira://project/{project_key}/board`: Same as `jira://board`, but for a specific project key instead of the configured default.

### Prompts
- `jira_daily_standup`: Instructs the agent to summarize blockers based on 'In Progress' and 'In Review' tickets.
- `init_project`: Starts the initial architecture phase -- read the spec, produce a DDD architecture doc and a feasibility spike, then present both for approval before any tickets are created.
- `refinement`: Breaks an approved architecture down into Jira tickets, each with strict acceptance criteria for TDD.
- `sprint_planning`: Reviews the backlog and active board, adjusts priorities, moves selected tickets to To Do, and triages which can run in parallel vs. must run in sequence.
- `review_retro`: Reviews a completed round, files any tech debt/enhancements found, and asks whether to proceed to the next round.
