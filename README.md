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
| **The AI layer** | 38 skills and 15 agents, installed into `~/.claude/` and read by Antigravity | `skills/`, `agents/` |
| **The runtime** | Python MCP servers and a CLI — Jira coordination, Discord approvals, cost accounting, health checks | `src/`, `scripts/` |

They are one repository on purpose. They used to be two, and the two drifted: skills were authored
in four places with 26 duplicated by name, and `git-workflow` silently diverged to 73 lines against
196 while a just-merged PR told one repo to defer to the other's copy. One surface is the answer.

**You can use either half alone.** Most skills need no MCP server. Only the coordination skills do,
and each one names the server it requires.

> **Antigravity as an active peer is currently supported, not recommended.** The skills, agents and
> rules below install for it the same as for Claude Code, and nothing here stops it running — but
> track record on this repo has been repeated violations of rules written specifically for it, plus
> a permission-prompt noise problem in its own harness this repo has no way to reach or fix. Treat
> it as a consumer of the AI layer for now, not an unattended second author. Current status and the
> reasoning live in this repo's own `SESSION_CHECKPOINT.md`.

---

## Quick start — the AI layer

No Python, no credentials, no server. Clone and install:

```bash
git clone https://github.com/sornbuen15/drunken-guild.git
cd drunken-guild
./scripts/install/install_skills.sh    # → ~/.claude/skills/
./scripts/install/install_agents.sh    # → ~/.claude/agents/
```

Both also install into Antigravity's tree when it is present, and neither creates it when it is
not. Add `--index-only` to rebuild `INDEX.md` without installing anything.

> The PowerShell pair installs to `~/.claude/` only — no Antigravity tree, no `--index-only`. The
> gap is stated in each script's header: there is no Windows machine here to test against, and an
> untested installer writing into a shared config directory is worse than one that does less.

Windows (PowerShell):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # one-time, if blocked
.\scripts\install\install_skills.ps1
.\scripts\install\install_agents.ps1
```

Then invoke a skill by its trigger — `/tdd`, `/secure`, `/scrutinize`, `/post-mortem` — or hand work
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
> printed `OK … (project TWA)` while Jira answered *"No project could be found"*. Verify the key
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
    "drunken-jira-mcp": { "command": "drunken-jira-mcp", "args": ["--project", "your-project"] }
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

### The three-tier system

```
┌─────────────────────────────────────────────────────────┐
│  TIER 1 — Domain Specialists                            │
│  WHAT to build · domain rules · regulations · data      │
│  fintech-specialist · insurance-specialist              │
└──────────────────────────┬──────────────────────────────┘
                           │ Domain Brief
                           ▼
┌─────────────────────────────────────────────────────────┐
│  TIER 2 — Principal Engineer                            │
│  HOW to structure the team · technical direction        │
│  platform strategy · ADRs · squad assembly              │
└──────────────────────────┬──────────────────────────────┘
                           │ Delegation
                           ▼
┌─────────────────────────────────────────────────────────┐
│  TIER 3 — Engineering Squad                             │
│  EXECUTION · code · infra · tests · security · mobile   │
│  fullstack · devops · qa · security · ios · android     │
│  cross-platform · laravel · desktop                     │
└─────────────────────────────────────────────────────────┘
```

**Tier 1** is optional — skip it for general engineering work, required in a regulated space.
**Tier 2** is always the orchestrator. **Tier 3** executes, loading the relevant skills first.

### Skill categories

`architecture` · `backend` · `frontend` · `infrastructure` · `security` · `testing` · `product` ·
`kanban` · `leadership` · `documents` · `workflow`

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
| [`examples/`](./examples/) | the full project lifecycle walked through with a fictional app |
| [`SESSION_CHECKPOINT.md`](./SESSION_CHECKPOINT.md) | where the work currently stands |

---

## Known limitations

1. **Token cost and latency.** Running multiple agents consumes significant tokens. Handing a
   specialist a Jira issue key rather than a paraphrased brief keeps each delegation small, but a
   sequence of them still adds up. `drunken-usage` will tell you what a run actually cost.
2. **Coordination needs the MCP server.** Eight skills and `principal-engineer` need
   `drunken-jira-mcp` and the ticket-rules file. Without them those skills degrade to the rules they
   carry inline — and they will not announce that they are working from a summary. The other 28
   skills stand alone.
3. **No claim expiry.** A Jira assignee never expires. If an agent stops mid-ticket the ticket stays
   assigned until a human reassigns it. The retired local board released a claim after 1800s, and
   that is the one capability the move to Jira gave up.
4. **Process-heavy for small tasks.** The three-tier architecture is designed for complex features.
   Using the full squad for a CSS tweak is overkill.
5. **Retry loops.** Autonomous agents can enter retry cycles. `/isolate` carries an anti-loop
   mandate — stop after two identical failures — but monitor long runs and intervene.
6. **Not on PyPI.** Nothing has been released yet. Install from a checkout.

---

## Why this exists

I'm a computer engineer, but I don't feel confident I'm good enough — and I don't have much time to
develop my skills the way I'd like to.

I built this to learn the fundamentals properly and try building an agent system from my own
perspective. It's part study, part experiment.

The skills were drafted by me, then **reviewed and improved with AI assistance** — I used Claude to
audit the reasoning, tighten the constraints, and sharpen the output format of each `SKILL.md`.

I'm sharing this because I wanted a review. I'm not sure I'm still where I need to be as a software
engineer, and this project is my honest attempt to find out.

---

## Contributing

Work lands on `develop` through a pull request; `main` accepts a PR from `develop` and nothing else.
The full rules are one file: [`skills/workflow/git-workflow/SKILL.md`](./skills/workflow/git-workflow/SKILL.md).

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).

Licensed under [MIT](./LICENSE). Security policy: [`SECURITY.md`](./SECURITY.md).
