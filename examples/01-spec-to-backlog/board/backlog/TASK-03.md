---
id: TASK-003
type: feature
phase: 1
priority: HIGH
title: Build task list UI (mobile)
assigned_to: "@cross-platform-mobile"
depends_on: [TASK-002]
blocks: [TASK-004]
source: "PROJECT_SPEC.md §3.1 — Mobile Task List Screen"
---

## Objective
Build the main task list screen so that users can view, complete, and delete their tasks from the mobile app.

## Context
- Spec §3.1: The task list is the primary screen — it is the first thing users see after login.
- Requires TASK-002 (CRUD API) to be complete so the screen has real data to display.

## Acceptance Criteria
- [ ] **`src/screens/TaskListScreen.tsx`** — task list screen component
- [ ] Task list renders all tasks fetched from the API, sorted by `updatedAt` descending
- [ ] Each row shows: title, completion checkbox, due date (if set), and label chips
- [ ] Tapping the checkbox toggles `completed` and syncs to the API optimistically
- [ ] Swipe-to-delete removes the task from the list and fires `DELETE /tasks/:id`
- [ ] Empty state: friendly prompt ("No tasks yet — add one!")
- [ ] Accessible: VoiceOver/TalkBack labels on all interactive elements
- [ ] Loading and error states handled (skeleton loader, inline error with retry)
- [ ] Tests added and green
- [ ] Full test suite green
