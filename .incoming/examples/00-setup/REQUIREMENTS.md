# Requirements

---

## Functional Requirements

### Must Have

| # | Feature | User Story |
|---|---|---|
| F-01 | User registration & login | As a user, I want to create an account with email/password so that my tasks are saved and synced across devices |
| F-02 | Task CRUD | As a user, I want to create, edit, complete, and delete tasks so that I can manage my work |
| F-03 | Offline support | As a user, I want to create and edit tasks without internet so that I'm never blocked by connectivity |
| F-04 | Background sync | As a user, I want my offline changes to sync automatically when I reconnect so that I don't have to think about it |
| F-05 | Push notifications | As a user, I want a reminder notification when a task's due date arrives so that I don't miss deadlines |

### Should Have

| # | Feature | User Story |
|---|---|---|
| F-10 | Due dates | As a user, I want to set a due date on any task so that I can prioritize by urgency |
| F-11 | Task labels / tags | As a user, I want to label tasks (e.g., "work", "personal") so that I can filter by context |

### Could Have

| # | Feature | User Story |
|---|---|---|
| F-20 | Subtasks | As a user, I want to break a task into subtasks so that I can track progress on complex work |

### Will Not Have (This Phase)

| # | Feature | Reason Deferred |
|---|---|---|
| F-30 | Shared task lists | Requires real-time collaboration infra — out of scope for MVP |
| F-31 | Third-party integrations | High implementation cost, low MVP value |

---

## Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|---|---|---|
| API response time | < 200ms at P95 | All CRUD endpoints |
| App cold start | < 2s | From tap to usable UI |
| Concurrent users | 500 at launch | Scale to 5,000 by month 3 |
| Uptime SLA | 99.5% | |

### Security

- [x] Authentication required (JWT + refresh token rotation)
- [ ] Role-based access control (not needed — single-user model)
- [x] Data encrypted at rest (RDS encryption enabled)
- [x] Data encrypted in transit (TLS 1.2+)
- [x] PII / sensitive data handling (email address — deletable on GDPR request)
- [ ] Audit logging required (Phase 2)
- [x] Compliance standard: GDPR

### Accessibility

- [x] WCAG 2.1 Level AA minimum
- [x] Screen reader support (VoiceOver / TalkBack)
- [x] Dynamic Type / large text support (mobile)

### Scalability

| Dimension | Current | 12-Month Target |
|---|---|---|
| Registered users | 0 | 10,000 |
| Daily active users | 0 | 2,000 |
| Tasks created per day | 0 | 20,000 |
| Data volume | 0 | ~5GB |

### Platform & Compatibility

| Platform | Min Version |
|---|---|
| iOS | 16.0 |
| Android | 10 (API 29) |
| Backend runtime | Node.js 20 LTS |

### Offline Support

- [x] Required — the following features must work offline:
  - Create task
  - Edit task
  - Complete task
  - Delete task
  - View all tasks

### Localization

- [x] Single language: English (Phase 1)

---

## Definition of Done

A feature is done when:

- [x] Acceptance criteria from the user story pass
- [x] Unit tests written and green
- [x] Integration tests written and green
- [x] No new lint warnings or type errors introduced
- [x] No new secrets in code, no new unvalidated inputs at system boundary
- [x] VoiceOver / TalkBack accessibility labels set
- [x] `/test-report` pre-merge gate passes
- [x] Conventional commit with type prefix (`feat:`, `fix:`, `chore:`)
- [x] PR description explains what changed and why
