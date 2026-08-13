# Drunken Team

**Drunken Team** orchestrates autonomous coding agents across multiple projects, using Jira as the single source of truth for tasks and a Discord bot for monitoring and approvals.

---

## Documentation

### 1. [Drunken-Team Guide](./Drunken-Team-Guide.md)
*For team members, tech leads, and AI agents working in this repo.*
Architecture, installation, the Jira workflow, the full Discord command reference (with examples), the approval flow, multi-project orchestration, and the QA gate.

### 2. [AI Integration Guide](./Integration-Guide.md)
*For connecting an external tool (Cursor, Aider, Claude Code) to this project, or bringing another project under the same workflow.*
The three MCP servers, the local-AI rule templates in `.guild_templates/`, and the handoff lifecycle from task intake to Done. Note: the servers work across projects via `--project <id>`, resolved against the central registry — no project ever holds a credential.

---

## Quick Start

1. Clone the repository and install dependencies:
   ```bash
   git clone https://github.com/sornbuen15/drunken-team.git
   cd drunken-team
   uv sync
   ```
2. Create the state directory and register this project. Credentials are
   *referenced*, never stored — `--jira-credential` takes `env://VAR`,
   `file://path#key`, `op://vault/item/field` or `keyring://service/user`, and
   there is deliberately no flag that accepts a token:
   ```bash
   uv run drunken-init \
     --project drunken-team \
     --path "$PWD" \
     --jira-url https://your-domain.atlassian.net \
     --jira-email you@example.com \
     --jira-project-key DT \
     --jira-credential env://JIRA_API_TOKEN \
     --discord-channel 123456789012345678
   ```
3. Check that everything resolves to where you think it does:
   ```bash
   uv run drunken-doctor
   ```
4. Run the Discord bot:
   ```bash
   uv run python src/service/discord_listener.py
   ```
5. In your configured Discord channel, type `/help` to see what you can do.

See the [Drunken-Team Guide](./Drunken-Team-Guide.md) for the full setup (including running the bot as a persistent background service) and command reference.
