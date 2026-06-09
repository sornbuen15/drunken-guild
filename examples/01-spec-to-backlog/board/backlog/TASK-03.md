---
Phase: Phase 1 — MVP
Priority: HIGH
---

# TASK-03: Task List UI (React Native)

## Objective
Build the main task list screen so that users can view, complete, and delete their tasks from the mobile app.

## Acceptance Criteria
- [ ] Task list screen renders all tasks fetched from the API, sorted by `updatedAt` descending
- [ ] Each task row shows: title, completion checkbox, due date (if set), and label chips
- [ ] Tapping the checkbox toggles `completed` and syncs to the API optimistically
- [ ] Swipe-to-delete removes the task from the list and fires `DELETE /tasks/:id`
- [ ] Empty state renders a friendly prompt ("No tasks yet — add one!")
- [ ] List is accessible: VoiceOver/TalkBack labels on all interactive elements
- [ ] Loading and error states are handled (skeleton loader, inline error with retry)
