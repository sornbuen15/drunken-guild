# Stage 5 — `/task` (agentic-kanban)

## What this skill does

`/task` is used mid-sprint when a new bug or feature request comes in. It stops you from jumping straight into code — instead it creates a structured task file first, then (and only then) proceeds with execution.

**Key rules:**
- For a **production bug**: target directory is `todo/` (immediate queue)
- For a **new feature or refactor**: target directory is `backlog/` (deferred)
- Bug tasks include a **Root Cause** section populated by pre-flight read-only investigation
- No code is written until the task file exists

## How to invoke

```
/task  (then describe the bug or feature)
```

---

## Example: Mid-Sprint Bug

While TASK-01 is in `in-progress/`, a bug is reported:

> "Login returns 500 when the email address contains uppercase letters."

The skill:
1. Runs read-only pre-flight investigation (`grep`, `cat`) to identify the cause
2. Creates TASK-07 in `todo/` (production bug → immediate queue)
3. Halts — TASK-01 is still in `in-progress/`, so TASK-07 waits until TASK-01 is done

See [`board/todo/TASK-07.md`](./board/todo/TASK-07.md) for the task file created.

> **Note:** `/next` will refuse to pick TASK-07 until TASK-01 is moved to `done/`. WIP limit = 1 is enforced.
