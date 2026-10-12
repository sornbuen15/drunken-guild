# Reference

Detail moved out of README.md and GETTING_STARTED.md so both could stay short (DG-517). Copied
verbatim from the versions of those two files at the commit this branch forked from
(`origin/develop`, `1459e3a`) — nothing here is paraphrased or re-derived.

## Contents

1. [Prerequisites](#prerequisites)
2. [Contributor and clone paths](#contributor-and-clone-paths)
3. [Guild block and AGENTS.md](#guild-block-and-agentsmd)
4. [AI layer location and git worktrees](#ai-layer-location-and-git-worktrees)
5. [Skills, agents and the three roles](#skills-agents-and-the-three-roles)
6. [The optional extras — 16 skills, 15 agents](#the-optional-extras--16-skills-15-agents)
7. [Steps 1-7, in detail](#steps-1-7-in-detail)
8. [Using the three roles](#using-the-three-roles)
9. [Skills not authored here](#skills-not-authored-here)
10. [Mid-sprint scenarios](#mid-sprint-scenarios)
11. [Known limitations](#known-limitations)
12. [Why this exists](#why-this-exists)
13. [Full documentation index](#full-documentation-index)
14. [Contributing](#contributing)

---

## Prerequisites

*(from the old GETTING_STARTED.md)*

**For the AI layer** — this is all of it:

- [Claude Code CLI](https://claude.ai/code), installed and authenticated
- Git
- macOS / Linux: Bash 3.2+ and `rsync` · Windows: PowerShell 5.1+ or [PowerShell 7+](https://github.com/PowerShell/PowerShell/releases)

**For the runtime**, additionally:

- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- A Jira account, and a Discord bot if you want approvals

---

## Contributor and clone paths

*(from the old README.md and GETTING_STARTED.md — the full detail behind README's short Install block)*

### Two halves, one repository

| | what it is | where |
|---|---|---|
| **The AI layer** | 11 skills and 3 team roles, installed into `~/.claude/` | `skills/`, `agents/` |
| **The runtime** | Python MCP servers and a CLI — Jira coordination, Discord approvals, cost accounting, health checks | `src/`, `scripts/` |

They are one repository on purpose. They used to be two, and the two drifted: skills were authored
in four places with 26 duplicated by name, and `git-workflow` silently diverged to 73 lines against
196 while a just-merged PR told one repo to defer to the other's copy. One surface is the answer.

**You can use either half alone.** Most skills need no MCP server. Only the coordination skills do,
and each one names the server it requires.

### Quick start — install from a release tag (no clone)

Needs [`uv`](https://docs.astral.sh/uv/) and Git. One install gives you the commands **and** the skills
and agents, which travel inside the package:

```bash
uv tool install git+https://github.com/sornbuen15/drunken-guild@v2.0.0   # pick the tag you want
drunken-install all                                                       # → ~/.claude/skills and ~/.claude/agents
```

Same on Windows PowerShell. `drunken-install` copies from the installed package, makes no model call,
rewrites only files whose bytes differ, and never writes through a link. Add `--dry-run` to see first.

To update, install the newer tag and say what changed *before* applying it:

```bash
uv tool install --force git+https://github.com/sornbuen15/drunken-guild@v2.1.0
drunken-install status      # what an update would change + the changelog entry; writes nothing
drunken-install all         # apply it
```

The update is installing the newer tag (a tag is a pin; this repository's text does not rely on
`uv tool upgrade` moving it). `drunken-install skills --prune` lists retired skills still installed; `--prune --prune-apply` removes only the ones named
in `scripts/install/retired_skills.txt`, never anything else. The agents are installed only if the
skills they need are there; if not, none is installed and the refusal says which. Then declare the
Jira server once per machine — see [GETTING_STARTED.md](../GETTING_STARTED.md).

The clone-and-run path below stays for contributors.

### Quick start — the AI layer, from a clone

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

### Quick start — the runtime

```bash
uv sync
```

Put credentials in a file **outside the repository**, readable only by you (Windows/PowerShell
form: [`Drunken-Guild-Guide.md`, section 2](../Drunken-Guild-Guide.md#2-registry-credentials-and-the-mcp-server)):

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

To take a project out of the registry (the file has no other way to delete one): `drunken-init --remove-project <id>`.
It copies the whole registry to `projects.json.bak-<UTC time>` beside it first, never replaces an earlier backup,
touches no project folder and no secret, and refuses an unknown id. There is no lock: do not run two
registry-changing commands at once.

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
environment installed, still shipping a server this package has since retired (`RETIRED.md`).
Uninstalling first is what actually removes it from your PATH.

```bash
drunken-doctor --project drunken-guild
```

Then declare the server **once per machine** at the user level of your agent — a project carries no
`.mcp.json` (REQ-019). For Claude Code:

```bash
claude mcp add --scope user drunken-jira-mcp -- "$(command -v drunken-jira-mcp)"
```

The steps, the Windows form and the check are in [GETTING_STARTED.md](../GETTING_STARTED.md).

> `uv tool install` ignores `uv.lock`, so the tool environment can drift inside the allowed
> dependency range. Pass `--with-requirements` if you need it pinned.

### Install the AI layer (the old GETTING_STARTED.md walkthrough)

The usual way — from a release tag, no clone (needs `uv` and Git):

```bash
uv tool install git+https://github.com/sornbuen15/drunken-guild@v2.0.0   # pick the tag you want
drunken-install all                                                       # → ~/.claude/skills and ~/.claude/agents
drunken-install status                                                    # later: what an update would change
```

The skills and agents travel inside the package. `drunken-install all --dry-run` shows what it would
write first. To update, install the newer tag with `uv tool install --force git+…@<tag>`, run
`drunken-install status`, then `drunken-install all`. The rest of this section is the **contributor**
path, from a clone:

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

### Add the runtime (optional)

This gives you the `jira_*` and approval tools.

```bash
uv sync --extra dev
```

The `--extra dev` is not optional if you intend to run the tests. Without pytest in `.venv`,
`uv run pytest` falls through to whatever `pytest` is on PATH — which may import a different
checkout entirely and pass. The suite refuses to start in that state and tells you so.

Put your credentials in a file **outside any repository**, readable only by you (Windows/PowerShell
form: [`Drunken-Guild-Guide.md`, section 2](../Drunken-Guild-Guide.md#2-registry-credentials-and-the-mcp-server)):

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
old environment installed, still shipping a server this package has since retired (`RETIRED.md`).

Then **declare the server once for the whole machine**. Do not put a `.mcp.json` in your project:
the server is the same for every project (each tool takes the registry project id as its first
argument, so no configuration decides which Jira is reached — DG-341), and a file in the project
would be the guild showing up in a repository that may be handed to a customer (REQ-019).

**Claude Code** — one command, any folder, run it yourself:

```bash
claude mcp add --scope user drunken-jira-mcp -- "$(command -v drunken-jira-mcp)"
claude mcp list        # drunken-jira-mcp ... ✔ Connected
```

On Windows PowerShell the second argument is the full path `uv tool` printed
(`C:\Users\<you>\.local\bin\drunken-jira-mcp.exe`): `claude mcp add --scope user drunken-jira-mcp -- <that path>`.
Name the **installed** command, never one inside a project's `.venv`: it works until the venv is
rebuilt, then fails with no visible link to the cause.

**Other agents** (Antigravity, Aider, Gemini CLI) are 2.1; until then use that agent's own
user-level MCP config. `./scripts/install/install_mcp.sh` prints the JSON to paste (it writes
nothing unless you pass `--out`), and `scripts/onboard_project.py --merge-mcp-config <file>` merges
it into a file that already declares other servers, by name, so those survive.

**Already have a `.mcp.json` in a project?** Delete it from that project once the user-level entry
shows *Connected*; if the project committed it, remove it with `git rm`. Leaving both works but
loads the server twice.

**Check:** open the project in a new Claude Code session and ask for the board
(`jira_board_info`). If the tool is missing, `claude mcp list` says which scope holds the entry.

---

## Guild block and AGENTS.md

*(from the old README.md, "Giving an existing AGENTS.md the guild block")*

`--path` on a project with no `AGENTS.md` writes one that already opens with the guild block — the
pointer table routing an agent to `/build`, `/git-workflow`, `/jira-tickets` and the rest. A project
that already has its own `AGENTS.md` keeps it byte for byte and gets nothing added, by design — see
"Quick start" above.

Add `--guild-block` to merge the block into that existing file instead:

```bash
uv run drunken-init --project drunken-guild --path "$PWD" --guild-block
```

No block yet: it is inserted right after the file's first heading — a leading UTF-8 BOM, if there is
one, stays at byte 0 and the heading is still found after it. An older block from a previous run:
only the text between its `<!-- guild-block:start -->` / `<!-- guild-block:end -->` markers is
replaced — everything else in the file is untouched, so running it again changes nothing. Nothing
secret and no project id is ever written to the block itself. A first-time `AGENTS.md` (no prior
file) is reported as `created with the block`, not `unchanged`.

It refuses rather than guessing, leaving the file untouched and exiting non-zero:

- **`AGENTS.md` itself is a symlink.** Merging through it could write into a file outside the
  project that the leaf name gives no hint of. This check is on the leaf only — it does not cover
  `--path` itself being a junction or sitting under a symlinked parent directory, since that is the
  operator's own choice of path, not something the merge can second-guess.
- **A hard link is not detected at all.** A hard link to a file outside the project looks exactly
  like an ordinary file — there is no "it's a link" bit to check — so the block is written through
  to the other name just as it would be for a normal file. Do not point `--path` at a project whose
  `AGENTS.md` is a hard link you do not own.
- **The markers are malformed** — a `start` with no matching `end`, an `end` that appears before its
  `start`, or more than one of either. Only zero markers (insert) or exactly one well-formed pair
  (replace) is something the merge can act on without guessing; the error names the problem and the
  line.

Not running the CLI here? Copy the block between those same markers out of
[`src/core/templates/AGENTS.md`](../src/core/templates/AGENTS.md) and paste it into the target
`AGENTS.md` by hand, replacing an older copy between the same markers if one is already there.

---

## AI layer location and git worktrees

*(from the old README.md, "Where a project's AI layer comes from")*

A project that uses the guild must not carry the guild: its own git tracks none of `AGENTS.md`,
`CLAUDE.md`, `.claude/` or the Jira configuration (REQ-019), and `drunken-doctor` fails when it does.
Those files live in **one private config repo you own**, one folder per project named with the
project's registered id (layout: [CONFIG_REPO.md](../CONFIG_REPO.md)). Clone it, then copy a
project's folder in; the copied files are hidden from the project's git through
`.git/info/exclude`:

```bash
git clone <your-private-config-repo> ~/config-repo        # once, by you
uv run drunken-init --project alpha --config-repo ~/config-repo
```

Re-running is safe: an untracked file that differs is skipped and named unless you pass
`--overwrite-ai-layer`, and a file the project's own git already tracks is always refused. Claude
Code reads the hidden `CLAUDE.md` and `.claude/settings.json` exactly like tracked ones (DG-432).

**A project that already committed its AI layer** (the doctor's `layering.tracked` fails and
`drunken-init` refuses) is moved out with one command. It shows the plan first; `--apply` performs
it: the files are backed up outside the repository (owner-only on POSIX), the layer is excluded,
then untracked with the deletion **staged — you commit it**. The files stay on disk. History is not
rewritten, so anything secret that was ever committed must still be rotated, and until you commit,
`git reset`, `git stash` or `git checkout` can put the files back under git.

```bash
uv run drunken-init --project alpha --migrate-ai-layer            # plan only
uv run drunken-init --project alpha --migrate-ai-layer --apply    # back up, exclude, untrack
```

Two things never go in the config repo: a **credential** (it lives in no git repository; the
registry holds a reference such as `file://~/.drunken/secrets.json#jira.alpha`) and an
**`.mcp.json`** (a project carries none; declare the server once per machine). This repository is
the exception: here the AI layer is the product and stays tracked.

*(from the old GETTING_STARTED.md, "Make sure it gets used" — the fact itself, kept here even
though that section's own fix (the routing hooks) is superseded; see the exception noted in this
ticket's PR body)*

Installing the skills is not the same as a session *calling* them. A session can start in a fresh
`git worktree` with no `AGENTS.md`, with no `SessionStart` hook configured anywhere, and the model
can simply do the work itself and never reach for a skill or an agent — nothing forced it to look.

---

## Skills, agents and the three roles

*(from the old README.md, "How the AI layer is organised")*

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
[`plugins/drunken-extras/`](../plugins/drunken-extras/).

### The flow — seven commands

```
/prd        →  PRD.md: the brief and the requirements in one file, every requirement
               carrying an id REQ-xxx and a MoSCoW class
/clarify    →  a short ranked list of decisions only the Boss can make, answered back
               into PRD.md
/ddd        →  DOMAIN.md: bounded contexts, shared vocabulary, core entities.
               Each context becomes an Epic
/breakdown  →  the Jira hierarchy — REQ → Epic → Story | Task → Subtask, Story and Task
               both siblings under the Epic — every level labelled req:REQ-xxx. Nothing
               is created until the Boss approves the plan
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
`drunken-extras` plugin in [`plugins/drunken-extras/`](../plugins/drunken-extras/).

Full catalogue with triggers: [`skills/INDEX.md`](../skills/INDEX.md).

---

## The optional extras — 16 skills, 15 agents

*(from the old GETTING_STARTED.md, "Older skills and agents")*

### 7 of the 12 skills need nothing else

`/prd`, `/clarify` and `/ddd` write markdown and ask you questions; `project-docs`, `git-workflow`
and `/isolate` are standards that read files and nothing else; `jira-tickets` is the reference for
the shape of a ticket, and it reads as documentation whether or not a server is there. All seven
install and work standalone. The general engineering standards — architecture, security, UI/UX,
testing and the rest — are in the optional `drunken-extras` plugin, and need nothing else either.

The other 5 coordinate work. `/breakdown`, `/replan`, `/build` and `/audit` call `jira_*` tools and name
`drunken-jira-mcp` in their own constraints — without the runtime declared they will **say so and
stop** rather than silently falling back to a file or a shell script. `ask-boss` needs
a notification webhook only for the case where the Boss is not reading the conversation; when they
are, it tells you to just ask them there.

If you have no Jira, you can still run `/prd`, `/clarify` and `/ddd` — skip the next section and
stop the flow at `DOMAIN.md`.

### Older skills and agents

Sixteen general engineering skills and fifteen domain-specialist agents from before the 2.0.0
re-scope live in `plugins/drunken-extras/` but were never wired into any installer (DG-512) — they
reach no machine until you ask for them:

```bash
drunken-install extras            # plan — what would install, by name
drunken-install extras --apply    # write them into ~/.claude/skills and ~/.claude/agents
drunken-install extras --only acronym-namer,laravel-developer --apply   # just these
```

It never removes anything, and a file you already have that differs from the packaged one is
reported, not overwritten. `drunken-install status` lists them too, separately from the core
skills and agents, since they stay optional.

**The 16 skills:**

| skill | one line |
|---|---|
| `acronym-namer` | Generates thematic backronyms for naming a project, bot or module. |
| `business-telemetry` | Structured event tracking and full-funnel analytics standard. |
| `clean-architecture` | Clean Architecture / DDD — layer separation, dependency rules, domain models. |
| `cloud-native` | Cloud-native infra standard — Docker, Kubernetes, CI/CD, IaC. |
| `electron-ipc-protocol` | The IPC contract for Electron apps — context isolation, preload bridge, channel naming. |
| `incident-response` | Crisis leadership for outage mitigation, comms, and blameless RCA. |
| `product-midset` | Product thinking, FinOps, and data-driven feature decisions. |
| `release-notes-writer` | Standardized, markdown-table release notes and tag descriptions. |
| `secure-by-design` | Zero Trust security, network to application layer. |
| `servant-leadership` | Empathetic communication, code review feedback, blameless culture. |
| `standard-playbook-generator` | Generates anonymized engineering playbooks from the skill files themselves. |
| `system-design-rules` | System design standard — trade-offs, API contracts, diagrams before code. |
| `test-architecture` | Architectural test strategy — BDD, ATDD, contract, mutation, property-based. |
| `test-strategy` | Reference for choosing the right test type across four test levels. |
| `universal-ui` | Visual standard against "developer UI" anti-patterns. |
| `universal-ux` | Frontend architecture — state/view separation, resilience, full UX lifecycle. |

**The 15 agents:**

| agent | one line |
|---|---|
| `agentic-systems-specialist` | Agentic AI design, tool-calling architecture, autonomous action boundaries. |
| `ai-memory-specialist` | Long-term memory architecture, RAG pipelines, vector DB selection. |
| `cross-platform-mobile` | Flutter/React Native/Kotlin Multiplatform, shared vs. platform-specific code. |
| `desktop-frontend-dev` | Electron desktop apps — main/renderer split, secure IPC, native menus. |
| `devops-engineer` | Infra, CI/CD, containers, Terraform/Helm/GitHub Actions, observability. |
| `fintech-specialist` | Payments, banking, KYC/AML, PCI-DSS/PSD2/ISO 20022 domain accuracy. |
| `fullstack-engineer` | General frontend/backend implementation, APIs, database design. |
| `insurance-specialist` | Policy, claims, underwriting; NAIC/HIPAA/ACORD domain accuracy. |
| `laravel-developer` | PHP 8.2+/Laravel 11 — repositories, type safety, FilamentPHP v3. |
| `native-android` | Kotlin, Jetpack Compose, Gradle, Play Store delivery. |
| `native-ios` | Swift, SwiftUI, UIKit, Xcode, App Store delivery. |
| `principal-engineer` | Direction, not execution — roadmap, trade-offs, priority, risk. |
| `qa-engineer` | Test strategy, unit/integration/E2E tests, pre-merge quality gates. |
| `security-engineer` | Security review, threat modeling, auth/authz design, dependency risk. |
| `voice-ai-specialist` | Voice pipelines, TTS/STT selection, real-time audio, latency budgets. |

**What is *not* restored, and why** (full detail in `RETIRED.md`): the local-board kanban skills
(`agentic-kanban`, `kanban-io`, `next-task`, `squad-workflow`) are not — a board beside Jira is a
second surface that can disagree with the first (DG-265), and that reason applies regardless of
which installer ships the file. The four vendored, unlicensed skills (`debug-mantra`,
`post-mortem`, `scrutinize`, `management-talk`) are not — they carry no licence and no reachable
upstream, so this repository cannot redistribute them under its own MIT licence (DG-263). Recover
either set from git with the commit named in `RETIRED.md`'s table, e.g.
`git show abe5df1:skills/<name>/SKILL.md` or `git show d41d99d:skills/workflow/<name>/SKILL.md`.

---

## Steps 1-7, in detail

*(from the old GETTING_STARTED.md, "Step-by-step: your first ticket")*

### Step 1 — Set up the project's rules

> **Where these files come from.** If the project is one you will hand to someone else, or keep
> private, its `AGENTS.md`, `CLAUDE.md` and `.claude/` do not belong in its git. Keep them in your
> private config repo and copy them in with `drunken-init --config-repo <path>` — README, "Where a
> project's AI layer comes from". The steps below still apply; only where the files live changes.

`drunken-init`, run above, already wrote `~/Projects/my-project/AGENTS.md` and a one-line
`CLAUDE.md` that imports it (REQ-015) — do not overwrite either by hand. What is left to copy from
`templates/` is the session scratchpad and, if you use them, the Cursor/Aider pointer files:

```bash
cp templates/SESSION_CHECKPOINT.md  ~/Projects/my-project/    # then add /SESSION_CHECKPOINT.md to .gitignore
```

Using Cursor or Aider as well? Add their files — both are thin and point at `AGENTS.md`, so the rules
stay in one place:

```bash
cp templates/.cursorrules                          ~/Projects/my-project/   # Cursor
cp templates/CONVENTIONS.md templates/.aider.conf.yml ~/Projects/my-project/   # Aider
```

`AGENTS.md` is the one that carries the **rules**: which Jira project this is, that Jira is the only
coordination surface, the `TODO → IN PROGRESS → IN REVIEW → DONE` ladder that must never skip
review, the MCP tools available, and your build and test commands.

Fill in its `## Commands` section and anything else it leaves open for this project. Skills and
agents read this file every session — **a placeholder left in reads as an instruction.**

**The project's documents** are located the same way by every skill that reads them — the
`project-docs` skill is the contract, and every flow step prints its block before doing anything
else. The map is a `## Documents` section in the project's root `AGENTS.md`. When there is no map,
these are the defaults:

- `.ai/PRD.md` — the brief and the numbered requirements, written by `/prd` in Step 2
- `.ai/DOMAIN.md` — contexts, vocabulary and entities, written by `/ddd` in Step 4
- `.ai/audit/` — one report per `/audit` run
- `docs/` and `docs/decisions/` — what people read, and the ADRs

There is nothing to write yet. A skill never invents a missing document and treats it as decided;
it says it was absent.

> **Why `.ai/`.** It is one place every agent reads, whichever vendor it comes from, and it keeps
> facts about the project out of the files that describe an agent. A project that keeps its
> documents somewhere else works too — record the paths in `AGENTS.md` and the skills follow. What
> does not work is the same document in two places: that is two surfaces, and skills stop and ask
> which one is real.

> **Already have a brief?** An older project's `PROJECT_BRIEF.md`, `REQUIREMENTS.md` and
> `PROJECT_SPEC.md` stay where they are. `/prd` offers to consolidate them into one `PRD.md`, names
> the source beside each section it carries over, says what the sources disagreed about rather than
> picking a winner, and does none of it without a yes.
> [`templates/PROJECT_BRIEF.md`](../templates/PROJECT_BRIEF.md) and
> [`templates/REQUIREMENTS.md`](../templates/REQUIREMENTS.md) are still there if you would rather
> write something down before the interview in Step 2;
> [`examples/00-setup/`](../examples/00-setup/) has both filled in for a fictional task manager.

### Step 2 — Write the PRD

Open Claude Code inside **your project directory**:

```
/prd
```

It prints which project documents it found and where, then routes: an existing `PRD.md` is
**updated, never rewritten**; an older split set is offered for consolidation; nothing at all means
an interview — what is being built, who for, the stack, the constraints, what is explicitly out of
scope, all in **one batch of questions** rather than one at a time.

The output is one file: a brief, then numbered requirements. Every requirement carries an id
`REQ-001`, `REQ-002`, … and a **MoSCoW class** — Must, Should, Could, Won't — plus one acceptance
sentence saying how anyone can tell it works.

Three rules are worth knowing before you read the draft:

- **Ids are allocated once and never reused.** A dropped requirement is struck through and keeps
  its id. Jira labels, branches and merged tickets already point at those numbers; renumbering
  silently repoints history at the wrong requirement.
- **Anything the AI inferred lands under `## Inferred — not yet accepted`**, with no id, until you
  accept it. A generated requirement in the numbered list reads to `/breakdown` as a decision
  nobody made.
- **Nothing is written until you say yes.** You see the whole draft, or the diff against an
  existing PRD, first.

This step writes no Jira ticket. It ends by listing what is still ambiguous.

### Step 3 — Answer the questions only you can answer

```
/clarify
```

It reads the PRD as someone who has to build from it tomorrow and cannot, and puts **about ten
ranked questions** to you — the one that decides an architecture first, the one that decides a
label last. Each names its `REQ-xxx`, states the ambiguity, and gives two or three concrete options
with what each costs. If more than ten qualify it asks the ten and says how many it held back.

It does **not** answer them itself, and it does not proceed on your behalf. Your answers are written
back into `PRD.md` — into the acceptance sentence, or as a dated `**Decided:**` line — after you
confirm the diff. An answer that lives only in the transcript is lost by the next session, and the
requirement still reads ambiguous to `/ddd`.

Every item left open is labelled either **`BLOCKS /ddd`** or **`Carry`**, with the reason on the
same line. Some ambiguity is fine to carry, and saying which is the point of this step.

### Step 4 — Agree the vocabulary

```
/ddd
```

Produces `DOMAIN.md` from the clarified PRD: **bounded contexts** (each one lists the requirements
it serves by id), the **shared vocabulary** — one term, one definition, one spelling — and the
**core entities** with the rules that must always hold about them. Three sections, not a fourth. No
tables, no endpoints, no framework names: those are decisions made per task in Step 6.

It is a **proposal until you accept it.** The Boss owns the language of their own domain, and an
agent that names it for them has renamed their business. Correct the names and it applies your
corrections; if a corrected name collides with another term it asks rather than resolving it
quietly.

Two findings get reported rather than quietly fixed, because each means something different:

- a context that serves **no requirement** is wrong — it would become an Epic with no work under it;
- a requirement that belongs to **no context** is a gap — either the model is missing a context or
  the PRD is missing a requirement.

Each context becomes exactly one Epic in the next step.

### Step 5 — Cut the backlog

```
/breakdown
```

This is where traceability is created or lost for good. It maps
`REQ-xxx → Epic → Story | Task → Subtask` — one Epic per bounded context, Stories and Tasks both
parented directly to that Epic (this team-managed Jira refuses a Task parented to a Story), Tasks
sized to **a vertical slice finishable in a day** and naming their Story, if any, in the
description, Subtasks only where steps are genuinely ordered. **Every level carries the label
`req:REQ-xxx`.** That label is the only thing `/audit` can trace on: not the summary text, not the
parent chain, not the branch name.

It probes `jira_board_info` first — issue types, settable field ids, **and whether this board has a
backlog at all** — then prints the whole hierarchy as a table and **halts**. Nothing is created
until you say yes.

> **Confirm your Jira project key is real before this step writes anything.** A green
> `drunken-doctor` line proves the credential authenticates, not that the project exists — it has
> printed `OK … (project ALPHA)` while Jira answered *"No project could be found"*. And a bad
> credential comes back as `200` with an empty list, which reads exactly like a project with no
> issues in it.

Urgency lands as a **label** — `critical`, `high`, `medium`, `low`, lower case — mapped from the
requirement's MoSCoW class: Must → `critical` or `high`, Should → `medium`, Could → `low`. **A
Won't gets no ticket at all.** Jira's `priority` field cannot be set on a team-managed project and
reads `Medium` on every issue, and there are no story points, so neither is used.

Everything it creates lands **in the backlog, in `TODO`, unassigned**. It never transitions or
starts anything — moving work onto the board and starting it are separate acts, with separate
owners. It ends with two questions: create these tickets, and execute in sequence or in parallel?
Tasks that touch the same files must run in sequence; that call is yours, not the agent's.

### Step 6 — Build one task

```
/build
```

The only flow step that writes code, and it does exactly one task. `jira_start_task` moves the
ticket to `IN PROGRESS` and hands back the branch command; the agent puts `agent:<its name>` in
`labels`, because the assignee is the accountable human, not the thing doing the typing.

Then, in order: read the ticket's SCOPE and ACCEPTANCE · check the plan still holds against the
code as it is now, and **comment on the ticket if it diverges** rather than deviating silently ·
**write the test, run it, and watch it fail** · implement the smallest change that turns it green ·
run the whole suite · open the PR.

**The failing run is the evidence, so it gets reported.** Not "tests added" — the test id and what
the assertion actually said: `AssertionError: expected 401, got 200`. A test written after the fix
proves only that it compiles.

**1 task = 1 owner = 1 branch = 1 worktree = 1 PR.** Two agents never share a checked-out working
tree, and tasks touching the same files run one after another.

The agent calls `jira_submit_for_review` — the ticket goes to `IN REVIEW`, never straight to
`DONE`. **Never skip `IN REVIEW`, including for your own work.** Then it stops: **an agent opens
the PR and a human merges it**, with no exception for a one-line change, a green CI, or an approval
that arrived in chat.

A ticket in `IN REVIEW` is not merged code. Run the suite and read the diff against the target
branch before believing any claim that it is fixed.

> Nothing expires a Jira assignee. If an agent stops mid-ticket, reassign it yourself — that is the
> one thing the retired board did that Jira does not.

### Step 7 — Audit what actually shipped

After the day's tasks merge:

```
/audit
```

It traces **every** `REQ-xxx` in the PRD through to its tickets, their status, the test that covers
it, and whether that test passed **on the merged tree** — fetched and run from a clean worktree of
`origin/develop`, not from the branch you happen to be standing on and not from the PR page.

Every gap has a name, because they have different causes and different fixes: `no-ticket` (nobody
was ever asked to build it) · `no-test` (built, unproven) · `unverified` (green on a branch, never
run on the merged tree) · `not-merged` (`DONE`, but the branch is not in `origin/develop`) ·
`not-deployed` (merged, and the thing a person can look at is still older than the merge).

One run writes two dated files under the audit directory, and never overwrites yesterday's: the
**audit report**, which is the engineering half, and the **daily report**, which is plain language
and can be handed to a customer unedited. Gaps are proposed as tickets in one table and created
through `/breakdown` only on your approval, off the board.

It diagnoses and records — it never edits source and never fixes a failing test. An auditor who
patches what he is grading has no finding left to report.

> **Merged is not deployed.** A merge does not update an installed tool or restart a running
> process. Where a project deploys is recorded in its own `AGENTS.md`; if it is not recorded there,
> the audit reports the target as unknown and asks. Deploying is your step, never the agent's.

---

## Using the three roles

*(from the old GETTING_STARTED.md)*

The workflow above runs skills in your own session. For larger work, start with the manager:

```bash
claude --agent manager
```

> "Read the project's documents and give me a plan: Epics, Stories and Tasks, in order, with what
> can run in parallel."

The manager proposes and you approve before anything starts; a `worker` then takes one task at a
time, and a `reviewer` checks the tests and the PR. The roles are described in
["Skills, agents and the three roles"](#skills-agents-and-the-three-roles) above.

---

## Skills not authored here

*(from the old GETTING_STARTED.md)*

`skills/.external` lists skills that are installed but deliberately not authored in this repo. An
empty file is a claim that there are none — not a default. Do not overwrite anything listed there.

---

## Mid-sprint scenarios

*(from the old GETTING_STARTED.md)*

### A bug arrives while a ticket is in flight

Do **not** interrupt the current ticket.

```
/breakdown
```

A bug comes through the same skill that cut the backlog, and it is a small job there: **one Bug
ticket against the `REQ-xxx` it breaks**, carrying that `req:` label and an urgency label. It does
not re-read the whole PRD, does not re-cut the hierarchy, and does not touch the work in flight.
You decide whether it jumps the queue — pick it up when the current ticket reaches `IN REVIEW`, or
sooner if it outranks what you are holding.

The same applies to a defect noticed *by* `/build` while it is working: its own ticket, and the
task in flight continues. Widening scope mid-branch is how one task stops being finishable in a day.

### End-of-day snapshot

```
/audit
```

The **daily report** it writes is the one to read or forward: what shipped today in plain
language, which requirement each piece serves, what is still open and what it waits on, and where
to go and look at it. Progress is counted in **requirements traced, not tickets closed** — tickets
closed is a number that rises steadily while the thing you asked for is still missing.

---

## Known limitations

*(from the old README.md)*

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

*(from the old README.md)*

I wanted to know where AI-assisted delivery actually holds and where it breaks, so I built a system
to find out rather than read about it.

The constraints came first, from 16 years of engineering: work items live in one place, agents never
merge, credentials are references and not tokens. Everything else was built around those.

The skills were drafted by me and reviewed with AI assistance — I used Claude to audit the
reasoning, tighten the constraints, and sharpen the output format of each `SKILL.md`.

Review and criticism are welcome.

---

## Full documentation index

*(from the old README.md, "Documentation" — README's own "Where to go next" table carries the
same links that still apply; the rows below are the ones nowhere else today)*

| | for whom |
|---|---|
| [`GETTING_STARTED.md`](../GETTING_STARTED.md) | first time here — setup through your first completed task |
| [`AGENTS.md`](../AGENTS.md) | agents and contributors working *in* this repo (`CLAUDE.md` is its one-line adapter) |
| [`Drunken-Guild-Guide.md`](../Drunken-Guild-Guide.md) | architecture, the Jira workflow, the Discord command reference, the approval flow |
| [`DESIGN.md`](../DESIGN.md) | why it is shaped this way — the decisions, and the failure behind each one |
| [`CONFIG_REPO.md`](../CONFIG_REPO.md) | the one private repo a project's AI layer comes from — its layout, what a project's folder may hold, and what must never be in it (REQ-019, REQ-020) |
| [`Integration-Guide.md`](../Integration-Guide.md) | connecting an external tool, or bringing another project under this workflow |
| [`examples/`](../examples/) | the flow and its filled-in setup documents, for a fictional app |
| [`SESSION_CHECKPOINT.md`](../SESSION_CHECKPOINT.md) | where the work currently stands |

---

## Contributing

*(from the old README.md)*

Work lands on `develop` through a pull request; `main` accepts a PR from `develop` and nothing else.
The full rules are one file: [`skills/workflow/git-workflow/SKILL.md`](../skills/workflow/git-workflow/SKILL.md).

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md).
