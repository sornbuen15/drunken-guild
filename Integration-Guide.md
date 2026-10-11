# Drunken-Guild: AI Integration Guide

This guide is for connecting a local AI coding tool (Claude Code, Cursor, Aider) to Drunken-Guild, so it can read and update Jira directly and hand off to the Discord daemon instead of you doing it by hand.

---

## 1. The MCP Servers

Drunken-Guild exposes two separate MCP servers -- there is no single combined server or `drunken-mcp` binary.

### `drunken-jira-mcp` -- Jira operations
- **Tools:** `jira_search_issues`, `jira_create_issue`, `jira_assign`, `jira_board_info`, `jira_transition_issue`, `jira_add_comment`, `jira_start_task` (transition to In Progress + the git branch command to run), `jira_submit_for_review` (transition to In Review + comment the PR link), `jira_move_to_backlog`, `jira_move_to_board`, `jira_edit_labels` (add/remove labels without replacing the set), `jira_edit_issue` (correct a summary or description; an empty argument is left unchanged).
- **Resources:** `jira://board`, `jira://issue/{issue_key}`, `jira://project/{project_key}/board`.
- **Prompts:** `jira_daily_standup`, `init_project`, `refinement`, `sprint_planning`, `review_retro` — each names the skill that owns that process, and says to stop if the skill is not installed.
- How to write and run a ticket is the `jira-tickets` skill, not this list.
- Full reference: [`src/jira_mcp/README.md`](./src/jira_mcp/README.md).

### Approvals -- no server, and nothing to call
- **The Boss is reading the conversation → ask them there.** That is the whole mechanism (DG-355). The approval server, its daemon and its 👍/👎 protocol are retired: a question that needs a person is a question for the person who is already reading.
- **Not reading it → send one notification and park the task.** `python -m core.notify "<line>" --link <url>` posts to the project's webhook. It is one-way: nothing comes back, so take the next unblocked task and pick the answer up next session.
- Nothing is killed for going unanswered, and nothing expires.

> **`drunken-board-mcp` is retired and is not packaged.** DG-250 removed the local board: a board sitting next to Jira is a second surface that can disagree with the first, which is the failure DG-248 and DG-249 each cost a session to. It also cost 2,162 tokens per request for a server nothing should call. DG-265 removed it from `[project.scripts]` and from the package, so there is no command to declare — the code is kept at `_not_used/board-mcp/` because an agent does not delete. Do not create `.claude/board/` or `.agents/board/`. Jira is the only coordination surface -- the **assignee** says whose the work is, the **status** says where it is.

It is not pre-registered anywhere. A project carries **no** `.mcp.json` (REQ-019, DG-457): the
server is declared once per machine at the agent's user level, and GETTING_STARTED.md has the
steps. For Claude Code:

```bash
claude mcp add --scope user drunken-jira-mcp -- "$(command -v drunken-jira-mcp)"
```

> **User scope is safe because the server takes no project.** It used to be unsafe: a user-scope
> entry launched with a fixed `--project` made every other project talk to that one project's Jira
> and Discord room. DG-341 removed the flag, so the same entry now serves every project, and the
> project id travels in each tool call.

> **The server takes no project (DG-341).** Every tool takes the registry project id as its first
> argument, which is why one entry serves every project. The flag it replaces was what user scope
> could pin: one `~/.claude.json` entry reaches every session on the machine, so a server launched
> with a project answered sessions that were not that project. Do **not** put a channel id here — the project id is
> the reference and the registry holds the value.
>
> A project's repository holds no `.mcp.json`. `scripts/install/install_mcp.sh` prints the JSON for
> an agent whose user-level config you edit by hand.

Which project a server acts on comes from `--project <id>`, resolved against the central registry -- never from the working directory, and never from a `.env` next to the code. Add `"--project", "<id>"` to `args` when running a server against a project other than the one it was launched from.

> **A host config regenerates itself clean; a repository's `.mcp.json` does not.** `onboard_project.py --merge-mcp-config` merges by name into whatever the host — Antigravity, Cursor — already has there, so its own servers survive. It also now **prunes** any entry matching this project's own `drunken-*-mcp` naming convention that is no longer in `MCP_SERVERS`, so a server this project retires (`drunken-board-mcp`, DG-265) disappears on the next regeneration instead of sitting there indefinitely. An entry that was never ours — a third-party `jira-board`, a local `kanban-board` — is never touched either way; regeneration only ever removes what it could also have added (DG-286). DG-277 is the one hand-fix that predates this: entries dead before the pruning rule existed still needed a human to delete them once, under `~/.gemini/`, because editing a file there is an install.



If your tool reads a user-level MCP config, you're done once the entry is there. Otherwise, point it at the same command manually (Section 4 below has a worked example for Cursor).

---

## 2. Local AI Configuration Templates

**The rules live in one file, `AGENTS.md`** (REQ-015) — `drunken-init` writes it, plus a one-line
`CLAUDE.md` that imports it, from `src/core/templates/`, the one location that is shipped in the
installed package and is the canonical source for what it writes. `templates/` at this repository's
root is a second, separate set: copy-paste extras for tools `drunken-init` does not configure, each
one thin and pointing at `AGENTS.md` rather than restating anything, because a rulebook per tool is
a rulebook per tool that drifts.

