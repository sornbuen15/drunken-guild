# Getting Started with AI Team Toolkit

A complete walkthrough — from installation through your first completed task. Each step links to a matching example in [`examples/`](./examples/) so you can see expected output before you run anything.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [macOS / Linux](#macos--linux)
  - [Windows](#windows)
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
- **macOS / Linux:** Bash 3.2+, `rsync`
- **Windows:** PowerShell 5.1+ or [PowerShell Core 7+](https://github.com/PowerShell/PowerShell/releases)

---

## Installation

### macOS / Linux

```bash
# 1. Clone the repo
git clone <repo-url> ai-team-toolkit
cd ai-team-toolkit

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
git clone <repo-url> ai-team-toolkit
cd ai-team-toolkit

# 2. Allow script execution (one-time, current user only)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3. Deploy skills to %USERPROFILE%\.claude\skills\
.\scripts\install\sync_skills.ps1

# 4. Deploy agents to %USERPROFILE%\.claude\agents\
.\scripts\install\sync_agents.ps1
```

Both scripts are safe to re-run after any update.

> **Note:** The `scripts\kanban\` scripts are separate — they implement board I/O for your *target project*, not this toolkit. Copy them into your project when you need them.

---

## Step-by-Step Guide

### Step 1 — Describe Your Project

Copy the two context templates into **your project root** and fill them in.

```bash
# macOS / Linux
cp path/to/ai-team-toolkit/templates/PROJECT_BRIEF.md  your-project/
cp path/to/ai-team-toolkit/templates/REQUIREMENTS.md   your-project/
```

```powershell
# Windows
Copy-Item path\to\ai-team-toolkit\templates\PROJECT_BRIEF.md  your-project\
Copy-Item path\to\ai-team-toolkit\templates\REQUIREMENTS.md   your-project\
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

The skill reads your `PROJECT_BRIEF.md` and `REQUIREMENTS.md` and generates one task file per feature in `.claude/board/backlog/`. It prints a summary table when finished, then **halts and asks for your approval** before moving anything.

```
.claude/board/
└── backlog/
    ├── TASK-001_user-auth-jwt.md
    ├── TASK-002_product-listing.md
    └── ...
```

**Review the generated tasks.** Check that priorities look right and that nothing important is missing. You can edit task files directly.

> See [`examples/01-spec-to-backlog/`](./examples/01-spec-to-backlog/) for what the generated files and summary table look like.

---

### Step 3 — Load the Sprint Queue

```
/refine
```

The skill scans your backlog and promotes tasks into `todo/` based on priority:
- `CRITICAL` tasks are promoted immediately, no confirmation needed
- `HIGH`, `MEDIUM`, and `LOW` tasks are offered by tier — you choose which to pull in

After `/refine`:

```
.claude/board/
├── todo/       ← tasks ready to execute (CRITICAL first, then HIGH, etc.)
└── backlog/    ← everything else, waiting for future sprints
```

> See [`examples/02-backlog-refinement/`](./examples/02-backlog-refinement/) for the queue report output.

---

### Step 4 — Size the Work

```
/estimate
```

The skill reads everything in `todo/` and prints an estimation table: T-shirt size (S/M/L/XL), estimated AI turns, and human review effort per task.

If any task is rated **XL**, the skill flags it and recommends splitting — XL tasks are too large for a single agent context window and produce unreliable output.

> See [`examples/03-task-estimation/`](./examples/03-task-estimation/) for a sample estimation table.

---

### Step 5 — Start the First Task

```
/next
```

The skill:
1. Checks that `in-progress/` is empty (WIP limit = 1)
2. Picks the highest-priority task from `todo/`
3. Moves it to `in-progress/`
4. Reads the relevant project files
5. Proposes a full **Execution Plan** — target files, implementation steps, and risk notes

Then **halts completely** and asks:

> "Tech Lead, do you approve this plan, or would you like to make adjustments before I write the code?"

Read the plan carefully. This is your last checkpoint before code is written. Options:
- **Approve** — agent proceeds with the plan as written
- **Adjust** — tell the agent what to change; it revises and halts again
- **Reject** — move the task back to `todo/` and pick a different one

> See [`examples/04-next-task/`](./examples/04-next-task/) for a full example execution plan.

---

### Step 6 — Review and Close the Task

Once the agent finishes implementation, run the test suite and review the diff. When satisfied, close the task:

```bash
# macOS / Linux
./scripts/kanban/kanban_write.sh done TASK-001
```

```powershell
# Windows
.\scripts\kanban\kanban_write.ps1 done TASK-001
```

Then commit with a conventional commit message:

```bash
git commit -m "feat: add user authentication (register/login/JWT)"
```

Now `in-progress/` is empty again. Run `/next` to pick up the next task.

---

## Mid-Sprint Scenarios

### Handling a Bug Mid-Sprint

If a bug is reported while a task is already in progress, do **not** interrupt the current task. Instead:

```
/task
```

Describe the bug. The skill will:
1. Run read-only commands to diagnose the root cause
2. Create a new task file in `todo/` with the root cause documented
3. Leave your current `in-progress/` task untouched

The bug task will be picked up automatically by `/next` after the current task is closed — or earlier if you manually promote it.

> See [`examples/05-agentic-kanban/`](./examples/05-agentic-kanban/) for an example bug task with pre-flight investigation.

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
| `/task` | agentic-kanban | New bug or feature — create task first |
| `/refine` | backlog-refinement | Sprint planning — promote tasks by priority |
| `/estimate` | task-estimation | Size tasks before sprint |
| `/next` | next-task | Start next highest-priority task |
| `/report` | local-progress-reporter | Sprint / project status snapshot |
| `/audit` | audit-to-backlog | Post-mortem or code audit |
| `/audit-project` | project-audit-reviewer | Full codebase health check |
| `/incident` | incident-response | Active production outage |
| `/lead` | servant-leadership | Code review, mentorship, team comms |
| `/product` | product-midset | Feature ROI, FinOps, build-vs-buy |
| `/telemetry` | business-telemetry | Adding event tracking |
| `/playbook` | standard-playbook-generator | Generate engineering documentation |
