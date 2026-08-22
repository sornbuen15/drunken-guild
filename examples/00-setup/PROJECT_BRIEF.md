# Project Brief

---

## Project Name
TaskFlow

## One-Line Summary
A cross-platform mobile app that helps individuals capture, organize, and complete daily tasks — with full offline support.

---

## Problem Statement
People forget tasks when they switch contexts (work → commute → home). Existing apps are either too heavy (Notion, Jira) or too simple (Apple Reminders). Users need something that works instantly, stays in sync across devices, and doesn't require internet to function.

## Target Users

| User Type | Goal | Key Frustration Today |
|---|---|---|
| Busy professional | Capture tasks quickly, zero friction | Opens app, needs to wait for sync before adding a task |
| Student | Organize tasks by subject/project | Too many taps to create a task with a due date |

---

## Business Goals

- [ ] 1,000 active users within 3 months of launch
- [ ] < 2-second task creation from app open
- [ ] 4.2+ App Store / Play Store rating at launch

---

## Platform Targets

- [ ] Web (browser)
- [ ] Native iOS
- [ ] Native Android
- [x] Cross-platform mobile (iOS + Android, shared codebase)
- [ ] Desktop (macOS / Windows / Linux)
- [x] Backend API only

---

## Domain

- [x] General / No specific domain

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend / Mobile | React Native (Expo) | Shared codebase, iOS + Android |
| Backend | Node.js / Express | REST API |
| Database | PostgreSQL | Tasks, users, sync state |
| Infra / Cloud | AWS (ECS + RDS) | |
| Auth | JWT + refresh tokens | Email/password v1, OAuth v2 |

---

## Team

| Role | Available |
|---|---|
| Full-stack engineer | Yes |
| DevOps / Infra | Yes |
| QA | Yes |
| iOS engineer | No |
| Android engineer | No |
| Designer | No |

---

## Constraints

### Timeline
Phase 1 (MVP) ships in **8 weeks**.

### Budget / Cost
AWS spend target: under $50/month at launch scale.

### Compliance
GDPR — users are EU residents. Email addresses are PII and must be deletable on request.

### Non-Negotiables
- Offline task creation and editing must work without any network connection.
- API P95 response time < 200ms.
- No data loss on sync conflict — last-write-wins with server timestamp is acceptable.

---

## Out of Scope (Phase 1)

- Shared / collaborative task lists
- AI-powered task suggestions
- Third-party integrations (Slack, Google Calendar)

---

## Links & References

| Resource | URL / Path |
|---|---|
| Figma wireframes | (not yet designed) |
| Competitor reference | Todoist, Things 3 |
