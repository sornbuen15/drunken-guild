# `/next` — Execution Plan Output

> TASK-01 has been moved to `in-progress/`.
> The skill has read the project files and proposes the following execution plan.
> **No code has been written yet. Awaiting Tech Lead approval.**

---

## Active Task: TASK-01 — User Authentication (Register / Login / JWT)

---

## Execution Plan

### Step 1: Database schema
- Create `users` table migration:
  - `id` (UUID, primary key)
  - `email` (varchar, unique, not null)
  - `password_hash` (varchar, not null)
  - `created_at`, `updated_at` (timestamps)
- Create `refresh_tokens` table:
  - `id` (UUID, primary key)
  - `user_id` (FK → users.id, cascade delete)
  - `token_hash` (varchar, not null)
  - `expires_at` (timestamp)
  - `revoked_at` (timestamp, nullable)

### Step 2: Auth service layer
- `AuthService.register(email, password)` — bcrypt hash (rounds: 12), insert user, generate token pair
- `AuthService.login(email, password)` — fetch user, compare hash, generate token pair
- `AuthService.refresh(refreshToken)` — verify token hash, check expiry + revocation, issue new JWT
- `AuthService.logout(refreshToken)` — set `revoked_at` on the token record
- `AuthService.deleteAccount(userId)` — hard-delete user row (cascades to tasks + refresh_tokens)

### Step 3: JWT middleware
- `authenticateJWT` middleware: extract Bearer token from `Authorization` header, verify signature + expiry, attach `req.user = { id, email }`
- Return `401` with `{ error: "Unauthorized" }` on failure — no detail leakage

### Step 4: Route handlers
- `POST /auth/register` → `AuthService.register` → `201` with `{ accessToken, refreshToken }`
- `POST /auth/login` → `AuthService.login` → `200` with `{ accessToken, refreshToken }`
- `POST /auth/refresh` → `AuthService.refresh` → `200` with `{ accessToken, refreshToken }`
- `POST /auth/logout` → `AuthService.logout` → `204`
- `DELETE /auth/account` → `AuthService.deleteAccount` → `204`

### Step 5: Tests
- Unit: `AuthService` — mock DB, test hash comparison, token generation, revocation logic
- Integration: all five endpoints — success paths + failure paths (wrong password, expired token, tampered token)
- Security: verify no plaintext password appears in any response or log

### Step 6: Verify acceptance criteria
- Run full test suite
- Manually test token expiry and refresh flow
- Confirm `DELETE /auth/account` removes all user data from DB

---

## Target Files

| Action | Path |
|---|---|
| Create | `src/db/migrations/001_create_users.sql` |
| Create | `src/db/migrations/002_create_refresh_tokens.sql` |
| Create | `src/services/auth.service.ts` |
| Create | `src/middleware/authenticate-jwt.ts` |
| Create | `src/routes/auth.routes.ts` |
| Create | `src/routes/auth.routes.test.ts` |
| Create | `src/services/auth.service.test.ts` |

---

## Potential Risks

- Refresh token rotation: if we invalidate the old token immediately on refresh, a network failure mid-rotation can lock the user out. Recommend a short grace window (30s overlap).
- `bcrypt` rounds set to 12 — verify this doesn't push login P95 above 200ms under load.

---

**Tech Lead, do you approve this plan, or would you like to make adjustments before I write the code?**
