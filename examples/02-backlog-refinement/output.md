# `/refine` — Queue Report Output

> This is the queue report the skill prints after promoting tasks.

---

## Current State

**In Progress:** _(nothing — no task is currently active)_

---

## Todo Queue (ready for execution)

| # | Task ID | Title | Priority |
|---|---|---|---|
| 1 | TASK-01 | User Authentication (Register / Login / JWT) | **CRITICAL** |
| 2 | TASK-02 | Task CRUD API | **CRITICAL** |

Both CRITICAL tasks were auto-promoted from `backlog/` per the Critical Auto-Promotion rule.

---

## Backlog (remaining)

| Task ID | Title | Priority |
|---|---|---|
| TASK-03 | Task List UI (React Native) | HIGH |
| TASK-04 | Offline Sync | HIGH |
| TASK-05 | CI/CD Pipeline | HIGH |
| TASK-06 | E2E Test Suite Scaffold | MEDIUM |

---

**Note:** TASK-03, TASK-04, and TASK-05 are HIGH priority. They were not promoted because CRITICAL tasks must be completed first. Run `/refine` again after TASK-01 and TASK-02 are in `done/` to promote the HIGH tier.

> _Next step: run `/estimate` to size the tasks in `todo/` before starting work._
