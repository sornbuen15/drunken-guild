---
id: TASK-004
type: feature
phase: 1
priority: HIGH
title: Implement offline sync layer
assigned_to: "@cross-platform-mobile"
depends_on: [TASK-003]
blocks: []
source: "PROJECT_SPEC.md §3.2 — Offline-First Sync"
---

## Objective
Implement a local-first sync layer so that task creation, edits, and deletions work without an internet connection and sync automatically when connectivity is restored.

## Context
- Spec §3.2: Offline support is a hard requirement — users are frequently in low-connectivity environments.
- Uses SQLite via `expo-sqlite` for local persistence.

## Acceptance Criteria
- [ ] **`src/storage/local.db.ts`** — SQLite schema and query layer
- [ ] **`src/sync/sync.service.ts`** — mutation queue and replay logic
- [ ] All four CRUD operations work with no network and update the local store immediately
- [ ] When connectivity is restored, queued mutations are replayed to the API in order
- [ ] Sync conflicts resolved with last-write-wins using server `updatedAt` timestamp
- [ ] Sync status indicator (synced / syncing / offline) visible in the UI
- [ ] No task is lost if the app is force-closed while offline mutations are queued
- [ ] Tests added and green
- [ ] Full test suite green
