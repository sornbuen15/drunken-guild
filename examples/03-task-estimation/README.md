# Stage 3 — `/estimate` (task-estimation)

## What this skill does

`/estimate` reads everything in `todo/` and produces a sizing table: T-shirt size, estimated AI turns, human review effort, and any risk flags.

**Estimation metrics:**
| Size | Meaning |
|---|---|
| S | Simple config or single-file change |
| M | Standard feature, 1–2 files |
| L | Complex logic, multiple files, or DB changes |
| XL | Architectural change — high hallucination risk, recommend splitting |

If any task is **XL**, the skill strongly recommends splitting it before execution.

## How to invoke

```
/estimate
```

Run after `/refine`, before picking up the first task.

---

## Example output for TaskFlow

See [`output.md`](./output.md) for the estimation table produced for TASK-01 and TASK-02.
