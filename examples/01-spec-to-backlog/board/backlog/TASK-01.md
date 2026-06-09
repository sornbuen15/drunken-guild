---
Phase: Phase 1 — MVP
Priority: CRITICAL
---

# TASK-01: User Authentication (Register / Login / JWT)

## Objective
Implement email/password registration, login, and JWT-based session management so that all other features can operate on a per-user basis.

## Acceptance Criteria
- [ ] `POST /auth/register` creates a user, hashes the password (bcrypt), and returns a JWT + refresh token
- [ ] `POST /auth/login` validates credentials and returns a JWT + refresh token
- [ ] `POST /auth/refresh` exchanges a valid refresh token for a new JWT
- [ ] `POST /auth/logout` invalidates the refresh token
- [ ] JWT middleware rejects expired or tampered tokens with `401`
- [ ] Passwords are never stored in plaintext or returned in any response
- [ ] GDPR: user account and all associated data is fully deletable via `DELETE /auth/account`
