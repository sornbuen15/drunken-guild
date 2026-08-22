# `/refine` — Queue Report Output

> This is the queue report the skill prints after moving tickets onto the board.

---

## Board probe

```
jira_board_info → board has a backlog: yes
                  issue types accepted: Task, Bug, Story, Epic
                  priority settable: no  (team-managed project)
```

The probe is not a formality. A board without a backlog cannot support this skill at all, and
`priority` being unsettable is why every row below shows a label rather than a priority.

---

## Current State

**In Progress:** _(nothing — no ticket is assigned or started)_

---

## On the board (in the current working set)

| # | Key | Summary | Urgency label | Status |
|---|---|---|---|---|
| 1 | TF-1 | `[Auth] Implement email/password registration, login and JWT sessions` | **`critical`** | `TODO` |
| 2 | TF-2 | `[API] Build task CRUD endpoints scoped to the authenticated user` | **`critical`** | `TODO` |

Both were moved from the backlog automatically under the critical-first rule.

**Read that Status column carefully.** These tickets are on the board and they are still `TODO`.
Being on the board says "this is in the current working set" and nothing more. Nothing here has
been transitioned, and nothing has been assigned — an assignee says who is working a ticket
*now*, and work has not started.

---

## Backlog (remaining)

| Key | Summary | Urgency label | Status |
|---|---|---|---|
| TF-3 | `[Mobile] Build the task list screen in React Native` | `high` | `TODO` |
| TF-4 | `[Mobile] Add offline write queue and sync-on-reconnect` | `high` | `TODO` |
| TF-5 | `[CI] Stand up the build, test and release pipeline` | `high` | `TODO` |
| TF-6 | `[QA] Scaffold the end-to-end test suite` | `medium` | `TODO` |

---

**Note:** TF-3, TF-4 and TF-5 are `high`. They were not moved because the `critical` tier goes
first. Run `/refine` again once TF-1 and TF-2 are `DONE` to offer the `high` tier.

> _Next step: run `/estimate` to size what is on the board before starting work._
