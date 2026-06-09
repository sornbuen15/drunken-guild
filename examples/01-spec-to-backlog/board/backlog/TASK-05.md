---
Phase: Phase 1 — MVP
Priority: HIGH
---

# TASK-05: CI/CD Pipeline

## Objective
Set up a GitHub Actions pipeline that runs tests, enforces code quality gates, and deploys the backend API to AWS ECS on every merge to `main`.

## Acceptance Criteria
- [ ] Pipeline triggers on every push to `main` and on every pull request
- [ ] Steps: lint → unit tests → integration tests → build Docker image → push to ECR → deploy to ECS
- [ ] Pipeline fails and blocks merge if any test or lint step exits non-zero
- [ ] Secrets (DB connection string, JWT secret, AWS credentials) are injected via GitHub Actions secrets — never hardcoded
- [ ] Deployment is zero-downtime (ECS rolling update)
- [ ] Pipeline run time < 5 minutes for a clean build
