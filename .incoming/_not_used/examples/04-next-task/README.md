# Stage 4 — `/next` (next-task)

## What this skill does

`/next` enforces a strict WIP limit of 1: one task in `in-progress/` at a time. It picks the highest-priority task from `todo/`, moves it to `in-progress/`, then proposes a full execution plan — and **halts before writing any code**.

**Key rules:**
- If `in-progress/` is not empty → skill refuses to pick a new task
- Selection order: CRITICAL → HIGH → MEDIUM → LOW (ties broken by lowest Task ID)
- The execution plan is a read-only proposal — no files are modified until you approve

## How to invoke

```
/next
```

---

## Example output for TaskFlow

1. Skill checks `in-progress/` → empty, proceeds
2. Scans `todo/`: TASK-01 (CRITICAL) and TASK-02 (CRITICAL)
3. Selects TASK-01 (oldest CRITICAL)
4. Moves TASK-01 from `todo/` → `in-progress/`
5. Reads project files to formulate an execution plan
6. Prints the plan and halts — see [`execution-plan.md`](./execution-plan.md)

Board state after `/next`:
- `in-progress/` → TASK-01
- `todo/` → TASK-02
