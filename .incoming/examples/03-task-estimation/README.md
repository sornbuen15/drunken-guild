# Stage 3 — `/estimate` (task-estimation)

## What this skill does

`/estimate` reads the `TODO` tickets on the Jira board and produces a sizing table: T-shirt
size, estimated AI turns, human review effort, and any risk flags.

**The table is printed, never written back.** This Jira has no story points, so there is nowhere
on a ticket to put an estimate, and the skill is forbidden to invent a field for one. The
estimate lives in the conversation and in whatever the Tech Lead does with it.

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

See [`output.md`](./output.md) for the estimation table produced for TF-1 and TF-2.
