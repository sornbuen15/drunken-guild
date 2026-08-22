# Examples & Walkthrough

This directory walks through a complete project lifecycle using the Drunken AI Team — from blank templates to a working Jira board — using a fictional app called **TaskFlow**.

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

Each stage shows the **state after** that skill fires.

```
Stage 0 — Setup
  └── Fill in PROJECT_BRIEF.md + REQUIREMENTS.md

Stage 1 — /init-project  (spec-to-backlog)
  └── Creates the initial Jira backlog: TF-1 through TF-6
      Urgency lands as a label; priority is not settable here

Stage 2 — /refine  (backlog-refinement)
  └── Moves the critical tickets onto the board
      The rest stay in the backlog. Nothing is transitioned:
      board membership and status are separate axes

Stage 3 — /estimate  (task-estimation)
  └── Sizes the TODO tickets: T-shirt, AI turns, review effort
      Printed, never written back — this Jira has no story points
```

> Stages 4 (`/next`) and 5 (`/task`) are gone: the skills they demonstrated were retired with
> the local board. Both are kept at [`_not_used/examples/`](../_not_used/examples/), where their
> `board/` fixtures are the clearest surviving record of how that board looked in use.

---

## Stages

- [`00-setup/`](./00-setup/) — Filled project context files for TaskFlow
- [`01-spec-to-backlog/`](./01-spec-to-backlog/) — Output of `/init-project`
- [`02-backlog-refinement/`](./02-backlog-refinement/) — Output of `/refine`
- [`03-task-estimation/`](./03-task-estimation/) — Output of `/estimate`
- [`contributing/`](./contributing/) — How to write a new skill or agent
