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
2. Put your credentials in a file outside the repository, readable only by you:
   ```bash
   mkdir -p ~/.drunken && chmod 700 ~/.drunken
   cat > ~/.drunken/secrets.json <<'JSON'
   { "jira": { "drunken-team": "your-jira-api-token" } }
   JSON
   chmod 600 ~/.drunken/secrets.json
   ```
3. Register the project. The registry stores a **reference** to that file, never
   the token — `--jira-credential` also accepts `env://VAR`,
   `op://vault/item/field` and `keyring://service/user`, and there is
   deliberately no flag that takes a token:
   ```bash
   uv run drunken-init \
     --project drunken-team \
     --path "$PWD" \
     --jira-url https://your-domain.atlassian.net \
     --jira-email you@example.com \
     --jira-project-key DT \
     --jira-credential 'file://~/.drunken/secrets.json#jira.drunken-team' \
     --discord-channel 123456789012345678
   ```
   Already have a working `.env` from an older release? `uv run python
   scripts/migrate_env_to_registry.py --project drunken-team` does steps 2 and 3
   for you without printing the token. Add `--dry-run` to see what it would do.
4. Prove it actually resolves — this is a separate step on purpose, because Jira
   answers a search with `200` and `[]` when the credential is bad:
   ```bash
   uv run drunken-doctor --project drunken-team
   ```
   You want `project.drunken-team.jira` to come back naming *you*. A warning that
   the daemon socket is missing is expected until step 5.
5. Run the Discord bot:
   ```bash
   uv run python src/service/discord_listener.py
   ```
6. In your configured Discord channel, type `/help` to see what you can do.

### Installing it as a command

Once registered, the servers can be installed globally and run from anywhere —
no checkout path, no `--directory`, no `PYTHONPATH`:

```bash
uv tool install .
drunken-doctor --project drunken-team
```

That gives you `drunken-init`, `drunken-doctor`, `drunken-listen` and the three
MCP servers. Another project's `.mcp.json` then names the command and nothing
else, which is what keeps one machine's directory layout out of another repo's
git history:

```json
{
  "mcpServers": {
    "drunken-jira-mcp": { "command": "drunken-jira-mcp", "args": ["--project", "your-project"] }
  }
}
```

> `uv tool install` ignores `uv.lock`, so the tool environment can drift inside
> the allowed dependency range. Pass `--with-requirements` if you need it pinned.

### Known limits

- The Discord daemon still reads `.env` directly for its own bot token. Only the
  Jira credential has moved to the registry so far.
- The daemon and the MCP servers agree on the socket location through
  `core.paths`, so **after upgrading, restart the daemon**. Until you do, the
  running daemon still listens on the old path and clients report approval as
  unavailable — they name the path they looked at, and `drunken-doctor` says so
  too, but nothing fixes it for you.

See the [Drunken-Team Guide](./Drunken-Team-Guide.md) for the full setup (including running the bot as a persistent background service) and command reference.
