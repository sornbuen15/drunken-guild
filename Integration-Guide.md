# Drunken-Team: AI Integration Guide

This guide is for connecting a local AI coding tool (Claude Code, Cursor, Aider) to Drunken-Team, so it can read and update Jira directly and hand off to the Discord daemon instead of you doing it by hand.

---

## 1. The MCP Servers

Drunken-Team exposes three separate MCP servers -- there is no single combined server or `drunken-mcp` binary.

### `drunken-jira-mcp` -- Jira operations
- **Tools:** `jira_search_issues(jql)`, `jira_create_issue(summary, description)`, `jira_transition_issue(issue_key, target_status)`, `jira_add_comment(issue_key, comment)`, `jira_start_task(issue_key)` (transition to In Progress + the git branch command to run), `jira_submit_for_review(issue_key, pr_link, files_changed)` (transition to In Review + comment the PR link).
- **Resources:** `jira://board`, `jira://issue/{issue_key}`, `jira://project/{project_key}/board`.
- **Prompts:** `jira_daily_standup`, `init_project`, `refinement`, `sprint_planning`, `review_retro`.
- Full reference: [`src/jira_mcp/README.md`](./src/jira_mcp/README.md).

### `drunken-discord-mcp` -- approvals
- **Tools:** `request_boss_approval_async(action, reason, ticket_key)` returns a `req_id` immediately; `check_approvals(req_ids)` collects the answers later. Asking never stops the agent -- park the task and take the next unblocked one.
- `request_boss_approval(action, reason, ticket_key)` is the older blocking form. It still works and is kept until 3.0.0, but prefer the async pair; reach for it only when nothing else could possibly be done meanwhile.
- There is no timeout and nothing is killed for going unanswered: reminders back off 15 min → 1 h → daily and survive a daemon restart. An approval is bound to the commit it was granted against, so from a different HEAD it reads `stale` and must be asked again.

> **`drunken-board-mcp` is retired and is not packaged.** DG-250 removed the local board: a board sitting next to Jira is a second surface that can disagree with the first, which is the failure DG-248 and DG-249 each cost a session to. It also cost 2,162 tokens per request for a server nothing should call. DG-265 removed it from `[project.scripts]` and from the package, so there is no command to declare — the code is kept at `_not_used/board-mcp/` because an agent does not delete. Do not create `.claude/board/` or `.agents/board/`. Jira is the only coordination surface -- the **assignee** says whose the work is, the **status** says where it is.

Both are registered for you already in `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "drunken-discord-mcp": { "command": "uv", "args": ["run", "python", "-m", "discord_mcp.server"], "env": { "PYTHONPATH": "src" } },
    "drunken-jira-mcp": { "command": "uv", "args": ["run", "python", "-m", "jira_mcp.server"], "env": { "PYTHONPATH": "src" } }
  }
}
```

Which project a server acts on comes from `--project <id>`, resolved against the central registry -- never from the working directory, and never from a `.env` next to the code. Add `"--project", "<id>"` to `args` when running a server against a project other than the one it was launched from.

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

1. **Intake:** Call `jira_start_task(issue_key)` to claim a ticket and get the branch name to check out. (`scripts/jira_bridge.py transition <key> "In Progress"` still works for shell use, but the MCP tools are the supported path.)
2. **Execution:** Write code and tests against that ticket's acceptance criteria. Before any destructive or merge-worthy action: if the Boss is reading the conversation, just ask them there. Otherwise call `request_boss_approval_async`, park the task with `board_block_task`, and move on to whatever `board_available_tasks` offers. Collect answers with `check_approvals` **when a task finishes or a session starts -- never mid-task**, because acting on an approval the moment it lands is how a repo ends up half-changed.
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

This installs the commands globally: `drunken-init` (create the state directory and register a project), `drunken-config` (generate MCP and install configuration), `drunken-doctor` (report where every path and secret actually resolves from), `drunken-listen` (run the Discord daemon), and `drunken-jira-mcp`, `drunken-discord-mcp` (the two MCP servers).

