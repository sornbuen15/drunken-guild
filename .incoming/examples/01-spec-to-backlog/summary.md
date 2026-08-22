# `/init-project` — Summary Output

> This is the summary table printed by the skill after creating the tickets.
> The skill halts here and asks: **"Tickets created in the backlog. Shall I move any onto the board?"**

---

## Created Tickets

| Key | Summary | Phase | Urgency label | Suggested specialist |
|---|---|---|---|---|
| TF-1 | `[Auth] Implement email/password registration, login and JWT sessions` | Phase 1 — MVP | **`critical`** | `@fullstack-engineer` |
| TF-2 | `[API] Build task CRUD endpoints scoped to the authenticated user` | Phase 1 — MVP | **`critical`** | `@fullstack-engineer` |
| TF-3 | `[Mobile] Build the task list screen in React Native` | Phase 1 — MVP | `high` | `@cross-platform-mobile` |
| TF-4 | `[Mobile] Add offline write queue and sync-on-reconnect` | Phase 1 — MVP | `high` | `@cross-platform-mobile` |
| TF-5 | `[CI] Stand up the build, test and release pipeline` | Phase 1 — MVP | `high` | `@devops-engineer` |
| TF-6 | `[QA] Scaffold the end-to-end test suite` | Phase 1 — MVP | `medium` | `@qa-engineer` |

**6 tickets created in the backlog, all at status `TODO`.**

Note what the last line does *not* say. Backlog membership and status are separate axes: these
tickets are out of the current working set, and they are also `TODO`. Moving one onto the board
does not transition it.

Note also that no ticket is assigned. The specialist is recorded as a label
(`agent:fullstack-engineer`); the **assignee** field says who is working a ticket *now*, and
nobody is yet.

Tickets created. Shall I move any onto the board?

> _Next step: run `/refine` and let `backlog-refinement` handle it by urgency tier._
