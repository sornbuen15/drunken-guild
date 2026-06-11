---
id: TASK-005
type: infrastructure
phase: 1
priority: HIGH
title: Set up CI/CD pipeline
assigned_to: "@devops-engineer"
depends_on: [TASK-001, TASK-002]
blocks: []
source: "PROJECT_SPEC.md §4.1 — CI/CD and Deployment"
---

## Objective
Set up a GitHub Actions pipeline that runs tests, enforces code quality gates, and deploys the backend API to AWS ECS on every merge to `main`.

## Context
- Spec §4.1: Automated deployment is required before any release can happen safely.
- Secrets must never be hardcoded — injected via GitHub Actions secrets only.

## Acceptance Criteria
- [ ] **`.github/workflows/ci.yml`** — pipeline definition
- [ ] Pipeline triggers on every push to `main` and on every pull request
- [ ] Steps: lint → unit tests → integration tests → build Docker image → push to ECR → deploy to ECS
- [ ] Pipeline fails and blocks merge if any step exits non-zero
- [ ] All secrets injected via GitHub Actions secrets — never hardcoded
- [ ] Deployment is zero-downtime (ECS rolling update)
- [ ] Pipeline run time < 5 minutes for a clean build
- [ ] Full test suite green
