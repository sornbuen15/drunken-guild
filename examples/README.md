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
  └── Generates the initial backlog: TASK-01 through TASK-06

Stage 2 — /refine  (backlog-refinement)
  └── Moves the critical tickets onto the board
      The rest stay in the backlog

Stage 3 — /estimate  (task-estimation)
  └── Sizes the TODO tickets: T-shirt, AI turns, review effort
```

> **These fixtures are pre-Jira and are being rewritten.** Each stage still ships a
> `board/<lane>/TASK-NN.md` directory as its expected output — the local board that `CLAUDE.md`
> now forbids. The skills themselves already run on Jira; only these recorded outputs lag. Read
> them for the *shape* of the work, not for the surface it lands on.
>
> Stages 4 (`/next`) and 5 (`/task`) are gone: the skills they demonstrated were retired with the
> board. Both are kept at [`_not_used/examples/`](../_not_used/examples/).

---

## Stages

- [`00-setup/`](./00-setup/) — Filled project context files for TaskFlow
- [`01-spec-to-backlog/`](./01-spec-to-backlog/) — Output of `/init-project`
- [`02-backlog-refinement/`](./02-backlog-refinement/) — Output of `/refine`
- [`03-task-estimation/`](./03-task-estimation/) — Output of `/estimate`
- [`contributing/`](./contributing/) — How to write a new skill or agent
