# `/estimate` — Estimation Table Output

> This is the estimation table the skill prints for the `TODO` tickets on the board.
> Nothing here is written back to Jira — there are no story points to write it to.

---

| Key | Summary | Urgency | T-Shirt | Est. AI Turns | Human Review | Risk / Blocker Note |
|---|---|---|---|---|---|---|
| TF-1 | `[Auth] Registration, login and JWT sessions` | `critical` | M | 3–4 | **Medium** | JWT secret rotation strategy needs confirming before implementation. Password hashing algorithm (bcrypt rounds) should be set explicitly. |
| TF-2 | `[API] Task CRUD scoped to the authenticated user` | `critical` | L | 5–6 | **High** | Requires DB schema + migration. Soft-delete logic (`deletedAt`) adds edge cases to GET queries. Ownership check (`403`) must be tested explicitly — easy to miss. |

---

## Recommendations

- **TF-1 (M):** Straightforward. Proceed directly. Confirm JWT expiry duration and refresh token TTL with the Tech Lead before starting.
- **TF-2 (L):** More complex due to migration + soft-delete. Recommend the Tech Lead reviews the DB schema before the agent writes any migration file.
- No XL tickets — no splits required.

**Estimated total for this sprint:** ~9–10 AI turns, ~30–45 min human review.

None of the above is now recorded in Jira. If a number here matters to someone other than you,
put it in a ticket comment with `jira_add_comment` — deliberately, as prose — rather than
expecting a field to hold it.

> _Next step: assign TF-1 with `jira_assign`, then `jira_start_task`, and have the specialist
> propose an execution plan before writing any code._
