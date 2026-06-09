---
Phase: Phase 1 — MVP
Priority: MEDIUM
---

# TASK-06: E2E Test Suite Scaffold

## Objective
Set up the end-to-end testing framework and write the core happy-path test for the auth + task creation flow so that regressions are caught before every release.

## Acceptance Criteria
- [ ] Detox (React Native) configured and running on CI for both iOS simulator and Android emulator
- [ ] Happy path E2E test: register → login → create task → complete task → delete task → logout
- [ ] Test runs headlessly in GitHub Actions on every PR targeting `main`
- [ ] Failed E2E tests block the merge
- [ ] Test output and screenshots on failure are uploaded as CI artifacts
