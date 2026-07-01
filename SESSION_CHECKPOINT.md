# Session Checkpoint

This file acts as the short-term memory and context handoff between AI coding sessions.
**AIs must read this file at the start of a session and update it before ending their turn.**

## 1. Current Objective
- Build and refine the "AI Guild Platform" for `drunken-team`.
- Expose Jira capabilities and SDLC conventions to Local AI tools.

## 2. Completed in Last Session
- Restructured documentation (`README.md`, `Drunken-Team-Guide.md`, `Integration-Guide.md`) and translated them to English.
- Isolated Discord listener `SSH_AUTH_SOCK` issues.
- Created `guild_mcp.py` using `FastMCP` exposing `get_jira_todo`, `transition_issue`, `ask_boss`, and `request_qa_review`.
- Created standard templates (`.cursorrules`, `CLAUDE.md`, `.aider.conf.yml`, `CONVENTIONS.md`, `SESSION_CHECKPOINT.md`) for Local AI onboarding.

## 3. Pending / Next Steps
- Scan the entire project for structural integrity.
- Conduct a codebase review (linters, static analysis, technical debt).
- Execute the test suite (`pytest`) to ensure zero defects.

## 4. Known Issues & Context
- Do not push directly to `main` branch. All work goes to `feat/restructure-agents` or other feature branches.
- `scripts/jira_bridge.py` requires `.env` with JIRA credentials.
