---
id: TASK-002
type: feature
phase: 1
priority: CRITICAL
title: Build task CRUD REST API
assigned_to: "@fullstack-engineer"
depends_on: [TASK-001]
blocks: [TASK-003]
source: "PROJECT_SPEC.md §2.2 — Task Management API"
---

## Objective
Build the core REST API endpoints for creating, reading, updating, and deleting tasks so that the mobile app has a backend to sync with.

## Context
- Spec §2.2: CRUD API is the backbone of the product — mobile UI cannot be built without it.
- All endpoints require a valid JWT; TASK-001 must complete first.

## Acceptance Criteria
- [ ] **`src/routes/tasks.router.ts`** and **`src/services/tasks.service.ts`** — full CRUD implemented
- [ ] `POST /tasks` creates a task for the authenticated user; returns created task with server-generated `id` and `updatedAt`
- [ ] `GET /tasks` returns all tasks for the authenticated user, sorted by `updatedAt` descending
- [ ] `PATCH /tasks/:id` updates allowed fields (`title`, `completed`, `dueDate`, `labels`); returns updated task
- [ ] `DELETE /tasks/:id` soft-deletes the task (sets `deletedAt`); excluded from `GET /tasks`
- [ ] All endpoints require valid JWT; unauthenticated requests return `401`
- [ ] A user cannot read or modify another user's tasks (`403` on ownership mismatch)
- [ ] API P95 response time < 200ms under 100 concurrent requests
- [ ] Tests added and green
- [ ] Full test suite green