> **`uv tool install` ignores `uv.lock`**, so the tool environment drifts inside the allowed dependency range -- the deployment carried `mcp` 1.29.0 against a lock pinning 1.28.1 for two releases, both satisfying `<2`, with nothing reporting it. To install what the lock actually names, let `drunken-config` write the requirements and give you the command:
>
> ```bash
> drunken-config --project <id> --kind install
> ```
>
> `drunken-doctor` reports the gap either way (`deployment.mcp_pin`).

### Step 2: Onboard the project

One command registers it and writes its MCP config:

```bash
python /path/to/drunken-team/scripts/onboard_project.py existing-project \
  --jira-project-key XYZ \
  --path /path/to/existing-project \
  --description "..." \
  --write-mcp-config
```

Add `--dry-run` first to see exactly what it would write, without writing it.

**It reuses the credential you already have.** If every project of yours lives on the same Jira site under the same account -- which is the usual case -- they share one entry in `~/.drunken/secrets.json` and differ only by `--jira-project-key`. Give a project its own with `--credential-key <name>` when it genuinely needs a different account.

> Sharing by reference is not a shortcut, it is the point. A copied token drifts: one of ours expired in a project's own `.env` and, because a Jira search answers a dead credential with `200` and an empty list, that board simply read as empty for months with nothing saying why.

The Jira URL and account are inherited from a project you have already registered, so you cannot end up with three entries naming three slightly different hosts.

**Doing it by hand instead.** `onboard_project.py` is a wrapper over `drunken-init` plus a config file; nothing stops you running the parts yourself:

```bash
drunken-init \
  --project existing-project \
  --path /path/to/existing-project \
  --jira-url https://your-domain.atlassian.net \
  --jira-email you@example.com \
  --jira-project-key XYZ \
  --jira-credential 'file://~/.drunken/secrets.json#jira.default' \
  --discord-channel 123456789012345678
```

**Credentials are referenced, never stored.** `--jira-credential` takes `file://path#key.path`, `env://VAR`, `op://vault/item/field` or `keyring://service/user`, and there is deliberately no flag that accepts a token. A reference with no scheme is rejected as an error rather than read as a literal -- `literal://` is the visible, greppable opt-out. That is what stops a real token ending up in a committable file and working right up until it is pushed.

`--path` is optional: a containerised server that only talks to Jira or Discord has no host checkout to name. Only the file-backed board needs one.

### Step 2b: Prove it, before trusting it

A separate step on purpose. `drunken-init` exiting 0 means a file was written, not that the credential works -- and a search cannot tell you either, because a bad token still returns `200`. `drunken-doctor` asks `/rest/api/3/myself`, which 401s:

```bash
drunken-doctor --project existing-project
```

You want `project.existing-project.jira` to come back naming *you*.

### Step 3: Copy the AI templates

```bash
cp /path/to/drunken-team/.guild_templates/CLAUDE.md .
cp /path/to/drunken-team/.guild_templates/.cursorrules .
cp /path/to/drunken-team/.guild_templates/CONVENTIONS.md .
cp /path/to/drunken-team/.guild_templates/SESSION_CHECKPOINT.md .
```

### Step 4: The MCP config

`--write-mcp-config` in step 2 already wrote this. It names the commands and carries no path at all, which is what keeps one machine's directory layout out of another repository's git history:

```json
{
  "mcpServers": {
    "drunken-jira-mcp": { "command": "drunken-jira-mcp", "args": ["--project", "existing-project"] },
    "drunken-discord-mcp": { "command": "drunken-discord-mcp", "args": ["--project", "existing-project"] }
  }
}
```

This depends on step 1 — the commands have to be on `PATH`. Without `uv tool install`, fall back to `uv run --directory /path/to/drunken-team drunken-jira-mcp --project existing-project`, and keep that file out of git.

For Cursor: **Settings > Features > MCP > Add New Server**, type `command`, `drunken-jira-mcp` with args `--project existing-project`, then the same for the other one.

From here, your local AI reads `CLAUDE.md`/`.cursorrules`, checks Jira via the MCP tools, writes code, and hands off through the same lifecycle described in Section 3.

---
*This document covers integration and handoff only. For Drunken-Team's own architecture and day-to-day Discord commands, see [Drunken-Team-Guide.md](./Drunken-Team-Guide.md).*
