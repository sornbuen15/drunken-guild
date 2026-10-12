# Drunken Guild: The Guild Guide

Drunken Guild gives AI coding agents one standard way to take a requirement through Jira to a
merged pull request — the same skills, roles and review gates every time. Three roles —
**manager** (plans), **worker** (implements one task), **reviewer** (checks it) — run the
**seven-command flow**: `/prd` → `/clarify` → `/ddd` → `/breakdown` → `/build` → `/audit`, plus
`/replan` when a requirement moves. **Jira** is the only coordination surface — there is no local
board — and two hooks (SessionStart context, per-prompt routing) make a session reach for the
right skill without being told.

*(For an individual project's own brief, requirements or spec — not the Guild's — see that
project's own documents, usually `.ai/`; the `project-docs` skill lists every place they are
looked for.)*

This page is the **operator** manual: install is [`README.md`](./README.md) and
[`GETTING_STARTED.md`](./GETTING_STARTED.md); this page covers the registry, Jira day to day,
approvals, and running more than one project.

## 1. Architecture

| Component | File | Purpose |
|---|---|---|
| Project registry | `src/core/registry.py` | One file (`projects.json` under `$DRUNKEN_HOME`) holding every project's Jira, checkout path and notification webhook. Credentials appear only as references. |
| Jira MCP server | `src/jira_mcp/server.py` | Exposes Jira operations as MCP tools for a coding agent to call directly ([Integration Guide](./Integration-Guide.md)). |
| Notifier | `src/core/notify.py` | One POST to a Discord webhook: a line and a link. Never raises; says why when it could not send. |
| Permission floor | `src/core/hook.py` (`drunken-hook`) | The PreToolUse hook: refuses what `.claude/settings.json` denies and a call it cannot read; silent otherwise. |

**AI behavior boundaries.** The detailed rules an agent must follow in this repository live in
[`AGENTS.md`](./AGENTS.md) — the source of truth, whichever agent is reading it. `CLAUDE.md` is
only the one-line adapter that imports it.

## 2. Registry, credentials and the MCP server

The registry (`$DRUNKEN_HOME/projects.json`, default `~/.drunken`) holds every project's Jira URL,
project key and a credential **reference** — never the token itself:

```bash
uv run drunken-init --project <id> --path "$PWD" \
  --jira-url https://your-domain.atlassian.net --jira-email you@example.com \
  --jira-project-key DG --jira-credential 'file://~/.drunken/secrets.json#jira.<id>'
```

`--jira-credential` takes `file://path#key.path`, `env://VAR`, `op://vault/item/field` or
`keyring://service/user` — no flag accepts a token directly, and a reference with no scheme is an
error, not a literal.

**Prove it, don't assume it.** Jira answers a bad credential with `200` and an empty list, so a
search cannot tell you it failed. `drunken-doctor --project <id>` asks `/rest/api/3/myself`, which
401s on a bad credential — read its remediation line rather than a fixed checklist here; it also
reports version drift between this checkout and the installed tool, and whether `uv.lock` and the
deployed tool agree.

**Declare the MCP server once per machine, not per project** (REQ-019, DG-457, DG-341) — a project
carries no `.mcp.json`. For Claude Code:

```bash
claude mcp add --scope user drunken-jira-mcp -- "$(command -v drunken-jira-mcp)"
claude mcp list        # drunken-jira-mcp ... Connected
```

One entry serves every project: each tool call carries the registry project id as its first
argument, so the same entry is correct everywhere. Full steps, other agents, and what one retired
server's config looks like today: [`GETTING_STARTED.md`](./GETTING_STARTED.md) and
[`Integration-Guide.md`](./Integration-Guide.md); what was retired and why: [`RETIRED.md`](./RETIRED.md).

## 3. Jira workflow

Four lanes: **Backlog → To Do → In Progress → In Review → Done** (Backlog is derived, not a native
status).

| for | use |
|---|---|
| search / status | `jira_search_issues` |
| claim and start | `jira_start_task` |
| move status | `jira_transition_issue` |
| hand off for review | `jira_submit_for_review` |
| leave a note | `jira_add_comment` |
| claim / release | `jira_assign` — an email, a display name, `"me"`, or `"none"` |
| board membership | `jira_board_info`, `jira_move_to_backlog`, `jira_move_to_board` |

One ticket, start to finish:

```
1. jira_search_issues("status = 'To Do' ORDER BY ...") -> pick one
2. jira_assign(key, "me"), jira_start_task(key) -> In Progress, branch name returned
3. git checkout -b feature/DG-42-short-description; write code, tests, commit
4. Open a PR, then jira_submit_for_review(key, pr_link, files_changed) -> In Review
5. The Boss merges the PR; /audit verifies it against the merged tree -> Done
```

How to write and run a ticket in full: `skills/workflow/jira-tickets/SKILL.md`.

## 4. Notifications and approvals

Discord is **one-way** — a notification carrying a link, for four things worth interrupting
someone over: a PR is ready, today's MVP is up, an audit found gaps, an agent needs a decision.
Nothing can be typed at it and no action is authorised from it.

```bash
uv run python -m core.notify "PR #80 is ready for review" --link https://github.com/x/y/pull/80
uv run drunken-init --project <id> --discord-webhook env://DISCORD_WEBHOOK_URL
```

A project with no webhook configured is not misconfigured — `drunken-doctor` reports that as
`skip`. **Approvals happen in the conversation**: the Boss is reading → ask them there. Not
reading → notify and park, pick up the answer next session; nothing is killed for going
unanswered. What no answer can grant — a force push, a hard reset, a recursive delete, reading
`.env` — is refused by `.claude/settings.json` and `drunken-hook` before either of them is
consulted. See the `ask-boss` skill.

## 5. Multi-project orchestration

One registry answers "which Jira, which repo, which webhook" for every project:

```json
{
  "version": 2,
  "projects": {
    "alpha": {
      "path": "/Users/you/Projects/alpha",
      "jira": { "url": "https://your-domain.atlassian.net", "email": "you@example.com",
                "project_key": "ALPHA", "credential": "env://JIRA_TOKEN_ALPHA" }
    }
  }
}
```

Nothing in it is secret, so it can be committed and shared — add an entry with
`drunken-init --project <id> ...` rather than by hand. Each project keeps its own Jira project
key, so a tool always acts on the project it was asked about, never on whichever was registered
first.

## 6. The quality gate

There is no separate gate process. A ticket is Done when its test was **seen failing first**, is
green **on the merged tree**, traces to a requirement, and the Boss merged the PR. `/audit` checks
that; `skills/workflow/jira-tickets/SKILL.md` §7 is the list to verify against.

## 7. Where to go next

- Connecting an external tool (Claude Code, Cursor, Aider), or bringing another project under this
  workflow: [Integration Guide](./Integration-Guide.md)
- Contributing code, branching and PR conventions: [CONTRIBUTING.md](./CONTRIBUTING.md)
- Why it is shaped this way: [DESIGN.md](./DESIGN.md)
