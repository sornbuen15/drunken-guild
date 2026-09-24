# Drunken Guild

A guild is a craftsmen's association that holds a shared standard. That is what this is: **one
repository holding the standard other projects copy** — the skills and agents that direct AI coding
agents, and the MCP servers that let them coordinate real work through Jira and Discord.

The name says drunk. The contents are FATAL directives, blast-radius checks and post-mortems. Both
halves are meant.

---

## Two halves, one repository

| | what it is | where |
|---|---|---|
| **The AI layer** | 11 skills and 3 team roles, installed into `~/.claude/` | `skills/`, `agents/` |
| **The runtime** | Python MCP servers and a CLI — Jira coordination, Discord approvals, cost accounting, health checks | `src/`, `scripts/` |

They are one repository on purpose. They used to be two, and the two drifted: skills were authored
in four places with 26 duplicated by name, and `git-workflow` silently diverged to 73 lines against
196 while a just-merged PR told one repo to defer to the other's copy. One surface is the answer.

**You can use either half alone.** Most skills need no MCP server. Only the coordination skills do,
and each one names the server it requires.

> **Being re-scoped to 2.0.0.** Agent-specific plumbing — the Antigravity hook, install trees and
> copy of the rules — was retired in DG-349; the target is one vendor-neutral set of rules any agent
> can read. Current status lives in this repo's own `SESSION_CHECKPOINT.md`.

---

## Quick start — the AI layer

No Python, no credentials, no server. Clone and install:

```bash
git clone https://github.com/sornbuen15/drunken-guild.git
cd drunken-guild
./scripts/install/install_skills.sh    # → ~/.claude/skills/
./scripts/install/install_agents.sh    # → ~/.claude/agents/
```

Add `--index-only` to rebuild `INDEX.md` without installing anything.

> The PowerShell pair has no `--index-only`. The
> gap is stated in each script's header: there is no Windows machine here to test against, and an
> untested installer writing into a shared config directory is worse than one that does less.

Windows (PowerShell):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # one-time, if blocked
.\scripts\install\install_skills.ps1
.\scripts\install\install_agents.ps1
```

Then invoke a skill by its trigger — `/prd`, `/breakdown`, `/build`, `/isolate` — or hand work
to an agent. `skills/INDEX.md` and `agents/INDEX.md` list every one with its path and trigger.

## Quick start — the runtime

```bash
uv sync
```

Put credentials in a file **outside the repository**, readable only by you:

```bash
mkdir -p ~/.drunken && chmod 700 ~/.drunken
cat > ~/.drunken/secrets.json <<'JSON'
{ "jira": { "drunken-guild": "your-jira-api-token" } }
JSON
chmod 600 ~/.drunken/secrets.json
```

Register the project. The registry stores a **reference** to that file, never the token —
`--jira-credential` also accepts `env://VAR`, `op://vault/item/field` and `keyring://service/user`,
and there is deliberately no flag that takes a token:

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

Prove it resolves. This is a separate step on purpose, because Jira answers a search with `200` and
`[]` when the credential is bad:

```bash
uv run drunken-doctor --project drunken-guild
```

You want `project.drunken-guild.jira` to come back naming *you*.

> `drunken-doctor` checks that the credential works — **not that the Jira project exists.** It has
> printed `OK … (project ALPHA)` while Jira answered *"No project could be found"*. Verify the key
> against the API before trusting a green line.

### Installing it as a command

If a previous version is installed under the old package name, **uninstall it first**:

```bash
uv tool uninstall drunken-team   # only if `uv tool list` shows it
uv tool install .
```

`uv tool install .` fails with *"Executables already exist"* while the old package owns those
names, and **`--force` is not the fix**: it repoints the symlinks but leaves the previous tool
environment installed, and that environment still ships `drunken-board-mcp`, which is no longer
part of this package (DG-265). Uninstalling first is what actually removes it from your PATH.

```bash
drunken-doctor --project drunken-guild
```

Another project's `.mcp.json` then names the command and nothing else, which keeps one machine's
directory layout out of another repo's git history:

```json
{
  "mcpServers": {
    "drunken-jira-mcp": { "command": "drunken-jira-mcp" }
  }
}
```

> `uv tool install` ignores `uv.lock`, so the tool environment can drift inside the allowed
> dependency range. Pass `--with-requirements` if you need it pinned.

---

## How the AI layer is organised

### Skills vs agents

A **skill** is a standard — how to write a ticket, how to review for security, how to debug. It
loads into whatever agent is already working. An **agent** is a role with its own model, tool set
and system prompt. Skills are the craft; agents are the craftsmen.

### Three roles

```
manager   — reads the project's documents, proposes the plan and its order; the Boss approves
worker    — implements one approved task: test first, smallest change, PR for a human to merge
reviewer  — one round on the plan, tests before implementation, the PR before merge; never merges
```

One agent can play all three, or a team can split them. The fifteen specialist agents that came
before these roles — fintech, insurance, mobile, desktop, voice, AI systems and the original
generalists — live on unchanged as the optional `drunken-extras` plugin in
[`plugins/drunken-extras/`](./plugins/drunken-extras/).

### The flow — seven commands

Six run in order; `/replan` runs whenever a requirement is added, cut or changed after the backlog
exists. Each owns one stage of the standard spec-driven sequence:

