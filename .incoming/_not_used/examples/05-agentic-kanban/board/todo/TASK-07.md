---
id: TASK-007
type: bug
phase: 1
priority: HIGH
title: Fix login 500 for emails with uppercase letters
assigned_to: "@fullstack-engineer"
depends_on: []
blocks: []
source: "Mid-sprint bug report — 2024-01-15"
---

## Objective
Fix the authentication bug that causes `POST /auth/login` to return a 500 error when the email address contains uppercase letters.

## Context
- Reported mid-sprint while TASK-001 is in progress.
- Root cause identified by pre-flight investigation before creating this task.

## Root Cause
`grep -n "email" src/services/auth.service.ts:42` — the login query uses a case-sensitive exact match:

```ts
// src/services/auth.service.ts:42 — current (broken)
const user = await db('users').where({ email }).first();
```

PostgreSQL `=` comparison is case-sensitive by default. An account registered as `user@example.com` is not found when the login attempt uses `User@Example.com`, so `user` is `undefined`. The subsequent `bcrypt.compare(password, user.password_hash)` throws a `TypeError: Cannot read properties of undefined`, caught by the global error handler and returned as a `500`.

The fix: normalize email to lowercase at both registration and login.

## Acceptance Criteria
- [ ] **`src/services/auth.service.ts`** — `register` and `login` normalize email to lowercase
- [ ] `POST /auth/login` returns `200` regardless of email casing
- [ ] No existing user data is affected (normalization is query-time only; stored emails unchanged)
- [ ] Regression test: register with lowercase email, login with uppercase variant → `200`
- [ ] All existing auth tests still pass
- [ ] Full test suite green

## Technical Notes
- Normalize at the application boundary (`email.toLowerCase()`) — do NOT add a DB-level `LOWER()` call.
- Blast radius: `AuthService.refresh` and `AuthService.deleteAccount` use `userId`, not raw email — no change needed there.
- Run `grep -rn "where.*email" src/` to confirm no other service queries `users` by raw email.
