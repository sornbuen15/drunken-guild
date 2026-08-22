# Stage 1 — `/init-project` (spec-to-backlog)

## What this skill does

`/init-project` reads your `PROJECT_BRIEF.md` and `REQUIREMENTS.md` and creates one Jira ticket
per feature or concern, in the project's backlog, via `drunken-jira-mcp`.

## How to invoke

```
/init-project
```

Run this on Day 0, before any code is written.

## What the skill reads

- `PROJECT_BRIEF.md` in your project root (or `.claude/PROJECT_SPEC.md`)
- `REQUIREMENTS.md`

## What it produces

One Jira ticket per feature, created with `jira_create_issue` and parked in the backlog with
`jira_move_to_backlog`. Each ticket follows the three-heading shape defined in
the `jira-tickets` skill — **FINDING, SCOPE, ACCEPTANCE**,
and nothing else — under a summary line of the form `[Area] imperative statement of the change`.

After creating the tickets, the skill prints a summary table and **halts**. It does not move
anything onto the board without your approval.

### Three things about this Jira that shape the output

- **Urgency is a label, not `priority`.** `priority` cannot be set on a team-managed project;
  every issue reads `Medium` regardless of what is sent. The tickets below carry
  `critical` / `high` / `medium` labels instead.
- **Backlog is not a status.** `jira_move_to_backlog` changes membership in the current working
  set. Every ticket below is still `TODO`.
- **≤ 120 words** for a task or bug. Longer means it is two tickets, or it needs a parent Epic.

---

## Example output for TaskFlow

Six tickets, created from the `00-setup/` templates. Rendered here as they would read in Jira.

### TF-1 — `[Auth] Implement email/password registration, login and JWT sessions`

*Labels: `critical`, `phase-1`, `agent:fullstack-engineer` · Parent: TF-EPIC-1*

```
FINDING
TaskFlow has no authentication. Every other feature is per-user and cannot be built
until identity exists.

SCOPE
- src/services/auth.service.ts — register, login, refresh, logout, deleteAccount
- POST /auth/register, /auth/login, /auth/refresh, /auth/logout
- JWT middleware on all task endpoints
- DELETE /auth/account for GDPR erasure

ACCEPTANCE
- Passwords stored bcrypt-hashed, never returned in any response
- Expired or tampered JWTs rejected with 401
- Refresh token invalidated by logout
- Account deletion removes the user and all associated data
- Tests added, full suite green
```

### TF-2 — `[API] Build task CRUD endpoints scoped to the authenticated user`

*Labels: `critical`, `phase-1`, `agent:fullstack-engineer` · Parent: TF-EPIC-1*

Blocked in practice by TF-1 — every endpoint needs the JWT middleware. That prerequisite is
stated in the SCOPE, because there is no dependency field for a scheduler to read.

### TF-3 — `[Mobile] Build the task list screen in React Native`

*Labels: `high`, `phase-1`, `agent:cross-platform-mobile` · Parent: TF-EPIC-1*

### TF-4 — `[Mobile] Add offline write queue and sync-on-reconnect`

*Labels: `high`, `phase-1`, `agent:cross-platform-mobile` · Parent: TF-EPIC-1*

### TF-5 — `[CI] Stand up the build, test and release pipeline`

*Labels: `high`, `phase-1`, `agent:devops-engineer` · Parent: TF-EPIC-1*

### TF-6 — `[QA] Scaffold the end-to-end test suite`

*Labels: `medium`, `phase-1`, `agent:qa-engineer` · Parent: TF-EPIC-1*

See [`summary.md`](./summary.md) for the table the skill prints at the end.
