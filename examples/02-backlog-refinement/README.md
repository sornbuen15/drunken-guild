# Stage 2 — `/refine` (backlog-refinement)

## What this skill does

`/refine` reads the Jira backlog and the board, and moves the right tickets **onto the board**
with `jira_move_to_board` — ready to be picked up.

**Key rules the skill enforces:**

- **Probe first.** It calls `jira_board_info` before anything else, because **not every board
  has a backlog.** If this one does not, the skill says so and stops rather than improvising.
- **Critical first.** Any ticket labelled `critical` in the backlog is moved onto the board
  immediately, with no confirmation needed.
- **Tiers, not tickets.** You can say "move all `high`" — never "move TF-3". Picking individual
  tickets is how a backlog stops being ordered.
- **It does not transition anything.** This is the rule that surprises people, and it is the one
  translation from the old local board that does not survive. On the board, moving a lane *was*
  the transition. In Jira, board membership and status are two separate axes:
  `jira_move_to_board` changes membership only. A ticket that was `TODO` in the backlog is still
  `TODO` on the board. The skill is forbidden to call `jira_transition_issue` at all.

## How to invoke

```
/refine
```

Run at the start of a sprint, or any time you want to re-evaluate what is in the working set.

---

## Example output for TaskFlow

After `/refine` runs on the Stage 1 backlog:

- **TF-1** (`critical`) → moved onto the board
- **TF-2** (`critical`) → moved onto the board
- TF-3, TF-4, TF-5, TF-6 stay in the backlog

All six are still at status `TODO`. Nothing was transitioned and nothing was assigned.

The skill then prints the queue report. See [`output.md`](./output.md).
