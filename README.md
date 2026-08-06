# Drunken Team

**Drunken Team** orchestrates autonomous coding agents across multiple projects, using Jira as the single source of truth for tasks and a Discord bot for monitoring and approvals.

---

## Documentation

### 1. [Drunken-Team Guide](./Drunken-Team-Guide.md)
*For team members, tech leads, and AI agents working in this repo.*
Architecture, installation, the Jira workflow, the full Discord command reference (with examples), the approval flow, multi-project orchestration, and the QA gate.

### 2. [AI Integration Guide](./Integration-Guide.md)
*For connecting an external tool (Cursor, Aider, Claude Code) to this project, or bringing another project under the same workflow.*
The two MCP servers, the local-AI rule templates in `.guild_templates/`, and the handoff lifecycle from task intake to Done. Note: MCP servers support cross-project usage via the `--workspace <path>` argument.

---

## Quick Start

1. Clone the repository and install dependencies:
   ```bash
   git clone https://github.com/sornbuen15/drunken-team.git
   cd drunken-team
   uv sync
   ```
2. Configure Jira and Discord credentials:
   ```bash
   uv run drunken-register
   ```
3. Run the Discord bot:
   ```bash
   uv run python src/service/discord_listener.py
   ```
4. In your configured Discord channel, type `/help` to see what you can do.

See the [Drunken-Team Guide](./Drunken-Team-Guide.md) for the full setup (including running the bot as a persistent background service) and command reference.
