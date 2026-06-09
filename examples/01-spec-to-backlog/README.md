# Stage 1 — `/init-project` (spec-to-backlog)

## What this skill does

`/init-project` reads your `PROJECT_BRIEF.md` and `REQUIREMENTS.md` and generates a prioritized backlog of atomic task files — one file per feature or concern.

## How to invoke

```
/init-project
```

Run this on Day 0, before any code is written.

## What the skill reads

- `.claude/PROJECT_SPEC.md` (or `PROJECT_BRIEF.md` in your project root)
- `REQUIREMENTS.md`

## What it produces

One `.md` task file per feature, created in `.claude/board/backlog/`. Each file follows a fixed template with Phase, Priority, Objective, and Acceptance Criteria.

After generating the files, the skill outputs a summary table and **halts** — it does not move any task to `todo/` without your approval.

---

## Example output for TaskFlow

The files in `board/backlog/` below are exactly what `/init-project` would create from the `00-setup/` templates.

See [`summary.md`](./summary.md) for the summary table the skill prints at the end.
