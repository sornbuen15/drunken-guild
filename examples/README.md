# Examples & Walkthrough

This directory walks through a complete project lifecycle using the Drunken AI Team — from blank templates to a running kanban board — using a fictional app called **TaskFlow**.

> **TaskFlow** is a cross-platform mobile task manager (iOS + Android) with a Node.js/PostgreSQL backend. It's simple enough to understand at a glance, complex enough to demonstrate every part of the toolkit.

---

## Who This Is For

| You are... | Start here |
|---|---|
| New to the toolkit — want to try it on your own project | Read [`GETTING_STARTED.md`](../GETTING_STARTED.md) first, then use these examples as reference |
| Curious what the output looks like before running anything | Follow the stages in order below |
| Writing a new skill or agent | Go to `contributing/` |

---

## Walkthrough Map

Each stage shows the **board state after** that skill fires. Files match exactly what the skill would create or move.

```
Stage 0 — Setup
  └── Fill in PROJECT_BRIEF.md + REQUIREMENTS.md

Stage 1 — /init-project  (spec-to-backlog)
  └── Generates initial backlog: TASK-01 through TASK-06

Stage 2 — /refine  (backlog-refinement)
  └── Promotes CRITICAL tasks → todo/
      Remaining tasks stay in backlog/

Stage 3 — /estimate  (task-estimation)
  └── Sizes todo/ tasks: T-shirt, AI turns, review effort

Stage 4 — /next  (next-task)
  └── Picks TASK-01, moves to in-progress/, proposes execution plan
      Halts — waits for Tech Lead approval before writing code

Stage 5 — /task  (agentic-kanban)
  └── Mid-sprint bug found → TASK-07 created in todo/
```

---

## Stages

- [`00-setup/`](./00-setup/) — Filled project context files for TaskFlow
- [`01-spec-to-backlog/`](./01-spec-to-backlog/) — Output of `/init-project`
- [`02-backlog-refinement/`](./02-backlog-refinement/) — Output of `/refine`
- [`03-task-estimation/`](./03-task-estimation/) — Output of `/estimate`
- [`04-next-task/`](./04-next-task/) — Output of `/next`
- [`05-agentic-kanban/`](./05-agentic-kanban/) — Output of `/task` (mid-sprint bug)
- [`contributing/`](./contributing/) — How to write a new skill or agent