| stage | step |
|---|---|
| requirement | `/prd` |
| clarify | `/clarify` |
| spec | `/ddd` |
| plan and tasks | `/breakdown` |
| implement | `/build` |
| validate | `/audit` |
| replan | `/replan` |

```
/prd        →  PRD.md: the brief and the requirements in one file, every requirement
               carrying an id REQ-xxx and a MoSCoW class
/clarify    →  a short ranked list of decisions only the Boss can make, answered back
               into PRD.md
/ddd        →  DOMAIN.md: bounded contexts, shared vocabulary, core entities.
               Each context becomes an Epic
/breakdown  →  the Jira hierarchy — REQ → Epic → Story → Task → Subtask — every level
               labelled req:REQ-xxx. Nothing is created until the Boss approves the plan
/build      →  one task, one branch, one PR. The test comes from the ticket's acceptance
               and is seen failing first. The Boss merges
/audit      →  every requirement traced to a task and to a test that passes on the merged
               tree. Gaps become tickets; the day's report is written
/replan     →  a requirement moved after the backlog exists: PRD.md first, then only the
               tickets whose req: label names it. Never orders the work — the Boss does
```

A Task is a vertical slice finishable in a day. Where a project's documents live is the
`project-docs` skill's contract — the project's root `AGENTS.md` is the map, and the defaults
when there is no map are `.ai/PRD.md`, `.ai/DOMAIN.md`, `.ai/audit/`, `docs/` and
`docs/decisions/`.

**Where to deploy is deliberately not part of the standard.** No skill assumes a target; the
first time it matters, the AI asks the project owner and records the answer in that project's
`AGENTS.md`.

### Skill categories

`flow` · `workflow` · `documents` — the skills the flow uses. The general engineering standards
(architecture, security, UI/UX, testing, cloud, product, leadership) moved unchanged to the optional
`drunken-extras` plugin in [`plugins/drunken-extras/`](./plugins/drunken-extras/).

Full catalogue with triggers: [`skills/INDEX.md`](./skills/INDEX.md).

---

## Documentation

| | for whom |
|---|---|
| [`GETTING_STARTED.md`](./GETTING_STARTED.md) | first time here — setup through your first completed task |
| [`CLAUDE.md`](./CLAUDE.md) | agents and contributors working *in* this repo |
| [`Drunken-Guild-Guide.md`](./Drunken-Guild-Guide.md) | architecture, the Jira workflow, the Discord command reference, the approval flow |
| [`DESIGN.md`](./DESIGN.md) | why it is shaped this way — the decisions, and the failure behind each one |
| [`Integration-Guide.md`](./Integration-Guide.md) | connecting an external tool, or bringing another project under this workflow |
| [`examples/`](./examples/) | the flow and its filled-in setup documents, for a fictional app |
| [`SESSION_CHECKPOINT.md`](./SESSION_CHECKPOINT.md) | where the work currently stands |

---

## Known limitations

1. **Token cost and latency.** Running multiple agents consumes significant tokens. Handing a
   specialist a Jira issue key rather than a paraphrased brief keeps each delegation small, but a
   sequence of them still adds up. `drunken-usage` will tell you what a run actually cost.
2. **Coordination needs the MCP server.** `/breakdown`, `/build`, `/audit` and the `manager` role
   need `drunken-jira-mcp`; `ask-boss` needs a notification webhook for the case where the Boss is
   not reading the conversation. Without the server the three flow steps say so and stop rather
   than falling back to a file or a shell script. The other seven skills — `/prd`, `/clarify`,
   `/ddd`, `jira-tickets`, `project-docs`, `git-workflow` and `/isolate` — stand alone;
   `jira-tickets` is the ticket reference those Jira steps follow, and it reads as documentation
   with or without a server.
3. **No claim expiry.** A Jira assignee never expires. If an agent stops mid-ticket the ticket stays
   assigned until a human reassigns it. The retired local board released a claim after 1800s, and
   that is the one capability the move to Jira gave up.
4. **Process-heavy for small tasks.** The three roles are designed for complex features. Running
   manager, worker and reviewer for a CSS tweak is overkill.
5. **Retry loops.** Autonomous agents can enter retry cycles. `/isolate` carries an anti-loop
   mandate — stop after two identical failures — but monitor long runs and intervene.
6. **Not on PyPI.** Nothing has been released yet. Install from a checkout.

---

## Why this exists

I wanted to know where AI-assisted delivery actually holds and where it breaks, so I built a system
to find out rather than read about it.

The constraints came first, from 16 years of engineering: work items live in one place, agents never
merge, credentials are references and not tokens. Everything else was built around those.

The skills were drafted by me and reviewed with AI assistance — I used Claude to audit the
reasoning, tighten the constraints, and sharpen the output format of each `SKILL.md`.

Review and criticism are welcome.

---

## Contributing

Work lands on `develop` through a pull request; `main` accepts a PR from `develop` and nothing else.
The full rules are one file: [`skills/workflow/git-workflow/SKILL.md`](./skills/workflow/git-workflow/SKILL.md).

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).

Licensed under [MIT](./LICENSE). Security policy: [`SECURITY.md`](./SECURITY.md).
