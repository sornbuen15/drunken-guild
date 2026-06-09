---
Phase: Phase 1 — MVP
Priority: HIGH
---

# TASK-04: Offline Sync

## Objective
Implement a local-first sync layer so that task creation, edits, and deletions work without an internet connection and sync automatically when connectivity is restored.

## Acceptance Criteria
- [ ] Tasks are persisted locally using SQLite (via `expo-sqlite`) on the device
- [ ] All four CRUD operations work with no network connection and update the local store immediately
- [ ] When network connectivity is restored, queued mutations are replayed to the API in order
- [ ] Sync conflicts are resolved with last-write-wins using server `updatedAt` timestamp
- [ ] A sync status indicator (synced / syncing / offline) is visible in the UI
- [ ] No task is lost if the app is force-closed while offline mutations are queued
