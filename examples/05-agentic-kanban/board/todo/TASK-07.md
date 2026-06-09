---
Phase: Phase 1 — MVP
Priority: HIGH
Type: Bug
---

# TASK-07: Login Returns 500 for Emails with Uppercase Letters

## Objective
Fix the authentication bug that causes `POST /auth/login` to return a 500 error when the email address contains uppercase letters.

## Root Cause
Pre-flight investigation (`grep -n "email" src/services/auth.service.ts`) found that the login query uses a case-sensitive exact match:

```ts
// src/services/auth.service.ts — current (broken)
const user = await db('users').where({ email }).first();
```

PostgreSQL `=` comparison is case-sensitive by default. An account registered as `user@example.com` is not found when the login attempt uses `User@Example.com`, so `user` is `undefined`. The subsequent `bcrypt.compare(password, user.password_hash)` throws a `TypeError: Cannot read properties of undefined`, which is caught by the global error handler and returned as a `500`.

The fix is to normalize email to lowercase at both registration and login.

## Required Skills to Load
- `$HOME/.claude/skills/workflow/anti-regression/SKILL.md`
- `$HOME/.claude/skills/workflow/core-engineering/SKILL.md`

## Execution Steps

### Step 1: Add regression test (Red)
- [ ] Write a failing integration test: register with lowercase email, attempt login with uppercase variant → expect `200`, not `500`

### Step 2: Apply fix (Green)
- [ ] In `AuthService.register`: normalize `email` to lowercase before inserting (`email.toLowerCase()`)
- [ ] In `AuthService.login`: normalize `email` to lowercase before querying
- [ ] Do NOT add a DB-level `LOWER()` call — normalize at the application boundary instead (simpler, consistent)

### Step 3: Blast radius check
- [ ] Verify `AuthService.refresh` and `AuthService.deleteAccount` do not pass raw email — confirm they use `userId`, not email (they do — no change needed)
- [ ] Check no other service queries `users` by raw email — `grep -rn "where.*email" src/`

### Step 4: Verify
- [ ] New regression test passes
- [ ] All existing auth tests still pass
- [ ] Manual test: register `test@example.com`, login as `TEST@EXAMPLE.COM` → `200`

## Acceptance Criteria
- [ ] `POST /auth/login` returns `200` regardless of email casing
- [ ] No existing user data is affected (normalization is query-time only, stored emails unchanged)
- [ ] Regression test added and green
