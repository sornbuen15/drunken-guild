# Drunken Agy: Software Development Workflow Guide

Welcome to the Drunken-Agy project! This repository relies on an advanced, highly-automated agentic software development lifecycle (SDLC). To prevent data fragmentation (split-brain) and maintain a stable codebase, all human developers and AI Agents MUST strictly adhere to the following Single Source of Truth (SSOT) protocols.

---

## 1. Task Management: Jira is the Single Source of Truth (SSOT)

We **do not** use local Markdown files (`.agents/board/*.md`) or the `kanban-board` MCP to track task status.

- **Intake & Backlog:** All new features, bugs, and ideas must be created as a Jira Ticket.
- **Workflow Lanes:** Issues flow through standard Jira columns: `Backlog` -> `Selected for Development` (To Do) -> `In Progress` -> `Done`.
- **Agent Routine:** Upon waking up, agents will automatically execute a daily standup routine. They will use `scripts/jira_bridge.py get-in-progress` and `get-todo` to connect directly to the Atlassian Jira Cloud API.
- **Command:** Never manually manipulate local task files. If you need to check task status, rely on the Jira web board or use `scripts/jira_bridge.py`.

---

## 2. Documentation: Git Repo is the SSOT (Synced to Confluence)

Documentation lives alongside the code. We do not edit documentation directly on Confluence.

- **Local Edits:** All technical documentation (e.g., `README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md`) must be authored and edited as standard Markdown files in this repository.
- **Confluence Sync:** We maintain a bridge to Atlassian Confluence. Once a Markdown document is updated and merged into `main`, you must trigger the sync.
- **Command:** Agents and developers can run `/confluence-sync` (which uses `scripts/confluence_bridge.py push`) to automatically convert and push the latest Markdown content to the project's Confluence Space.

---

## 3. Git Protocol: Branching, PRs, and Safety Gates

Direct commits to the `main` or `develop` branches are strictly prohibited. 

- **Feature Branches:** All work must take place on a dedicated branch (e.g., `feature/workflow-guide` or `bugfix/DAGY-1`).
- **Pull Requests (PR):** When work is completed (and integration tests pass), you must open a Pull Request against `main`.
- **Merge Authorization Gate:** **Agents are strictly forbidden from merging PRs autonomously without explicit human oversight.** 
  - Before a merge, the Agent will ask: *"Will you review and merge this PR yourself, or do you want me (AGY) to merge it for you?"*
  - If instructed to auto-merge, the Agent will issue a final **Warning** about the risks of unverified code breaking the build.
- **Release and Tagging:** Once a feature or bugfix is successfully merged into `main`, a Semantic Git Tag (e.g., `v1.3.0`) MUST be generated. 
- **Release Notes:** Use the `release-notes-writer` standard to generate a Markdown table comprising an Executive Summary, Changelog (Features/Fixes/Deprecations), and Migration Warnings. Publish this via GitHub Releases (`gh release create`).

---

By adhering to this guide, both human developers and autonomous AI agents can safely co-pilot the development of the Drunken-Agy architecture without stepping on each other's toes.
