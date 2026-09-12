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
6. [Using the three roles](#using-the-three-roles)
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

### 7 of the 11 skills need nothing else

`/prd`, `/clarify` and `/ddd` write markdown and ask you questions; `project-docs`, `git-workflow`
and `/isolate` are standards that read files and nothing else; `jira-tickets` is the reference for
the shape of a ticket, and it reads as documentation whether or not a server is there. All seven
install and work standalone. The general engineering standards — architecture, security, UI/UX,
testing and the rest — are in the optional `drunken-extras` plugin, and need nothing else either.

The other 4 coordinate work. `/breakdown`, `/build` and `/audit` call `jira_*` tools and name
`drunken-jira-mcp` in their own constraints — without the runtime declared they will **say so and
stop** rather than silently falling back to a file or a shell script. `ask-boss` needs
`drunken-discord-mcp` only for the case where the Boss is not reading the conversation; when they
are, it tells you to just ask them there.

If you have no Jira, you can still run `/prd`, `/clarify` and `/ddd` — skip the next section and
stop the flow at `DOMAIN.md`.

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

### Step 1 — Set up the project's rules

This is the one list of what to copy from `templates/`, and where. The **rules** go at the project
root; the **project's documents** are not copied from anywhere — the flow writes them, in Steps 2
to 4.

```bash
cp templates/CLAUDE.md              ~/Projects/my-project/CLAUDE.md
cp templates/SESSION_CHECKPOINT.md  ~/Projects/my-project/    # then add /SESSION_CHECKPOINT.md to .gitignore
```

Using Cursor or Aider as well? Add their files — both are thin and point at `CLAUDE.md`, so the rules
stay in one place:

```bash
cp templates/.cursorrules                          ~/Projects/my-project/   # Cursor
cp templates/CONVENTIONS.md templates/.aider.conf.yml ~/Projects/my-project/   # Aider
```

`CLAUDE.md` is the one that carries the **rules**: which Jira project this is, that Jira is the only
coordination surface, the `TODO → IN PROGRESS → IN REVIEW → DONE` ladder that must never skip
review, the MCP tools available, and your build and test commands.

Fill in every `<angle-bracket>` placeholder and delete what does not apply. Skills and agents read
this file every session — **a placeholder left in reads as an instruction.**

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
> [`templates/PROJECT_BRIEF.md`](./templates/PROJECT_BRIEF.md) and
> [`templates/REQUIREMENTS.md`](./templates/REQUIREMENTS.md) are still there if you would rather
> write something down before the interview in Step 2;
> [`examples/00-setup/`](./examples/00-setup/) has both filled in for a fictional task manager.

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
`REQ-xxx → Epic → Story → Task → Subtask` — one Epic per bounded context, Stories from the
requirements that context serves, Tasks sized to **a vertical slice finishable in a day**, Subtasks
only where steps are genuinely ordered. **Every level carries the label `req:REQ-xxx`.** That label
is the only thing `/audit` can trace on: not the summary text, not the parent chain, not the branch
name.

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

## Mid-sprint scenarios

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

Step 7 above is also the standing report. The **daily report** it writes is the one to read or
forward: what shipped today in plain language, which requirement each piece serves, what is still
open and what it waits on, and where to go and look at it. Progress is counted in **requirements
traced, not tickets closed** — tickets closed is a number that rises steadily while the thing you
asked for is still missing.

---

## Using the three roles

The workflow above runs skills in your own session. For larger work, start with the manager:

```bash
claude --agent manager
```

> "Read the project's documents and give me a plan: Epics, Stories and Tasks, in order, with what
> can run in parallel."

The manager proposes and you approve before anything starts; a `worker` then takes one task at a
time, and a `reviewer` checks the tests and the PR. The roles are described in the
[README](./README.md#three-roles).

---

## Where to go next

| | |
|---|---|
| [`skills/INDEX.md`](./skills/INDEX.md) | every skill, its trigger and its path |
| [`agents/INDEX.md`](./agents/INDEX.md) | every agent and when to invoke it |
| [`Drunken-Guild-Guide.md`](./Drunken-Guild-Guide.md) | the Discord command reference and approval flow |
| [`Integration-Guide.md`](./Integration-Guide.md) | bringing another project under this workflow |
| [`CLAUDE.md`](./CLAUDE.md) | the rules, if you are going to contribute here |

The commands, in one place:

| Command | When |
|---|---|
| `/prd` | starting a project, or requirements have changed |
| `/clarify` | the PRD reads cleanly but is not actually decided |
| `/ddd` | before any ticket is cut, to agree the contexts and the names |
| `/breakdown` | cutting the backlog — and filing a bug against the requirement it breaks |
| `/build` | executing one task: test first, one branch, one PR |
| `/audit` | after the day's merges, before anyone says a requirement is done |
| `/isolate` | a command has failed the same way twice |
| `/git-workflow` | branch naming, commit shape, which merge strategy belongs to which target |

The general engineering standards — `/system-design`, `/secure`, `/clean-arch`, `/ui`, `/ux` and
the rest — live in the optional `drunken-extras` plugin in
[`plugins/drunken-extras/`](./plugins/drunken-extras/).
