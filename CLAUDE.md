# Drunken-Team Guidelines for Claude Code

This file (`CLAUDE.md`) is automatically loaded by the **Claude Code CLI** to provide project-specific instructions and command shortcuts.

## Build & Test Commands
- Install dependencies: `python -m pip install -e .[dev]`
- Run tests: `pytest tests/`

## Workflow Directives (CRITICAL)
1. **Jira is the Single Source of Truth for Tasks:**
   - You MUST NOT guess your next task.
   - To find your next task, run: `python scripts/jira_bridge.py get-todo`
   - When you start working, transition it: `python scripts/jira_bridge.py transition <ISSUE_KEY> "In Progress"`
   - When finished and PR is merged, transition it: `python scripts/jira_bridge.py transition <ISSUE_KEY> "Done"`

2. **Documentation is Repo-First:**
   - Do not edit Confluence directly.
   - Edit Markdown files locally in this repository.
   - After merging documentation changes to `main`, run: `python scripts/confluence_bridge.py push "Page Title" FILENAME.md`

3. **Git & PR Protocol:**
   - Never push directly to `main`.
   - Always create a `feature/*` or `bugfix/*` branch.
   - Create a PR via `gh pr create` and request human approval before merging.
