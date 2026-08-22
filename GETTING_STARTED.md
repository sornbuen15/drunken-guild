# Getting Started with Drunken AI Team
*Brought to you by Drunken Programmer*

A complete walkthrough — from installation through your first completed task. Each step links to a matching example in [`examples/`](./examples/) so you can see expected output before you run anything.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [macOS / Linux](#macos--linux)
  - [Windows](#windows)
  - [Manual Installation (no scripts)](#manual-installation-no-scripts)
- [Step-by-Step Guide](#step-by-step-guide)
  - [Step 1 — Describe Your Project](#step-1--describe-your-project)
  - [Step 2 — Generate Your Backlog](#step-2--generate-your-backlog)
  - [Step 3 — Load the Sprint Queue](#step-3--load-the-sprint-queue)
  - [Step 4 — Size the Work](#step-4--size-the-work)
  - [Step 5 — Start the First Task](#step-5--start-the-first-task)
  - [Step 6 — Review and Close the Task](#step-6--review-and-close-the-task)
- [Mid-Sprint Scenarios](#mid-sprint-scenarios)
  - [Handling a Bug Mid-Sprint](#handling-a-bug-mid-sprint)
  - [End-of-Sprint Snapshot](#end-of-sprint-snapshot)
- [Using the Multi-Agent Squad](#using-the-multi-agent-squad)
- [Full Skill Reference](#full-skill-reference)

---

## Prerequisites

- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- Git
- **[Node.js](https://nodejs.org/) v18 or v24** *(required for the kanban MCP server and CLI fallback scripts — `kanban-server.js`, `kanban_read.sh`, `kanban_write.sh` and their Windows equivalents)*
- **macOS / Linux:** Bash 3.2+, `rsync`
- **Windows:** PowerShell 5.1+ or [PowerShell Core 7+](https://github.com/PowerShell/PowerShell/releases)

---

## Installation

### macOS / Linux

```bash
# 1. Clone the repo
git clone <repo-url> drunken-ai-team
cd drunken-ai-team

# 2. Deploy skills to ~/.claude/skills/
bash scripts/install/sync_skills.sh

# 3. Deploy agents to ~/.claude/agents/
bash scripts/install/sync_agents.sh
```

Both scripts are safe to re-run — they only update files that have changed.

### Windows

Open PowerShell (5.1+ or Core 7+):

```powershell
# 1. Clone the repo
git clone <repo-url> drunken-ai-team
cd drunken-ai-team

# 2. Allow script execution (one-time, current user only)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3. Deploy skills to %USERPROFILE%\.claude\skills\
.\scripts\install\sync_skills.ps1

# 4. Deploy agents to %USERPROFILE%\.claude\agents\
.\scripts\install\sync_agents.ps1
```

Both scripts are safe to re-run after any update.

> **Note:** The `scripts\kanban\` and `scripts\mcp\` directories are separate — they implement board I/O for your *target project*, not this toolkit. Register the MCP server in your project's `.claude/settings.json` using `templates/mcp-settings.json`. See `scripts/mcp/README.md` for full setup instructions.

---

### Manual Installation (no scripts)

Use this path if you cannot run shell or PowerShell scripts (e.g., restricted environments, corporate policies, or you just prefer to do it by hand).

**1. Create the target directories**

```bash
mkdir -p ~/.claude/skills
mkdir -p ~/.claude/agents
```

Windows (PowerShell):
```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.claude\skills"
New-Item -ItemType Directory -Force -Path "$HOME\.claude\agents"
```

**2. Copy each skill folder**

For every folder under `skills/` that contains a `SKILL.md`, copy the whole folder to `~/.claude/skills/`. For example:

```bash
# macOS / Linux — repeat for each skill
cp -r skills/kanban/spec-to-backlog       ~/.claude/skills/
cp -r skills/kanban/issue-intake          ~/.claude/skills/
cp -r skills/kanban/audit-to-backlog      ~/.claude/skills/
cp -r skills/workflow/git-workflow        ~/.claude/skills/
cp -r skills/workflow/project-audit-reviewer ~/.claude/skills/
# ... repeat for all remaining skill folders
```

Windows (PowerShell):
```powershell
Copy-Item -Recurse skills\kanban\spec-to-backlog       "$HOME\.claude\skills\"
Copy-Item -Recurse skills\kanban\issue-intake          "$HOME\.claude\skills\"
# ... repeat for all remaining skill folders
```

To see every skill that needs copying:
```bash
find skills -name "SKILL.md" | sort
```

**3. Copy each agent file**

```bash
# macOS / Linux
cp agents/*.md ~/.claude/agents/
```

Windows (PowerShell):
```powershell
Copy-Item agents\*.md "$HOME\.claude\agents\"
```

**4. Copy the Skill Index**

```bash
cp skills/INDEX.md ~/.claude/skills/INDEX.md
```

Windows (PowerShell):
```powershell
Copy-Item skills\INDEX.md "$HOME\.claude\skills\INDEX.md"
```

---

## Step-by-Step Guide

### Step 1 — Describe Your Project

Copy the two context templates into **your project root** and fill them in.

```bash
# macOS / Linux
cp path/to/drunken-ai-team/templates/PROJECT_BRIEF.md  your-project/
cp path/to/drunken-ai-team/templates/REQUIREMENTS.md   your-project/
```

```powershell
# Windows
Copy-Item path\to\drunken-ai-team\templates\PROJECT_BRIEF.md  your-project\
Copy-Item path\to\drunken-ai-team\templates\REQUIREMENTS.md   your-project\
```

Open each file and fill in every section. The more complete they are, the better every skill and agent performs — these files are the single source of truth for your squad.

**What to fill in:**
- `PROJECT_BRIEF.md` — what you're building, who it's for, the tech stack, constraints, and what's out of scope
- `REQUIREMENTS.md` — Must/Should/Could/Won't features, performance targets, security requirements, and your Definition of Done

> See [`examples/00-setup/`](./examples/00-setup/) for a fully filled example using a fictional task manager app.

---

### Step 2 — Generate Your Backlog

Open Claude Code inside **your project directory**, then run:

```
/init-project
```

The skill reads your `PROJECT_BRIEF.md` and `REQUIREMENTS.md` and creates one Jira ticket per
feature in the project's backlog, via `jira_create_issue`. It prints a summary table when
finished, then **halts and asks for your approval** before moving anything onto the board.

Urgency lands as a **label** — `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` — not as Jira's `priority`
field, which cannot be set on a team-managed project and reads `Medium` on every issue.

**Review the generated tickets in Jira.** Check that the labels look right and that nothing
important is missing. Edit them in Jira directly.

> See [`examples/01-spec-to-backlog/`](./examples/01-spec-to-backlog/) for what the summary table
> looks like. **The `examples/` fixtures are pre-Jira** — they still show `board/<lane>/TASK-NN.md`
> files, the local board that is now retired. Read them for the shape of the work, not for the
> surface it lands on.

---

### Step 3 — Load the Sprint Queue

```
/refine
```

The skill probes with `jira_board_info` first — **not every board has a backlog** — then moves
tickets onto the board with `jira_move_to_board`, by urgency label:
- `CRITICAL` tickets are moved immediately, no confirmation needed
- `HIGH`, `MEDIUM`, and `LOW` are offered by tier — you choose which to pull in

**It does not transition anything.** Backlog membership and status are two separate axes in
Jira: a ticket moved onto the board is still `TODO` if that is what it was. On the old local
board, moving a lane *was* the transition — that is the one translation that does not survive.

> See [`examples/02-backlog-refinement/`](./examples/02-backlog-refinement/) for the queue report output.

---

### Step 4 — Size the Work

```
/estimate
```

The skill reads the `TODO` tickets on the board and prints an estimation table: T-shirt size
(S/M/L/XL), estimated AI turns, and human review effort per ticket.

The table is printed, **not written back**. This Jira has no story points, so the skill has
nowhere on a ticket to put an estimate and is forbidden to invent one.

If any ticket is rated **XL**, the skill flags it and recommends splitting — XL tickets are too
large for a single agent context window and produce unreliable output.

> See [`examples/03-task-estimation/`](./examples/03-task-estimation/) for a sample estimation table.

---

### Step 5 — Start the First Task

There is no `/next` command. Picking up work is two Jira calls and a habit, not a skill —
`next-task` was retired with the local board (see
[`_not_used/skills/next-task/RETIRED.md`](./_not_used/skills/next-task/RETIRED.md)).

Ask the agent to start the next ticket. It should:

1. Call `jira_daily_standup` for the current working set
2. Pick the highest tier — urgency is a **label** (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW`),
   because `priority` cannot be set on a team-managed Jira project
3. Call `jira_assign`, then `jira_start_task` — assignee says whose it is, status says where
4. Read the relevant project files
5. Propose a full **Execution Plan** — target files, implementation steps, and risk notes

Then it should **halt completely** and ask:

> "Tech Lead, do you approve this plan, or would you like to make adjustments before I write the code?"

Read the plan carefully. This is your last checkpoint before code is written. Options:
- **Approve** — agent proceeds with the plan as written
- **Adjust** — tell the agent what to change; it revises and halts again
- **Reject** — transition the ticket back to `TODO` and pick a different one

> Nothing expires a Jira assignee. If an agent stops mid-ticket, reassign it yourself — that
> is the one thing the retired board did that Jira does not.

---

### Step 6 — Review and Close the Task

Once the agent finishes implementation, it calls `jira_submit_for_review` — the ticket goes to
`IN REVIEW`, never straight to `DONE`. **Never skip `IN REVIEW`, including for your own work.**

A ticket in `IN REVIEW` is not merged code. Run the test suite and review the diff against the
target branch before you believe any claim that it is fixed. When satisfied, transition it with
`jira_transition_issue`, and commit with a conventional commit message:

```bash
git commit -m "feat: add user authentication (register/login/JWT)"
```

Then start the next ticket as in Step 5.

---

## Mid-Sprint Scenarios

### Handling a Bug Mid-Sprint

If a bug is reported while a ticket is already in progress, do **not** interrupt the current
ticket. Instead:

```
/issue
```

Describe the bug. The skill will:
1. Run read-only commands to diagnose the root cause
2. Create a Jira ticket with the root cause documented and the urgency label set
3. Leave your current in-flight ticket untouched

Pick the bug ticket up when the current one reaches `IN REVIEW` — or sooner if it outranks what
you are holding.

> `/task` (`agentic-kanban`) is retired. Its triage half is what `/issue` does; its orchestration
> half is not replaced. See
> [`_not_used/skills/agentic-kanban/RETIRED.md`](./_not_used/skills/agentic-kanban/RETIRED.md).

### End-of-Sprint Snapshot

```
/report
```

Prints a status snapshot of the board: what's done, what's in progress, what's queued, and any blockers. Useful for async standups or personal review.

---

## Using the Multi-Agent Squad

The kanban workflow above uses skills (slash commands) running in your own session. For larger, more autonomous work, delegate to the full agent squad:

```bash
# Start with the orchestrator — it reads your context files and assigns work
claude --agent principal-engineer
```

> "Read `PROJECT_BRIEF.md` and `REQUIREMENTS.md`. Analyze the project and give me a platform strategy, initial ADR, and squad plan."

The orchestrator assembles the squad and delegates work with precise, context-rich prompts. See the [Leader's Guidebook](./README.md#leaders-guidebook) in the main README for the full squad workflow.

---

## Full Skill Reference

Once comfortable with the basics, see the [Skill Catalog](./README.md#skill-catalog) in the main README for every available slash command and when to use each one.

| Command | Skill | When to use |
|---|---|---|
| `/system-design` | system-design-rules | Before writing any new system or API |
| `/clean-arch` | clean-architecture | Designing or reviewing layer structure |
| `/ui` | universal-ui | Any frontend layout / visual work |
| `/ux` | universal-ux | Any frontend state / flow / error handling |
| `/infra` | cloud-native | Docker, K8s, CI/CD, IaC |
| `/secure` | secure-by-design | Any auth, data handling, or new endpoint |
| `/test-types` | test-strategy | Choosing the right test for the situation |
| `/test-arch` | test-architecture | Designing a test suite or CI/CD pipeline |
| `/test-report` | test-report-generator | Pre-merge quality gate |
| `/tdd` | core-engineering | Writing new code or fixing a bug |
| `/surgical` | anti-regression | Modifying existing files |
| `/discipline` | ai-output | Enforcing output formatting standards |
| `/git-workflow` | git-workflow | Branches, commits, PR lifecycle |
| `/git` | project-hygiene | Commits, branches, README, ADR |
| `/init-project` | spec-to-backlog | Day 0 — spec → backlog |
| `/issue` | issue-intake | Report a bug or problem — captured to backlog automatically |
| `/refine` | backlog-refinement | Sprint planning — move backlog tickets onto the board |
| `/estimate` | task-estimation | Size tickets before sprint |
| `/report` | local-progress-reporter | Sprint / project status snapshot |
| `/audit` | audit-to-backlog | Post-mortem or code audit |
| `/audit-project` | project-audit-reviewer | Full codebase health check |
| `/incident` | incident-response | Active production outage |
| `/lead` | servant-leadership | Code review, mentorship, team comms |
| `/product` | product-midset | Feature ROI, FinOps, build-vs-buy |
| `/telemetry` | business-telemetry | Adding event tracking |
| `/playbook` | standard-playbook-generator | Generate engineering documentation |
