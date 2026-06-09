# Getting Started

This guide walks you through using the AI Team Toolkit on a real project — from setup to your first completed task. Each step references the matching example in [`examples/`](./examples/) so you can see what the output should look like before you run it yourself.

> **Before you begin:** Clone this repo and run the sync scripts once.
> ```bash
> bash scripts/sync_skills.sh   # installs skills to ~/.claude/skills/
> bash scripts/sync_agents.sh   # installs agents to ~/.claude/agents/
> ```

---

## Step 1 — Describe your project

Copy the two context templates into your project root and fill them in.

```bash
cp templates/PROJECT_BRIEF.md  your-project/PROJECT_BRIEF.md
cp templates/REQUIREMENTS.md   your-project/REQUIREMENTS.md
```

Open each file and fill in every section. The more complete they are, the better every skill and agent will perform — these files are the single source of truth for your entire squad.

**What to fill in:**
- `PROJECT_BRIEF.md` — what you're building, who it's for, the tech stack, constraints, and what's out of scope
- `REQUIREMENTS.md` — Must/Should/Could/Won't features, performance targets, security requirements, and your Definition of Done

> See [`examples/00-setup/`](./examples/00-setup/) for a fully filled example using a fictional task manager app.

---

## Step 2 — Generate your backlog

Open Claude Code inside your project, then run:

```
/init-project
```

The skill reads your `PROJECT_BRIEF.md` and `REQUIREMENTS.md` and generates one task file per feature in `.claude/board/backlog/`. It prints a summary table when it finishes, then **halts and asks for your approval** before moving anything.

```
.claude/board/
└── backlog/
    ├── TASK-01.md   ← one file per feature, with Priority and Acceptance Criteria
    ├── TASK-02.md
    └── ...
```

At this point: **review the generated tasks.** Check that priorities look right and that nothing important is missing. You can edit task files directly before moving on.

> See [`examples/01-spec-to-backlog/`](./examples/01-spec-to-backlog/) for what the generated files and summary table look like.

---

## Step 3 — Load the sprint queue

```
/refine
```

The skill scans your backlog and automatically promotes tasks into `todo/` based on priority. Any `CRITICAL` task is promoted immediately without asking. `HIGH`, `MEDIUM`, and `LOW` tasks are offered to you by tier — you choose which tier to pull in.

After `/refine`, your board looks like this:

```
.claude/board/
├── todo/       ← tasks ready to execute (CRITICAL first, then HIGH, etc.)
└── backlog/    ← everything else, waiting for future sprints
```

> See [`examples/02-backlog-refinement/`](./examples/02-backlog-refinement/) for the queue report the skill prints.

---

## Step 4 — Size the work

```
/estimate
```

The skill reads everything in `todo/` and prints an estimation table: T-shirt size (S/M/L/XL), estimated AI turns, and human review effort for each task.

If any task is rated **XL**, the skill will flag it and recommend you split it before starting — XL tasks are too large for a single agent context window and will produce unreliable output.

> See [`examples/03-task-estimation/`](./examples/03-task-estimation/) for a sample estimation table.

---

## Step 5 — Start the first task

```
/next
```

The skill checks that `in-progress/` is empty (WIP limit = 1), picks the highest-priority task from `todo/`, moves it to `in-progress/`, reads the relevant project files, and proposes a full **Execution Plan** — target files, implementation steps, and risk notes.

It then **halts completely** and asks:

> "Tech Lead, do you approve this plan, or would you like to make adjustments before I write the code?"

Read the plan carefully. This is your last checkpoint before the agent touches any code. You can:
- **Approve** — the agent proceeds with the plan as written
- **Adjust** — tell the agent what to change; it will revise the plan and halt again
- **Reject** — move the task back to `todo/` and pick a different one

> See [`examples/04-next-task/`](./examples/04-next-task/) for a full example execution plan.

---

## Step 6 — Review and close the task

Once the agent finishes implementation, run the test suite and review the diff. When you're satisfied:

```bash
# Move the task to done/ manually, or ask the agent:
# "Tests pass. Move TASK-01 to done."
mv .claude/board/in-progress/TASK-01.md .claude/board/done/TASK-01.md
```

Then commit with a conventional commit message:

```bash
git commit -m "feat: add user authentication (register/login/JWT)"
```

Now `in-progress/` is empty again. Run `/next` to pick up the next task.

---

## Handling a mid-sprint bug

If a bug is reported while a task is already in progress, do **not** interrupt the current task. Instead:

```
/task
```

Describe the bug. The skill will:
1. Run read-only commands to diagnose the root cause
2. Create a new task file in `todo/` with the root cause documented
3. **Leave your current `in-progress/` task untouched**

The bug task will be picked up automatically by `/next` after the current task is closed — or earlier if you manually move it to `in-progress/` after closing the active task.

> See [`examples/05-agentic-kanban/`](./examples/05-agentic-kanban/) for an example bug task with pre-flight investigation.

---

## End-of-sprint snapshot

```
/report
```

Prints a status snapshot of the board: what's done, what's in progress, what's queued, and any blockers. Useful for async standups or personal review.

---

## Full skill reference

Once you're comfortable with the basics, see the [Skill Catalog](./README.md#skill-catalog) in the main README for every available slash command and when to use each one.

---

## Using the multi-agent squad

The kanban workflow above uses skills (slash commands) running in your own session. For larger, more autonomous work, you can delegate to the full agent squad:

```bash
# Start with the orchestrator — it reads your context files and assigns work
claude --agent principal-engineer
```

See the [Leader's Guidebook](./README.md#leaders-guidebook) in the main README for the full squad workflow.
