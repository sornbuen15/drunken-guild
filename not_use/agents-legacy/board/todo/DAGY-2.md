---
title: Enforce Global .gitignore Policies for Edge and Backend Secrets
priority: HIGH
assigned_to: "@security-engineer"
---
# Security Vulnerability Prevention
Audit all `.gitignore` files globally to ensure `*.env`, `.env`, `.env.*`, and `*config.json` (where secrets are stored) are firmly ignored. We found that the main project root lacked `.env` protection. This needs to be checked across all backend microservices, edge clients, and agent repos.
