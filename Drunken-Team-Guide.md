# Drunken Team: The Guild Guide

This is the operating manual for Drunken-Team ("the Guild"). It covers the architecture, how to install and run it, and how to use the Jira workflow and the Discord bot day to day.

*(This document explains how the Guild's own automation works. For an individual project's feature specs or system design, see that project's own `PROJECT_SPEC.md`/`DESIGN.md`.)*

---

## 1. What Drunken-Team Is

Drunken-Team is a small orchestration layer, not a framework you code against. It has three moving parts:

- **Jira** is the single source of truth for tasks. There is no local task file or board -- every ticket's status lives in Jira, and every command below reads or writes it directly.
- **A Discord bot** (a persistent background daemon) lets you monitor agent work and approve or reject actions from your phone, plus a set of commands for common Jira/PR operations without opening a terminal.
- **An MCP server** exposes the same Jira operations as tools an AI agent (Claude Code, etc.) can call directly while it works.

What it deliberately does **not** do: there is no dashboard UI (removed -- Jira alone covers status), and there is no free-form natural-language task dispatch from Discord (you cannot type "fix the login bug" into Discord and have an agent start working on it; see [Section 5](#5-discord-bot-commands) for what you *can* do from Discord).

---

## 2. Architecture

| Component | File | Purpose |
|---|---|---|
| Project Registry | `src/core/registry.py` | One file (`projects.json` under `$DRUNKEN_HOME`) holding every project's Jira, checkout path and Discord channel, so commands can target a project other than the one Discord is running in. Credentials appear only as references. |
| Discord daemon | `src/service/discord_listener.py` | The bot process. Owns the Discord connection, the approval state machine, and a Unix socket that an MCP tool call blocks on while waiting for you to react. |
| Discord router | `src/service/discord_router.py` | Parses incoming Discord messages and dispatches to the right command handler. |
| Approval manager | `src/service/approval_manager.py` | State machine for a single approval request: post the question, wait, remind once, escalate if you never respond. |
| Jira bridge | `scripts/jira_bridge.py` | The one place that talks to the Jira REST API. Both the Discord commands and the MCP server call into this. |
| Jira MCP server | `src/jira_mcp/server.py` | Exposes Jira operations as MCP tools/resources/prompts for a coding agent to call directly (see the [Integration Guide](./Integration-Guide.md)). |
| QA gate | `scripts/qa_automation.py` | The round-integration gate: merges every ticket that individually passed onto a scratch branch, reruns the full test suite, and only then marks tickets Done. |

There is no separate "router AI" deciding what to do with your messages -- every Discord command below is deterministic: same input, same Jira/GitHub call, every time.

### 2.1 AI behavior boundaries

The detailed rules an AI agent must follow while working in this repo (when it can act immediately, when it must ask, what's forbidden outright) live in [`.agents/AGENTS.md`](./.agents/AGENTS.md) -- that file is the source of truth for agent-facing rules, kept separate here to avoid two documents drifting out of sync. In short: destructive or merge-worthy actions go through the approval flow in [Section 6](#6-approval-flow), not straight execution.

---

## 3. Installation & Setup

### 3.1 Prerequisites
- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (package manager and script runner)
- Git
- A Jira Cloud account with an API token
- A Discord bot token and a channel ID (create a bot at the [Discord Developer Portal](https://discord.com/developers/applications), invite it to your server, enable the Message Content and Server Members intents)

### 3.2 Clone and install dependencies

```bash
git clone https://github.com/sornbuen15/drunken-team.git
cd drunken-team
uv sync
```

### 3.3 Configure credentials

There are two halves: the **secret itself**, which lives outside the repository, and the **registry**, which holds only a reference to it.

**1. The secret.** One JSON file under `$DRUNKEN_HOME`, owner-readable only:

```bash
mkdir -p ~/.drunken && chmod 700 ~/.drunken
cat > ~/.drunken/secrets.json <<'JSON'
{ "jira": { "drunken-team": "your-jira-api-token" } }
JSON
chmod 600 ~/.drunken/secrets.json
```

One file can hold every project's credential — the reference's `#jira.drunken-team` fragment is a dotted path into it.

**2. The registry.**

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

This writes one central registry under `$DRUNKEN_HOME` (default `~/.drunken`, mode 700) -- not into the project. The command is non-interactive and idempotent, so it also works inside a Dockerfile or a provisioning script.

**Credentials are referenced, never stored.** `--jira-credential` accepts `file://path#key.path`, `env://VAR`, `op://vault/item/field` or `keyring://service/user`, and there is deliberately no flag that takes a token. A reference with no scheme is an error rather than a literal; `literal://` is the visible opt-out.

> Why `file://` rather than `env://` for a local install: the MCP servers are launched as subprocesses by whatever AI tool you use, and that tool's environment is not your shell's. An `env://` reference resolves only if the variable is exported by whatever starts the tool — which is the kind of invisible configuration that makes a setup work on one machine and nowhere else. `file://` is also exactly what a mounted secret volume looks like later.

**Migrating from an older release.** If you already have a working `.env`, this does both halves without ever printing the token:

```bash
uv run python scripts/migrate_env_to_registry.py --project drunken-team --dry-run
uv run python scripts/migrate_env_to_registry.py --project drunken-team
```

**3. Prove it resolves.** A separate, deliberate step, because Jira answers a search with `200` and `[]` when the credential is bad -- so searching cannot tell you whether it worked. `drunken-doctor` asks `/rest/api/3/myself`, which 401s:

```bash
uv run drunken-doctor --project drunken-team
```

`project.drunken-team.jira` should come back naming *you*. Until you start the daemon, a warning about a missing socket is expected.

**The `.env` file is still needed** -- the Discord daemon reads its own bot token from there directly, and `scripts/jira_bridge.py` uses it for shell work:

```bash
cp .env.example .env
```

`.env.example` documents every variable the project reads with inline comments. `.env` is gitignored -- your real values never get committed.

### 3.4 Register the MCP servers (for an AI coding agent)

`.mcp.json` at the repo root already registers all three MCP servers for tools like Claude Code:

```json
{
  "mcpServers": {
    "drunken-discord-mcp": { "command": "uv", "args": ["run", "python", "-m", "discord_mcp.server"], "env": { "PYTHONPATH": "src" } },
    "drunken-jira-mcp": { "command": "uv", "args": ["run", "python", "-m", "jira_mcp.server"], "env": { "PYTHONPATH": "src" } },
    "drunken-board-mcp": { "command": "uv", "args": ["run", "python", "-m", "board_mcp.server"], "env": { "PYTHONPATH": "src" } }
  }
}
```

Which project a server acts on comes from `--project <id>`, resolved against the registry -- never from the working directory. Add `"--project", "<id>"` to a server's `args` to point it at a project other than the one it was launched from.

If your agent supports project-level `.mcp.json` discovery, this works out of the box. Otherwise see the [Integration Guide](./Integration-Guide.md) for manual configuration.

### 3.5 Run the Discord bot

For a one-off test:

```bash
uv run python src/service/discord_listener.py
```

For everyday use, install it as a persistent background service (macOS, via `launchd`) so approvals reach you without a terminal open:

```bash
uv run python scripts/setup_daemon_service.py install   # start now, and on every login
uv run python scripts/setup_daemon_service.py status     # check it's running
uv run python scripts/setup_daemon_service.py uninstall   # remove it
```

This is local-machine-only -- if the machine is off or asleep, approvals will not reach Discord.

---

## 4. Jira Workflow

Jira is the only place task state lives. The board has four lanes: **Backlog -> To Do -> In Progress -> In Review -> Done** (Backlog is derived, not a native Jira status -- see below).

### 4.1 Query the board from the CLI

```bash
uv run python scripts/jira_bridge.py get-todo          # priority DESC, created ASC
uv run python scripts/jira_bridge.py get-in-progress
uv run python scripts/jira_bridge.py get-in-review
uv run python scripts/jira_bridge.py get-backlog        # status != Done AND no round label
uv run python scripts/jira_bridge.py get-by-label round-1
```

Each prints a JSON list of `{key, summary, status, priority, description, assignee}`.

### 4.2 Change ticket state

```bash
uv run python scripts/jira_bridge.py transition DT-42 "In Progress"
uv run python scripts/jira_bridge.py comment DT-42 "Investigated -- root cause was X."
uv run python scripts/jira_bridge.py label DT-42 round-2
uv run python scripts/jira_bridge.py create "Fix flaky test" "Steps to reproduce..."
```

### 4.3 The full lifecycle for one ticket

```
1. uv run python scripts/jira_bridge.py get-todo
   -> pick the first result (already priority-sorted)
2. uv run python scripts/jira_bridge.py transition DT-42 "In Progress"
3. git checkout -b feature/DT-42-short-description
   ... write code, tests, commit ...
4. Open a PR, then:
   uv run python scripts/jira_bridge.py transition DT-42 "In Review"
   uv run python scripts/jira_bridge.py comment DT-42 "PR: https://github.com/.../pull/60"
5. Round-integration gate passes (scripts/qa_automation.py) -> ticket auto-transitions to Done.
```

Every step above also has a Discord equivalent -- see the next section.

---

## 5. Discord Bot Commands

All commands are plain messages starting with `/` in your configured channel (this is not Discord's native slash-command UI -- just type the text). None of them require the Boss to wait for a reply beyond a couple of seconds, except `/qa`, which acknowledges immediately and replies later when the background job finishes.

### 5.1 Status & control

| Command | What it does |
|---|---|
| `/help` | Full command list. |
| `/list-cmd` | Short command list. |
| `/status` | Is an agent currently running, and what's the last thing it did. |
| `/stop` or `/kill` | Immediately terminate the running agent task (and clean up any orphaned process from a crashed daemon). |
| `!detail` | Upload the full raw execution log as a file. |

### 5.2 Jira/PR queries (read-only, instant)

| Command | Example | What it does |
|---|---|---|
| `/tasks` | `/tasks` | List the To Do lane. |
| `/inprogress` | `/inprogress` | List the In Progress lane. |
| `/review` | `/review` | List the In Review lane. |
| `/backlog` | `/backlog` | List the backlog. |
| `/pr` | `/pr` | List open GitHub PRs. |
| `/pending` | `/pending` | List approval requests still waiting on you. |

Example:
```
You:  /tasks
Bot:  **To Do** (3)
      `DT-90` [Medium] Reconcile Drunken-Team-Guide.md and README.md
      `DT-95` [Medium] Add token/cost tracking for agent runs
      `DT-104` [Medium] ...
```

### 5.3 Workflow actions

| Command | Example | What it does |
|---|---|---|
| `/project [name]` | `/project isac` | Show, or switch, which registered project the commands above (and `/next`/`/refine`) target. No argument shows the current one. |
| `/next` | `/next` | If nothing is In Progress, pick the top of To Do and transition it there. Refuses if a ticket is already In Progress. |
| `/refine` | `/refine` | Auto-promote any Critical-priority backlog ticket straight to To Do; report a priority breakdown of everything else (no auto-promotion for non-Critical). |
| `/approve <ticket>` | `/approve DT-42` | Clear an escalated (timed-out) approval block on a ticket and re-dispatch the work with the original context, so it isn't stuck forever. |
| `/qa` | `/qa` | Run the round-integration QA gate in the background; replies to its own acknowledgement message when done. |

Example:
```
You:  /next
Bot:  ▶️ DT-42 moved to In Progress.
      Fix flaky test in test_discord_router.py

You:  /refine
Bot:  **Backlog refinement** (4 total)
      🔺 Auto-promoted Critical -> To Do: DT-101
      **Medium** (2): DT-95, DT-104
      **Low** (1): DT-88
```

### 5.4 Anything not starting with `/`

Free-form natural-language task commanding is disabled. Any plain message gets one fixed reply pointing you at `/help`. This is a deliberate, tracked decision (Jira ticket DT-94), not an oversight -- it avoids the cost, latency, and prompt-injection surface of a free-text router while still covering the day-to-day Jira/PR operations above.

---

## 6. Approval Flow

Some agent actions require your explicit sign-off (e.g. a destructive command, or a merge). **If you are reading the agent's conversation, it should simply ask you there.** Discord is for when you are not watching.

Unattended, asking must never stop the rest of the work:

1. The agent calls `request_boss_approval_async(action, reason, ticket_key)`, which returns a `req_id` immediately, and the bot posts the question to Discord with 👍/👎 reactions attached.
2. The agent parks that task with `board_block_task`, carrying the `req_id` that would free it, and takes the next task `board_available_tasks` offers.
3. **React 👍** to approve, **👎** to reject.
4. The agent collects answers with `check_approvals` **when it finishes a task or starts a session -- never mid-task.** Acting on an approval the moment it lands is how a repo ends up half-changed.
5. **There is no timeout and nothing is auto-killed.** Reminders back off 15 min → 1 h → daily and survive a daemon restart. A question you have not reached yet is not an error.
6. An approval is bound to the commit it was granted against. From a different HEAD it reads `stale` and has to be asked again -- a yes given this morning does not authorise tonight's different code.
7. A pre-commit hook blocks new commits on a ticket with an unresolved approval, so nothing slips through while a request is hanging.
8. Force-push, hard reset, `rm -rf` and reading `.env` are refused by `.claude/settings.json` **no matter what comes back over Discord.** Remote approval is only safe while some actions sit outside it.

The older blocking `request_boss_approval` still works and is kept until 3.0.0. Prefer the async pair.

While an agent task is running, you can also react **❌** on its status message to kill it immediately -- equivalent to `/stop`.

---

## 7. Multi-Project Orchestration

Drunken-Team can operate on more than one codebase. One central registry -- `projects.json` under `$DRUNKEN_HOME` (default `~/.drunken`) -- answers "which Jira, which repo, which Discord channel" for every project:

```json
{
  "version": 2,
  "projects": {
    "drunken-team": {
      "path": "/Users/you/Projects/drunken-team",
      "description": "The Guild Headquarters",
      "jira": {
        "url": "https://your-domain.atlassian.net",
        "email": "you@example.com",
        "project_key": "DT",
        "credential": "env://JIRA_API_TOKEN"
      },
      "discord": { "channel_id": "123456789012345678" }
    },
    "isac": {
      "description": "ISAC Project",
      "jira": {
        "url": "https://your-domain.atlassian.net",
        "email": "you@example.com",
        "project_key": "ISAC",
        "credential": "env://JIRA_TOKEN_ISAC"
      }
    }
  }
}
```

Nothing in it is secret -- credentials appear only as references -- so it can be committed, reviewed and shared, which is exactly what stops five copies of a token drifting apart in five `.env` files. `path` is optional: only the file-backed board needs a checkout on disk, and a containerised Jira or Discord server has no host path to give.

Add an entry with `drunken-init --project <id> ...` (Section 3.3) rather than by hand. A v1 registry -- the bare `{"name": {...}}` map written by earlier releases -- is upgraded in memory on read and never rewritten behind your back, so downgrading is just running the old code again.

Once registered, `/project <name>` in Discord switches which project the Jira-lane commands and `/next`/`/refine` operate against -- each project can have its own Jira project key, so `/project isac` then `/tasks` lists ISAC's own To Do lane, not drunken-team's.

---

## 8. The QA Gate

`scripts/qa_automation.py` is the safety net between "individually passing tests" and "actually Done":

1. Finds every ticket currently In Review.
2. Runs each ticket's own test suite on its own branch.
3. Merges every ticket that passed onto a scratch integration branch and reruns the **full** suite together -- this catches the case where two tickets pass alone but conflict when combined.
4. If the combined run passes, every contributing ticket transitions to Done with the report attached as a Jira comment. If it fails, they go back to In Progress with the failure report instead.

Run it manually with `/qa` in Discord, or `uv run python scripts/qa_automation.py` from the CLI. It performs real `git checkout`/`merge`/branch-delete operations on your working tree -- don't run it with uncommitted changes you care about.

---

## 9. Where to Go Next

- Connecting an external AI coding tool (Claude Code, Cursor, Aider) to this Guild: [Integration Guide](./Integration-Guide.md)
- Contributing code, branching, and PR conventions: [CONTRIBUTING.md](./CONTRIBUTING.md)
