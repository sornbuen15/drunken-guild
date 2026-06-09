---
Phase: Phase 1 — MVP
Priority: CRITICAL
---

# TASK-02: Task CRUD API

## Objective
Build the core REST API endpoints for creating, reading, updating, and deleting tasks so that the mobile app has a backend to sync with.

## Acceptance Criteria
- [ ] `POST /tasks` creates a task for the authenticated user; returns the created task with a server-generated `id` and `updatedAt` timestamp
- [ ] `GET /tasks` returns all tasks for the authenticated user, sorted by `updatedAt` descending
- [ ] `PATCH /tasks/:id` updates allowed fields (`title`, `completed`, `dueDate`, `labels`); returns the updated task
- [ ] `DELETE /tasks/:id` soft-deletes the task (sets `deletedAt`); excluded from `GET /tasks` responses
- [ ] All endpoints require a valid JWT; unauthenticated requests return `401`
- [ ] A user cannot read or modify another user's tasks (`403` on ownership mismatch)
- [ ] API P95 response time < 200ms under 100 concurrent requests (load tested)
