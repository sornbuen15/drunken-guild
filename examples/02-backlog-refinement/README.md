# Stage 2 — `/refine` (backlog-refinement)

## What this skill does

`/refine` scans `backlog/` and `todo/`, applies the priority rules, and promotes the right tasks to `todo/` — ready to be picked up for execution.

**Key rules the skill enforces:**
- **CRITICAL auto-promotion** — any CRITICAL task in `backlog/` is immediately flagged and moved to `todo/`
- **No individual task picking** — you can only say "promote all HIGH" or "promote all CRITICAL", never "do task 003"
- Tasks in `todo/` are always sorted: CRITICAL → HIGH → MEDIUM → LOW

## How to invoke

```
/refine
```

Run at the start of a sprint, or any time you want to re-evaluate priorities.

---

## Example output for TaskFlow

After `/refine` runs on the Stage 1 backlog:

- **TASK-01** (CRITICAL) → promoted to `todo/`
- **TASK-02** (CRITICAL) → promoted to `todo/`
- TASK-03, TASK-04, TASK-05, TASK-06 remain in `backlog/`

The skill then prints the queue report. See [`output.md`](./output.md).
