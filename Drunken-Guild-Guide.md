# Drunken Guild: The Guild Guide

This is the operating manual for Drunken-Guild ("the Guild"). It covers the architecture, how to install and run it, and how to use the Jira workflow and the Discord bot day to day.

*(This document explains how the Guild's own automation works. For an individual project's feature specs or system design, see that project's own `PROJECT_SPEC.md`/`DESIGN.md`.)*

---

## 1. What Drunken-Guild Is

Drunken-Guild is a small orchestration layer, not a framework you code against. It has three moving parts:

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
git clone https://github.com/sornbuen15/drunken-guild.git
cd drunken-guild
uv sync
```

### 3.3 Configure credentials

There are two halves: the **secret itself**, which lives outside the repository, and the **registry**, which holds only a reference to it.

**1. The secret.** One JSON file under `$DRUNKEN_HOME`, owner-readable only:

```bash
mkdir -p ~/.drunken && chmod 700 ~/.drunken
cat > ~/.drunken/secrets.json <<'JSON'
{ "jira": { "drunken-guild": "your-jira-api-token" } }
JSON
chmod 600 ~/.drunken/secrets.json
```

One file can hold every project's credential — the reference's `#jira.drunken-guild` fragment is a dotted path into it.

**2. The registry.**

```bash
uv run drunken-init \
  --project drunken-guild \
  --path "$PWD" \
  --jira-url https://your-domain.atlassian.net \
  --jira-email you@example.com \
  --jira-project-key DG \
  --jira-credential 'file://~/.drunken/secrets.json#jira.drunken-guild' \
  --discord-channel 123456789012345678
```

This writes one central registry under `$DRUNKEN_HOME` (default `~/.drunken`, mode 700) -- not into the project. The command is non-interactive and idempotent, so it also works inside a Dockerfile or a provisioning script.

**Credentials are referenced, never stored.** `--jira-credential` accepts `file://path#key.path`, `env://VAR`, `op://vault/item/field` or `keyring://service/user`, and there is deliberately no flag that takes a token. A reference with no scheme is an error rather than a literal; `literal://` is the visible opt-out.

> Why `file://` rather than `env://` for a local install: the MCP servers are launched as subprocesses by whatever AI tool you use, and that tool's environment is not your shell's. An `env://` reference resolves only if the variable is exported by whatever starts the tool — which is the kind of invisible configuration that makes a setup work on one machine and nowhere else. `file://` is also exactly what a mounted secret volume looks like later.

**Migrating from an older release.** If you already have a working `.env`, this does both halves without ever printing the token:

```bash
uv run python scripts/migrate_env_to_registry.py --project drunken-guild --dry-run
uv run python scripts/migrate_env_to_registry.py --project drunken-guild
```

**3. Prove it resolves.** A separate, deliberate step, because Jira answers a search with `200` and `[]` when the credential is bad -- so searching cannot tell you whether it worked. `drunken-doctor` asks `/rest/api/3/myself`, which 401s:

```bash
uv run drunken-doctor --project drunken-guild
```

`project.drunken-guild.jira` should come back naming *you*. Until you start the daemon, a warning about a missing socket is expected.

**The `.env` file is still needed** -- the Discord daemon reads its own bot token from there directly, and `scripts/jira_bridge.py` uses it for shell work:

```bash
cp .env.example .env
```

`.env.example` documents every variable the project reads with inline comments. `.env` is gitignored -- your real values never get committed.

### 3.4 Register the MCP servers (for an AI coding agent)

**A fresh clone has no `.mcp.json`, and nothing will tell you.** The file is operating config, not
source — it names which project each server serves — so DG-250 keeps it out of git and DG-313
untracked it here. Untracked does not mean optional: **every checkout needs its own**, or an agent
opened there has no `drunken-jira-mcp` tools at all. There is no error. The tools are simply absent,
and the session falls back to driving Jira by hand.

Generate it, in the checkout, once:

```bash
uv run drunken-config --project <PROJECT-ID> --kind mcp --out .mcp.json
```

That writes exactly this — **two** servers, named as commands, with no path anywhere:

```json
{
  "mcpServers": {
    "drunken-jira-mcp":    { "command": "drunken-jira-mcp",    "args": ["--project", "<PROJECT-ID>"] },
    "drunken-discord-mcp": { "command": "drunken-discord-mcp", "args": ["--project", "<PROJECT-ID>"] }
  }
}
```

Two servers, not three: `drunken-board-mcp` was retired with the local board (DG-250/DG-265) and is
no longer packaged. If you find a config naming it, that config predates the retirement.

**Names, never paths.** An absolute path here is one machine's directory layout in everyone else's
repository. The command form depends on §3.2 having run `uv tool install .`, so the two executables
are on `PATH`. Without that, and only then, fall back to the checkout-relative form — and note it
works *only* from inside that checkout, silently doing nothing from anywhere else:

```json
{ "command": "uv", "args": ["run", "--directory", "/abs/path/to/drunken-guild",
                            "drunken-jira-mcp", "--project", "<PROJECT-ID>"] }
```

> **`--project` is required on both servers (DG-313).** It is not decoration on the Discord one:
> it selects which daemon socket the server dials, and therefore which Discord room approvals
> reach — see §7.1. Omit it on a machine with more than one project registered and approvals post
> into whichever project's daemon answers first. Do **not** put a channel id here; the project id
> is the reference and the registry holds the value.

Which project a server acts on comes from `--project <id>`, resolved against the registry — never
from the working directory.

**Regenerating is always safe.** The file is derived entirely from the registry, so if you are ever
unsure whether it is current, write it again. Re-run the command above after anything that changes
a project's id, or after upgrading to a release that adds or retires a server.

**Your agent reads it at startup.** Writing the file into a session that is already open changes
nothing until that session is restarted — which is the confusing part of getting this wrong: you
fix it, and nothing appears to happen.

If your agent supports project-level `.mcp.json` discovery, this works out of the box. For Cursor
and others that do not, see the [Integration Guide](./Integration-Guide.md).

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

> **One daemon per project (DG-313), so install one per project.** The daemon binds
> `~/.drunken/daemon-<project>.sock`, named after the project it serves, and the MCP server started
> with `--project <id>` dials that same name. `setup_daemon_service.py install` writes
> `DRUNKEN_PROJECT` into the launchd plist for you — matched against the registry's own `path`
> field, not guessed from the directory name — and `--project <id>` installs one for a project
> other than this checkout's:
>
> ```bash
> uv run python scripts/setup_daemon_service.py install --project alpha
> ```
>
> A daemon already running keeps its old socket until restarted. See §7.1 for the full resolution
> order and for what the pre-DG-313 behaviour looked like, which you will still meet on any machine
> whose daemon has not been restarted.

### 3.6 Prove it works, before trusting it

Every step below can pass while the next one fails, which is why they are separate. Work down the
list; each names what its failure actually looks like, because none of them announce themselves.

**1 — The commands exist.**

```bash
which drunken-jira-mcp drunken-discord-mcp
```

Both should resolve under `~/.local/bin/`. A path inside a `.venv` works until that venv is rebuilt
and then fails with no obvious connection to the cause. Nothing at all means §3.2 has not run.

**2 — The registry knows the project, and the credential works.**

```bash
drunken-doctor --project <PROJECT-ID>
```

Look for `project.<id>.jira` naming *you*. This asks `/rest/api/3/myself`, which 401s on a bad
credential — **a Jira search cannot tell you this**, because it answers a dead credential with
`200` and an empty list. A board with 39 issues on it once read as empty for months that way.

Two warnings here are worth acting on rather than skimming past:

- `deployment.tool_env` — the installed tool is a different revision from this checkout. It lists
  the files that differ. Fix with `uv tool install . --reinstall`. **Every module being present
  says nothing about which revision of it is there**, which is why the check compares content.
- `deployment.mcp_pin` — `uv tool install` ignores `uv.lock`, so the deployment drifts inside the
  allowed range. `drunken-config --project <id> --kind install` gives you the pinned command.

`drunken-doctor` verifies that a credential *works*. It does **not** verify that the project key
exists — it once printed `OK … (project XYZ)` while Jira answered *"No project could be found"*
(DG-260). If the key is new, check it directly.

**3 — The MCP config exists and names the right project.**

```bash
cat .mcp.json
```

Missing entirely is the common case on a fresh clone — see §3.4. Wrong `--project` is the quieter
one: the server starts, the tools appear, and every ticket goes to another project's board.

**4 — The server starts.**

```bash
drunken-jira-mcp --project <PROJECT-ID> --help
```

Exit 0 means the entry point resolves and its dependencies import. This is worth doing separately
because a host that cannot start a server usually reports it as *"the process exited"* with nothing
about why.

**5 — Your agent can see the tools.** Restart the session first — **`.mcp.json` is read at startup,
so a file written into an open session changes nothing.** That is the confusing part of getting
this wrong: you fix it, and nothing appears to happen. Then ask the agent to list a few tickets;
`jira_search_issues` answering is the proof.

If the tools are absent, the agent is not failing — it never had them. It will quietly fall back to
`scripts/jira_bridge.py`, which works, so the symptom is slowness rather than an error.

**6 — The daemon is up, on the right socket.**

```bash
uv run python scripts/setup_daemon_service.py status
ls ~/.drunken/*.sock
```

You want `daemon-<project>.sock` for each project you installed. A bare `daemon.sock` means a
pre-DG-313 daemon is still running — it keeps its old socket until restarted, and it has
`KeepAlive`, so it comes back if you only kill it. Re-run `install`, which unloads the old agent
as part of its job.

**7 — A real approval reaches the right room.** This is the only step that proves the thing anyone
actually cares about, and **no tool can do it for you**: `drunken-doctor` checks that a channel id
is *set*, not that the bot is in that room, and not that a daemon binds that socket.

Ask your agent for something needing permission, or turn away mode on and run any command that is
not allowlisted:

```bash
uv run drunken-away on --note "testing the approval path"
# ... trigger a prompt, answer it in Discord with 👍 ...
uv run drunken-away off
```

Then check the room. **Which room it lands in is the test** — on a multi-project machine the
pre-DG-313 failure was that approvals arrived somewhere real, reported success, and were simply
never seen by whoever was waiting.

`uv run drunken-away off` is deliberately allowlisted, so you cannot strand yourself with away mode
on and no way to answer.

**8 — Sending messages from Discord.** Once the daemon is up the bot takes commands in its room —
`/status`, `/project`, and the read-only Jira and PR queries. The full list is §5; the approval
protocol is §6.

---

## 4. Jira Workflow

Jira is the only place task state lives. The board has four lanes: **Backlog -> To Do -> In Progress -> In Review -> Done** (Backlog is derived, not a native Jira status -- see below).

### 4.1 The `drunken-jira-mcp` tools (supported path)

An AI agent with the MCP server registered (Section 3.4) uses these directly -- no shell-out, no
separate credential handling:

| for | use |
|---|---|
| search / status | `jira_search_issues` |
| claim and start | `jira_start_task` |
| move status | `jira_transition_issue` |
| hand off for review | `jira_submit_for_review` |
| leave a note | `jira_add_comment` |
| claim / release | `jira_assign` -- an email, a display name, `"me"`, or `"none"` |
| board membership | `jira_board_info`, `jira_move_to_backlog`, `jira_move_to_board` |

### 4.2 `scripts/jira_bridge.py` (shell fallback only)

Still works for a terminal with no MCP-capable agent attached, but it is not the supported path --
prefer the tools above whenever an agent is doing the work:

```bash
uv run python scripts/jira_bridge.py get-todo          # priority DESC, created ASC
uv run python scripts/jira_bridge.py transition DG-42 "In Progress"
uv run python scripts/jira_bridge.py comment DG-42 "Investigated -- root cause was X."
```

### 4.3 The full lifecycle for one ticket

```
1. jira_search_issues("status = 'To Do' ORDER BY ...") -> pick one
2. jira_assign(key, "me"), then jira_start_task(key) -> In Progress, branch name returned
3. git checkout -b feature/DG-42-short-description
   ... write code, tests, commit ...
4. Open a PR, then jira_submit_for_review(key, pr_link, files_changed) -> In Review
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
      `DG-90` [Medium] Reconcile Drunken-Guild-Guide.md and README.md
      `DG-95` [Medium] Add token/cost tracking for agent runs
      `DG-104` [Medium] ...
```

### 5.3 Workflow actions

| Command | Example | What it does |
|---|---|---|
| `/project [name]` | `/project alpha` | Show, or switch, which registered project the commands above (and `/next`/`/refine`) target. No argument shows the current one. |
| `/next` | `/next` | If nothing is In Progress, pick the top of To Do and transition it there. Refuses if a ticket is already In Progress. |
| `/refine` | `/refine` | Auto-promote any Critical-priority backlog ticket straight to To Do; report a priority breakdown of everything else (no auto-promotion for non-Critical). |
| `/approve <ticket>` | `/approve DG-42` | Clear an escalated (timed-out) approval block on a ticket and re-dispatch the work with the original context, so it isn't stuck forever. |
| `/qa` | `/qa` | Run the round-integration QA gate in the background; replies to its own acknowledgement message when done. |

Example:
```
You:  /next
Bot:  ▶️ DG-42 moved to In Progress.
      Fix flaky test in test_discord_router.py

You:  /refine
Bot:  **Backlog refinement** (4 total)
      🔺 Auto-promoted Critical -> To Do: DG-101
      **Medium** (2): DG-95, DG-104
      **Low** (1): DG-88
```

### 5.4 Anything not starting with `/`

Free-form natural-language task commanding is disabled. Any plain message gets one fixed reply pointing you at `/help`. This is a deliberate, tracked decision (Jira ticket DG-94), not an oversight -- it avoids the cost, latency, and prompt-injection surface of a free-text router while still covering the day-to-day Jira/PR operations above.

---

## 6. Approval Flow

Some agent actions require your explicit sign-off (e.g. a destructive command, or a merge). **If you are reading the agent's conversation, it should simply ask you there.** Discord is for when you are not watching.

Unattended, asking must never stop the rest of the work:

1. The agent calls `request_boss_approval_async(action, reason, ticket_key)`, which returns a `req_id` immediately, and the bot posts the question to Discord with 👍/👎 reactions attached.
2. The agent doesn't perform that action yet and picks up whatever else is unblocked. There is no
   local board (DG-265) -- "parking" a task means exactly that and nothing more; no tool call marks
   it blocked.
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

Drunken-Guild can operate on more than one codebase. One central registry -- `projects.json` under `$DRUNKEN_HOME` (default `~/.drunken`) -- answers "which Jira, which repo, which Discord channel" for every project:

```json
{
  "version": 2,
  "projects": {
    "drunken-guild": {
      "path": "/Users/you/Projects/drunken-guild",
      "description": "The Guild Headquarters",
      "jira": {
        "url": "https://your-domain.atlassian.net",
        "email": "you@example.com",
        "project_key": "DG",
        "credential": "env://JIRA_API_TOKEN"
      },
      "discord": { "channel_id": "123456789012345678" }
    },
    "alpha": {
      "description": "Another project on the same Jira site",
      "jira": {
        "url": "https://your-domain.atlassian.net",
        "email": "you@example.com",
        "project_key": "ALPHA",
        "credential": "env://JIRA_TOKEN_ALPHA"
      }
    }
  }
}
```

Nothing in it is secret -- credentials appear only as references -- so it can be committed, reviewed and shared, which is exactly what stops five copies of a token drifting apart in five `.env` files. `path` is optional: only the file-backed board needs a checkout on disk, and a containerised Jira or Discord server has no host path to give.

Add an entry with `drunken-init --project <id> ...` (Section 3.3) rather than by hand. A v1 registry -- the bare `{"name": {...}}` map written by earlier releases -- is upgraded in memory on read and never rewritten behind your back, so downgrading is just running the old code again.

Once registered, `/project <name>` in Discord switches which project the Jira-lane commands and `/next`/`/refine` operate against -- each project can have its own Jira project key, so `/project alpha` then `/tasks` lists that project's own To Do lane, not drunken-guild's.

### 7.1 One daemon per project, and the socket name is what joins them

`/project` switches Jira-lane routing for commands already reaching the bot. Which Discord room an
**approval** reaches is a different question, answered before the bot sees anything: the
`ApprovalManager` is handed its channel **at construction**, read once when the daemon starts. No
per-request argument can reach it. So the split has to be one daemon per project, and it is
(DG-313).

**The socket name carries the project.** That is what makes the two ends meet with no second knob
to keep in sync:

```
drunken-discord-mcp --project alpha   →  dials   daemon-alpha.sock
DRUNKEN_PROJECT=alpha drunken-listen  →  binds   daemon-alpha.sock
```

Neither is told the other's socket. Resolution order, first match wins:

1. **`--project <id>`** on the MCP server, or **`DRUNKEN_PROJECT`** for the daemon.
2. **`DRUNKEN_PROJECT`** in the environment.
3. **The registered project whose own `path` contains the working directory.**
4. Otherwise the unchanged **`daemon.sock`**.

**Step 3 is not decoration.** The pre-commit approval check, the away-mode hook and
`drunken-doctor` all dial the daemon from a plain shell with no `DRUNKEN_PROJECT` set. Without it
they would stay on `daemon.sock` while the daemon moved, and the approval gate would go quiet. It
matches on the registry entry's `path`, never the directory name — a checkout need not be named
after its key.

Install one per project, from any checkout:

```bash
python scripts/setup_daemon_service.py install                 # this checkout's project
python scripts/setup_daemon_service.py install --project alpha
python scripts/setup_daemon_service.py install --project beta
```

The LaunchAgent label carries the project too, or installing a second one overwrites the first
one's plist. Both install and uninstall unload the **pre-DG-313 un-suffixed agent**: it has
`KeepAlive`, so left loaded it resurrects a second daemon on the shared socket — the exact
cross-posting this removes. A daemon already running keeps its old socket until it is restarted.

> **What this replaced, so the old behaviour is recognisable if you meet it.** There used to be
> exactly one Discord identity per machine, chosen at startup: `DRUNKEN_PROJECT` if set, otherwise
> **the first project in the registry declaring a `discord` block** — registration order, nothing
> about which project you meant. On a multi-project machine every approval from every other project
> posted to that first channel while both ends reported success:
> `request_boss_approval_async` returned a `req_id`, nothing errored, and the message simply never
> reached the room anyone was watching. The multi-tenant daemon had been cut, back when this ran
> one project, on the premise that nobody drives more than one; that premise is gone, and DG-313
> reversed it.

**`drunken-doctor` cannot confirm this for you.** It checks that a channel id is *set* — not that
the bot is in that room, and not that any daemon binds that socket. Confirm it the only way that
means anything: raise one real approval and watch which room it lands in.

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