| File | For | What it is |
|---|---|---|
| `AGENTS.md` | every tool | The project's rules: Jira lifecycle, approvals, git, what must never be deleted, where the project's documents are, build and test commands. Written once by `drunken-init`. |
| `CLAUDE.md` | Claude Code | A one-line `@AGENTS.md` import (REQ-015), also written by `drunken-init` — not something you fill in by hand. |
| `templates/.cursorrules` | Cursor | "Read `AGENTS.md`; it is the authority" — plus MCP setup and approvals, the parts that differ for Cursor. Copy-paste; nothing writes this one for you. |
| `templates/CONVENTIONS.md` + `templates/.aider.conf.yml` | Aider | The config loads `AGENTS.md` and `CONVENTIONS.md` read-only into every session and turns off Aider's own commits. Copy-paste. |
| `templates/SESSION_CHECKPOINT.md` | every tool | A handoff note, read at session start, rewritten before ending. Untracked. Jira stays the record. Copy-paste. |
| `templates/PROJECT_BRIEF.md`, `templates/REQUIREMENTS.md` | every tool | Optional pre-`/prd` drafting material — what is built and what it must do, written before `/prd`'s interview instead of during it. Copy-paste. |

Which files to copy, and where, is [GETTING_STARTED.md, Step 1](./GETTING_STARTED.md#step-1--describe-your-project) —
one list, kept in one place.

---

## 3. Workflow Handoff

The lifecycle is the same from the CLI or via MCP:

1. **Intake:** Call `jira_start_task(issue_key)` to claim a ticket and get the branch name to check out. The MCP tools are the only supported path for an agent — no shell script, no local board.
2. **Execution:** Write code and tests against that ticket's acceptance criteria. Before any destructive or merge-worthy action: if the Boss is reading the conversation, just ask them there. Otherwise notify and park -- don't perform the action, and move on to whatever else is unblocked. There is no local board, so "parking" a task is just not doing that step, not a tool call. Pick the answer up **when a task finishes or a session starts -- never mid-task**, because acting on it the moment it lands is how a repo ends up half-changed.
3. **Handoff:** Push the branch, open a PR, then call `jira_submit_for_review(issue_key, pr_link, files_changed)` to move the ticket to In Review with the PR linked.
4. **Validation:** A ticket is Done when its test was seen failing first, is green **on the merged tree**, traces to a requirement, and the Boss merged the PR. `/audit` is what checks that.

---

## 4. Integrating an Existing (Non-Drunken-Guild) Project

To bring an existing project under this same workflow:

### Step 1: Install Drunken-Guild's CLI tools

```bash
git clone https://github.com/sornbuen15/drunken-guild.git
cd drunken-guild
uv tool install .
```

This installs four commands plus two pieces of plumbing: `drunken-init` (create the state directory and register a project), `drunken-doctor` (report where every path and secret actually resolves from, and print the pinned install line), `drunken-usage` (what a run cost) — and `drunken-jira-mcp` (the MCP server, which a host launches) and `drunken-hook` (the permission floor, which `.claude/settings.json` calls). Nobody types the last two.

> **`uv tool install` ignores `uv.lock`**, so the tool environment drifts inside the allowed dependency range -- the deployment carried `mcp` 1.29.0 against a lock pinning 1.28.1 for two releases, both satisfying `<2`, with nothing reporting it. `drunken-doctor` is what reports it, and the same tool writes the pinned requirements and hands you the command:
>
> ```bash
> drunken-doctor --requirements
> ```
>
> `drunken-doctor` reports the gap either way (`deployment.mcp_pin`).

### Step 2: Onboard the project

One command registers it (no MCP file is written into the project — see Step 4):

```bash
python /path/to/drunken-guild/scripts/onboard_project.py existing-project \
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

`--path` is optional: a containerised server that only talks to Jira or Discord has no host checkout to name.

### Step 2b: Prove it, before trusting it

A separate step on purpose. `drunken-init` exiting 0 means a file was written, not that the credential works -- and a search cannot tell you either, because a bad token still returns `200`. `drunken-doctor` asks `/rest/api/3/myself`, which 401s:

```bash
drunken-doctor --project existing-project
```

You want `project.existing-project.jira` to come back naming *you*.

### Step 3: Copy the templates

Follow [GETTING_STARTED.md, Step 1](./GETTING_STARTED.md#step-1--describe-your-project). It is
the one list of what to copy from `templates/` and where each file goes; a second list here is the
kind of copy that drifts. For an existing project, fill `AGENTS.md`'s build and test commands from
what the project already runs — the placeholders read as instructions if left in.

### Step 4: The MCP server

A project carries no `.mcp.json` (REQ-019, DG-457), and `--write-mcp-config` now refuses. Declare the
server once for the machine, at your agent's user level — for Claude Code:

```bash
claude mcp add --scope user drunken-jira-mcp -- "$(command -v drunken-jira-mcp)"
claude mcp list        # drunken-jira-mcp ... Connected
```

This depends on step 1 — the command has to be installed. Name the installed command, never one
inside a project's `.venv`. GETTING_STARTED.md has the Windows form and the check.

For Cursor: **Settings > Features > MCP > Add New Server**, type `command`, `drunken-jira-mcp` with args `--project existing-project`, then the same for the other one.

From here, your local AI reads `AGENTS.md` — directly, through `CLAUDE.md`'s one-line import, or through `templates/.cursorrules` / `templates/.aider.conf.yml`, which point at it — checks Jira via the MCP tools, writes code, and hands off through the same lifecycle described in Section 3.

---
*This document covers integration and handoff only. For Drunken-Guild's own architecture and day-to-day Discord commands, see [Drunken-Guild-Guide.md](./Drunken-Guild-Guide.md).*
