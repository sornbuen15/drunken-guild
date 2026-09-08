# Getting Started with Drunken Guild

From nothing installed to your first completed ticket.

This repo has two halves and you do **not** need both. Start with the AI layer — it needs no
Python, no credentials and no server. Add the runtime only when you want work coordinated on Jira.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Install the AI layer](#install-the-ai-layer)
3. [Add the runtime (optional)](#add-the-runtime-optional)
4. [Step-by-step: your first ticket](#step-by-step-your-first-ticket)
5. [Mid-sprint scenarios](#mid-sprint-scenarios)
6. [Using the multi-agent squad](#using-the-multi-agent-squad)
7. [Where to go next](#where-to-go-next)

---

## Prerequisites

**For the AI layer** — this is all of it:

- [Claude Code CLI](https://claude.ai/code), installed and authenticated
- Git
- macOS / Linux: Bash 3.2+ and `rsync` · Windows: PowerShell 5.1+ or [PowerShell 7+](https://github.com/PowerShell/PowerShell/releases)

**For the runtime**, additionally:

- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- A Jira account, and a Discord bot if you want approvals

---

## Install the AI layer

```bash
git clone https://github.com/sornbuen15/drunken-guild.git
cd drunken-guild
./scripts/install/install_skills.sh    # → ~/.claude/skills/
./scripts/install/install_agents.sh    # → ~/.claude/agents/
```

Windows:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # one-time, only if blocked
.\scripts\install\install_skills.ps1
.\scripts\install\install_agents.ps1
```

Verify — you should see the skill directories and an index:

```bash
ls ~/.claude/skills/
```

### 26 of the 34 skills need nothing else

Architecture, testing, security, UI/UX, Electron, git discipline, debugging — all of
it installs and works standalone.

The remaining 8 plus the `principal-engineer` agent coordinate work on Jira. They call `jira_*`
tools, and without the runtime declared they will **say so and stop** rather than silently falling
back to a file or a shell script. Every one of them names the server it requires in its own
constraints.

If you have no Jira, skip the next section and ignore those 8. Nothing else is affected.

### Skills not authored here

`skills/.external` lists skills that are installed but deliberately not authored in this repo. An
empty file is a claim that there are none — not a default. Do not overwrite anything listed there.

---

## Add the runtime (optional)

This gives you the `jira_*` and approval tools.

```bash
uv sync --extra dev
```

The `--extra dev` is not optional if you intend to run the tests. Without pytest in `.venv`,
`uv run pytest` falls through to whatever `pytest` is on PATH — which may import a different
checkout entirely and pass. The suite refuses to start in that state and tells you so.

Put your credentials in a file **outside any repository**, readable only by you:

```bash
mkdir -p ~/.drunken && chmod 700 ~/.drunken
cat > ~/.drunken/secrets.json <<'JSON'
{ "jira": { "my-project": "your-jira-api-token" } }
JSON
chmod 600 ~/.drunken/secrets.json
```

Register your project. The registry stores a **reference**, never the token — `--jira-credential`
also takes `env://VAR`, `op://vault/item/field` and `keyring://service/user`, and there is
deliberately no flag that accepts a token:

```bash
uv run drunken-init \
  --project my-project \
  --path ~/Projects/my-project \
  --jira-url https://your-domain.atlassian.net \
  --jira-email you@example.com \
  --jira-project-key ABC \
  --jira-credential 'file://~/.drunken/secrets.json#jira.my-project'
```

Check it:

```bash
uv run drunken-doctor --project my-project
```

You want the Jira line to come back naming *you*. Two traps worth knowing:

> **A green line is not proof the project exists.** `drunken-doctor` verifies that the credential
> authenticates, not that the project key is real. It has printed `OK … (project ALPHA)` while Jira
> answered *"No project could be found"*. Confirm the key yourself the first time.

> **Jira answers a bad credential with `200` and an empty list.** That is why checking is a separate
> step and not something a search result would have told you.

Install it as a command so other projects need no paths:

```bash
uv tool uninstall drunken-team   # only if `uv tool list` shows the old name
uv tool install .
```

If a previous version is installed under the old package name, `uv tool install .` fails with
*"Executables already exist"*. `--force` is not the fix — it repoints the symlinks and leaves the
old environment installed, still shipping a `drunken-board-mcp` this package no longer contains.

Then generate the config for **your project** rather than writing it by hand:

```bash
./scripts/install/install_mcp.sh my-project --out ~/Projects/my-project/.mcp.json
```

It prints by default and only writes when you pass `--out`. `--host` (the default) emits absolute
paths and merges, so any other MCP servers that config already declares survive; `--repo` emits the
names-only form, which is what a repository's own `.mcp.json` should carry so one machine's
directory layout never reaches another repo's git history.

---

## Step-by-step: your first ticket

### Step 1 — Describe your project

Copy the context templates into **your project root** and fill them in.

```bash
cp templates/PROJECT_BRIEF.md  ~/Projects/my-project/
cp templates/REQUIREMENTS.md   ~/Projects/my-project/
cp templates/CLAUDE.md         ~/Projects/my-project/CLAUDE.md
```

`CLAUDE.md` is the one that carries the **rules**: which Jira project this is, that Jira is the only
coordination surface, the `TODO → IN PROGRESS → IN REVIEW → DONE` ladder that must never skip
review, the MCP tools available, and your build and test commands.

Fill in every `<angle-bracket>` placeholder and delete what does not apply. Skills and agents read
this file every session — **a placeholder left in reads as an instruction.**

- `PROJECT_BRIEF.md` — what you're building, who for, the stack, constraints, what's out of scope
- `REQUIREMENTS.md` — Must/Should/Could/Won't, performance targets, security requirements, and your
  Definition of Done

> [`examples/00-setup/`](./examples/00-setup/) has both filled in for a fictional task manager.

### Step 2 — Generate your backlog

Open Claude Code inside **your project directory**:

```
/init-project
```

It reads `PROJECT_BRIEF.md` and `REQUIREMENTS.md` and creates one Jira ticket per feature in the
backlog. It prints a summary table, then **halts and asks** before moving anything onto the board.

Urgency lands as a **label** — `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` — not as Jira's `priority` field,
which cannot be set on a team-managed project and reads `Medium` on every issue.

Review the tickets in Jira and edit them there directly.

> [`examples/01-spec-to-backlog/`](./examples/01-spec-to-backlog/)

### Step 3 — Load the sprint queue

```
/refine
```

It probes with `jira_board_info` first — **not every board has a backlog** — then moves tickets on
by urgency label. `CRITICAL` moves immediately; the rest are offered by tier for you to choose.

**It does not transition anything.** Backlog membership and status are separate axes: a ticket moved
onto the board is still `TODO` if that is what it was. On the retired local board, moving a lane
*was* the transition — that is the one translation that does not survive.

> [`examples/02-backlog-refinement/`](./examples/02-backlog-refinement/)

### Step 4 — Size the work

```
/estimate
```

Prints a table: T-shirt size, estimated AI turns, human review effort per ticket.

The table is printed, **not written back**. This Jira has no story points, so the skill has nowhere
to put an estimate and is forbidden to invent one.

Anything rated **XL** gets flagged for splitting — XL tickets outgrow a single agent context window
and produce unreliable output.

> [`examples/03-task-estimation/`](./examples/03-task-estimation/)

### Step 5 — Start the first task

There is no `/next` command. Picking up work is two Jira calls and a habit, not a skill.

Ask the agent to start the next ticket. It should:

1. Read the current working set
2. Pick the highest urgency **label**
3. Call `jira_assign`, then `jira_start_task` — assignee says whose it is, status says where it is
4. Read the relevant project files
5. Propose a full **execution plan** — target files, steps, risk notes

Then it should **halt** and ask whether you approve. This is your last checkpoint before code is
written. Approve, adjust, or send the ticket back to `TODO` and pick another.

> Nothing expires a Jira assignee. If an agent stops mid-ticket, reassign it yourself — that is the
> one thing the retired board did that Jira does not.

### Step 6 — Review and close

The agent calls `jira_submit_for_review` — the ticket goes to `IN REVIEW`, never straight to `DONE`.
**Never skip `IN REVIEW`, including for your own work.**

A ticket in `IN REVIEW` is not merged code. Run the suite and read the diff against the target
branch before believing any claim that it is fixed. Then transition it, and commit:

```bash
git commit -m "feat: add user authentication (register/login/JWT)"
```

---

## Mid-sprint scenarios

### A bug arrives while a ticket is in flight

Do **not** interrupt the current ticket.

```
/issue
```

Describe the bug. The skill runs read-only diagnosis, creates a ticket with the root cause and an
urgency label, and leaves your in-flight work untouched. Pick it up when the current ticket reaches
`IN REVIEW` — or sooner if it outranks what you are holding.

### End-of-sprint snapshot

```
/report
```

What's done, what's in progress, what's queued, what's blocked. Useful for async standups.

---

## Using the multi-agent squad

The workflow above runs skills in your own session. For larger autonomous work, delegate to the
squad:

```bash
claude --agent principal-engineer
```

> "Read `PROJECT_BRIEF.md` and `REQUIREMENTS.md`. Analyse the project and give me a platform
> strategy, an initial ADR, and a squad plan."

The orchestrator assembles the squad and delegates with context-rich prompts. The three tiers are
described in the [README](./README.md#the-three-tier-system).

---

## Where to go next

| | |
|---|---|
| [`skills/INDEX.md`](./skills/INDEX.md) | every skill, its trigger and its path |
| [`agents/INDEX.md`](./agents/INDEX.md) | every agent and when to invoke it |
| [`Drunken-Guild-Guide.md`](./Drunken-Guild-Guide.md) | the Discord command reference and approval flow |
| [`Integration-Guide.md`](./Integration-Guide.md) | bringing another project under this workflow |
| [`CLAUDE.md`](./CLAUDE.md) | the rules, if you are going to contribute here |

A few commands worth knowing early:

| Command | When |
|---|---|
| `/system-design` | before writing any new system or API |
| `/clean-arch` | designing or reviewing layer structure |
| `/secure` | any auth, data handling, or new endpoint |
| `/tdd` | fixing a bug, or writing tests |
| `/isolate` | a command has failed the same way twice |
