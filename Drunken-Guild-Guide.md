# Drunken Guild: The Guild Guide

This is the operating manual for Drunken-Guild ("the Guild"). It covers the architecture, how to install and run it, and how to use the Jira workflow day to day.

*(This document explains how the Guild's own automation works. For an individual project's brief, requirements, spec, architecture or policy, see that project's own documents — usually in its `.ai/` directory; the `project-docs` skill lists every place they are looked for.)*

---

## 1. What Drunken-Guild Is

Drunken-Guild is a small orchestration layer, not a framework you code against. It has three moving parts:

- **Jira** is the single source of truth for tasks. There is no local task file or board -- every ticket's status lives in Jira, and every command below reads or writes it directly.
- **An MCP server** exposes Jira operations as tools an AI agent (Claude Code, etc.) can call directly while it works.
- **A notifier** posts one line and a link to Discord when something wants a person: a PR is ready, today's MVP is up, an audit found gaps, an agent needs a decision.

What it deliberately does **not** do: there is no dashboard UI (Jira alone covers status), and Discord is **one-way** -- there is nothing to type at, and no action can be authorised from it. An agent that needs permission asks the person reading its output.

---

## 2. Architecture

| Component | File | Purpose |
|---|---|---|
| Project Registry | `src/core/registry.py` | One file (`projects.json` under `$DRUNKEN_HOME`) holding every project's Jira, checkout path and notification webhook, so a command can target a project other than the one you are standing in. Credentials appear only as references. |
| Jira MCP server | `src/jira_mcp/server.py` | Exposes Jira operations as MCP tools/resources/prompts for a coding agent to call directly (see the [Integration Guide](./Integration-Guide.md)). |
| Notifier | `src/core/notify.py` | One POST to a Discord webhook: a line and a link. Never raises, and says why when it could not send -- nobody is blocked by a notification, which is exactly why a silent failure would go unnoticed. |
| Permission floor | `src/core/hook.py` | The PreToolUse hook. Refuses what `.claude/settings.json` denies, and refuses a call it cannot read; silent about everything else, because it has no authority to widen permission. |

### 2.1 AI behavior boundaries

The detailed rules an AI agent must follow while working in this repo (when it can act immediately, when it must ask, what's forbidden outright) live in [`CLAUDE.md`](./CLAUDE.md) -- that file is the source of truth for agent-facing rules, whichever agent is reading it, kept separate here to avoid two documents drifting out of sync. In short: a destructive or merge-worthy action is asked about in the conversation, not simply executed.

---

## 3. Installation & Setup

### 3.1 Prerequisites
- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (package manager and script runner)
- Git
- A Jira Cloud account with an API token
- Optionally, a Discord **webhook URL** for notifications (channel settings → Integrations → Webhooks). Nothing else about Discord is needed: the Guild only posts to it.

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

**Storing or rotating the token.** Put it into `secrets.json` without it ever being printed or reaching shell history — the value is read from a hidden prompt:

```bash
uv run python scripts/set_secret.py jira.default
```

**3. Prove it resolves.** A separate, deliberate step, because Jira answers a search with `200` and `[]` when the credential is bad -- so searching cannot tell you whether it worked. `drunken-doctor` asks `/rest/api/3/myself`, which 401s:

```bash
uv run drunken-doctor --project drunken-guild
```

`project.drunken-guild.jira` should come back naming *you*.

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

That writes exactly this — named as a command, with no path anywhere:

```json
{
  "mcpServers": {
    "drunken-jira-mcp": { "command": "drunken-jira-mcp" }
  }
}
```

One server, where there were three: `drunken-board-mcp` was retired with the local board
(DG-250/DG-265), and the approval server with the Discord machinery (DG-355). If you find a config
naming either, that config predates the retirement — regenerating prunes it.

**Names, never paths.** An absolute path here is one machine's directory layout in everyone else's
repository. The command form depends on §3.2 having run `uv tool install .`, so the executable is
on `PATH`. **And no project:** the same entry is correct for every project, because each tool takes
the registry project id as its first argument. Without that, and only then, fall back to the checkout-relative form — and note it
works *only* from inside that checkout, silently doing nothing from anywhere else:

```json
{ "command": "uv", "args": ["run", "--directory", "/abs/path/to/drunken-guild",
                            "drunken-jira-mcp", "--project", "<PROJECT-ID>"] }
```

> **The project arrives per call, not per server (DG-341).** A tool called with no project, or with
> an id the registry does not have, is refused with the registered ids named — it never guesses,
> because a server that guessed would quietly file work onto somebody else's board. That is not
> hypothetical: an entry registered at user scope reaches every session on the machine, and one
> pinned to `drunken-guild` answered sessions that were not it.

Which project a call acts on comes from its first argument, resolved against the registry — never
from the working directory, and never from how the server was started.

**Regenerating is always safe.** The file is derived entirely from the registry, so if you are ever
unsure whether it is current, write it again. Re-run the command above after anything that changes
a project's id, or after upgrading to a release that adds or retires a server.

**Your agent reads it at startup.** Writing the file into a session that is already open changes
nothing until that session is restarted — which is the confusing part of getting this wrong: you
fix it, and nothing appears to happen.

If your agent supports project-level `.mcp.json` discovery, this works out of the box. For Cursor
and others that do not, see the [Integration Guide](./Integration-Guide.md).

### 3.6 Prove it works, before trusting it

Every step below can pass while the next one fails, which is why they are separate. Work down the
list; each names what its failure actually looks like, because none of them announce themselves.

**1 — The commands exist.**

```bash
which drunken-jira-mcp
```

It should resolve under `~/.local/bin/`. A path inside a `.venv` works until that venv is rebuilt
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

Missing entirely is the common case on a fresh clone — see §3.4. There is no wrong project to
configure any more: the file carries none.

**4 — The server starts.**

```bash
drunken-jira-mcp --help
```

Exit 0 means the entry point resolves and its dependencies import. This is worth doing separately
because a host that cannot start a server usually reports it as *"the process exited"* with nothing
about why.

**5 — Your agent can see the tools.** Restart the session first — **`.mcp.json` is read at startup,
so a file written into an open session changes nothing.** That is the confusing part of getting
this wrong: you fix it, and nothing appears to happen. Then ask the agent to list a few tickets;
`jira_search_issues` answering is the proof.

If the tools are absent, the agent is not failing — it never had them, and there is no fallback
left to hide it. The symptom is an agent updating Jira by asking you to.

**6 — A notification reaches the room.** No tool can confirm this for you: `drunken-doctor`
checks that a webhook reference *resolves*, not that the room you are watching is the one behind
it. Send one and look:

```bash
uv run python -m core.notify "checking the notification path" --link https://example.com
```

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

### 4.2 The full lifecycle for one ticket

```
1. jira_search_issues("status = 'To Do' ORDER BY ...") -> pick one
2. jira_assign(key, "me"), then jira_start_task(key) -> In Progress, branch name returned
3. git checkout -b feature/DG-42-short-description
   ... write code, tests, commit ...
4. Open a PR, then jira_submit_for_review(key, pr_link, files_changed) -> In Review
5. The Boss merges the PR; the ticket is verified against the merged tree and transitions to Done.
```

---

## 5. Notifications and approvals

Discord is one-way. There is no bot to talk to, no commands to type at it, and nothing to react to
— what arrives is a notification carrying a link, for the four things worth interrupting someone
over: **a PR is ready, today's MVP is up, an audit found gaps, an agent needs a decision.**

Sent by `core.notify`, from a hook or from CI:

```bash
uv run python -m core.notify "PR #80 is ready for review" --link https://github.com/x/y/pull/80
```

The webhook URL is a credential — anyone holding it can post as the bot — so it is configured as a
*reference*, never as the URL itself:

```bash
uv run drunken-init --project <id> --discord-webhook env://DISCORD_WEBHOOK_URL
```

Notifications are optional. A project with no webhook configured is not misconfigured, and
`drunken-doctor` reports that as `skip` rather than a fault.

**Approvals happen in the conversation.** When an agent needs permission it asks the person reading
its output, which is where the answer was always going to come from. What no answer can grant at
all — a force push, a hard reset, a recursive delete, reading `.env` — is refused by
`.claude/settings.json` and by the `drunken-hook` deny floor, which is evaluated before anything
else and has nothing to consult. See the `ask-boss` skill.

---

## 6. Multi-Project Orchestration

Drunken-Guild can operate on more than one codebase. One central registry -- `projects.json` under `$DRUNKEN_HOME` (default `~/.drunken`) -- answers "which Jira, which repo, which webhook" for every project:

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
      "discord": { "webhook": "env://DISCORD_WEBHOOK_URL" }
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

Nothing in it is secret -- credentials appear only as references -- so it can be committed, reviewed and shared, which is exactly what stops five copies of a token drifting apart in five `.env` files. `path` is optional: a containerised server has no host path to give.

Add an entry with `drunken-init --project <id> ...` (Section 3.3) rather than by hand. A v1 registry -- the bare `{"name": {...}}` map written by earlier releases -- is upgraded in memory on read and never rewritten behind your back, so downgrading is just running the old code again.

Each project carries its own Jira project key, so the tools always act on the project they were asked about and never on whichever one was registered first.

## 7. The quality gate

There is no separate gate process. A ticket is Done when its test was **seen failing first**, is
green **on the merged tree**, traces to a requirement, and the Boss merged the PR. `/audit` is what
checks that, and `skills/workflow/jira-tickets/SKILL.md` §7 is the list to verify against.

---

## 8. Where to Go Next

- Connecting an external AI coding tool (Claude Code, Cursor, Aider) to this Guild: [Integration Guide](./Integration-Guide.md)
- Contributing code, branching, and PR conventions: [CONTRIBUTING.md](./CONTRIBUTING.md)
