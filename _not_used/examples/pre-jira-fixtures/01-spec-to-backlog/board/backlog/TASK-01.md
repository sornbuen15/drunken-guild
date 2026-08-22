---
id: TASK-001
type: feature
phase: 1
priority: CRITICAL
title: Implement user authentication (register / login / JWT)
assigned_to: "@fullstack-engineer"
depends_on: []
blocks: [TASK-002, TASK-003]
source: "PROJECT_SPEC.md §2.1 — Core Authentication"
---

## Objective
Implement email/password registration, login, and JWT-based session management so that all other features can operate on a per-user basis.

## Context
- Spec §2.1: Auth is the foundational layer — all task endpoints require a valid JWT.
- POLICY.md: Passwords must never be stored in plaintext; bcrypt required.

## Acceptance Criteria
- [ ] **`src/services/auth.service.ts`** — register, login, refresh, logout, deleteAccount methods
- [ ] `POST /auth/register` creates a user, hashes the password (bcrypt), returns JWT + refresh token
- [ ] `POST /auth/login` validates credentials and returns JWT + refresh token
- [ ] `POST /auth/refresh` exchanges a valid refresh token for a new JWT
- [ ] `POST /auth/logout` invalidates the refresh token
- [ ] JWT middleware rejects expired or tampered tokens with `401`
- [ ] Passwords are never stored in plaintext or returned in any response
- [ ] GDPR: user account and all associated data is fully deletable via `DELETE /auth/account`
- [ ] Tests added and green
- [ ] Full test suite green
