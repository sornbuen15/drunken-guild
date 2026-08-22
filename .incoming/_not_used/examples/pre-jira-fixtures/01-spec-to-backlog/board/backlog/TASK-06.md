---
id: TASK-006
type: feature
phase: 1
priority: MEDIUM
title: Scaffold E2E test suite
assigned_to: "@qa-engineer"
depends_on: [TASK-003, TASK-005]
blocks: []
source: "PROJECT_SPEC.md §5.1 — End-to-End Testing"
---

## Objective
Set up the end-to-end testing framework and write the core happy-path test for the auth + task creation flow so that regressions are caught before every release.

## Context
- Spec §5.1: E2E coverage of the core happy-path is the minimum bar for release readiness.
- Requires the mobile UI (TASK-003) and CI pipeline (TASK-005) to be in place.

## Acceptance Criteria
- [ ] **`e2e/auth-task.test.ts`** — happy-path E2E test
- [ ] Detox (React Native) configured and running on CI for iOS simulator and Android emulator
- [ ] Happy path E2E test: register → login → create task → complete task → delete task → logout
- [ ] Tests run headlessly in GitHub Actions on every PR targeting `main`
- [ ] Failed E2E tests block the merge
- [ ] Test output and screenshots on failure uploaded as CI artifacts
- [ ] Full test suite green
