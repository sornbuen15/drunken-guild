# `/estimate` — Estimation Table Output

> This is the estimation table the skill prints for all tasks in `todo/`.

---

| Task ID | Task Name | Priority | T-Shirt | Est. AI Turns | Human Review | Risk / Blocker Note |
|---|---|---|---|---|---|---|
| TASK-01 | User Auth (Register / Login / JWT) | CRITICAL | M | 3–4 | **Medium** | JWT secret rotation strategy needs confirming before implementation. Password hashing algorithm (bcrypt rounds) should be set explicitly. |
| TASK-02 | Task CRUD API | CRITICAL | L | 5–6 | **High** | Requires DB schema + migration. Soft-delete logic (`deletedAt`) adds edge cases to GET queries. Ownership check (`403`) must be tested explicitly — easy to miss. |

---

## Recommendations

- **TASK-01 (M):** Straightforward. Proceed directly. Confirm JWT expiry duration and refresh token TTL with the Tech Lead before starting.
- **TASK-02 (L):** More complex due to migration + soft-delete. Recommend the Tech Lead reviews the DB schema before the agent writes any migration file.
- No XL tasks — no splits required.

**Estimated total for this sprint:** ~9–10 AI turns, ~30–45 min human review.

> _Next step: run `/next` to pick TASK-01 and receive a step-by-step execution plan for approval._
