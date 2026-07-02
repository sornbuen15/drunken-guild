# Session Checkpoint

This file acts as the short-term memory and context handoff between AI coding sessions.
**AIs must read this file at the start of a session and update it before ending their turn.**

## 1. Current Objective
- Build and refine the "AI Guild Platform" for `drunken-team`.
- Establish Discord as the universal **Remote Control** for Agents, following the headless architecture defined in `Planv2.md`.

## 2. Completed in Last Session
- Restructured documentation (`README.md`, `Drunken-Team-Guide.md`, `Integration-Guide.md`) and translated them to English.
- Isolated Discord listener `SSH_AUTH_SOCK` issues.
- Created `guild_mcp.py` using `FastMCP` exposing `get_jira_todo`, `transition_issue`. (Removed `ask_boss` and `request_qa_review` as they violate async architecture).
- Created standard templates (`.cursorrules`, `CLAUDE.md`, `.aider.conf.yml`, `CONVENTIONS.md`, `SESSION_CHECKPOINT.md`) for Local AI onboarding.
- Fixed Ruff Config in `pyproject.toml` and cleared Technical Debt (`C901` in `serve_dashboard.py`).
- Implemented TDD: added `test_guild_mcp.py` utilizing `autospec=True`, boosting test coverage to >25% (Zero-Defect Pipeline).
- **Architecture Correction:** Clarified that the Discord bot spawns Agents in the background (headless) rather than inside the IDE UI. Created `Planv2.md` to document the exact Remote Control workflow using `discord_outbox.json` / `discord_inbox.json`.
- **Executed Plan v2:** Implemented the Outbox/Inbox watcher inside the Discord Bot to facilitate the "Silent Wait Protocol".
- Tested the full End-to-End Remote Control loop: Agent asks for permission (Outbox) -> Discord Bot sends to Boss -> Boss reacts (👍) -> Bot writes Inbox -> Agent resumes.
- Extended test coverage to reach 88% for `discord_listener.py`.

## 3. Pending / Next Steps
- Finalize Jira JQL Builder logic.
- Extend test coverage for `serve_dashboard.py` to reach 50%.

## 4. Known Issues & Context
- Do not push directly to `main` branch. All work goes to `feat/restructure-agents` or other feature branches.
- `scripts/jira_bridge.py` requires `.env` with JIRA credentials.
- **UI Expectation:** Background Agents spawned by Discord will NOT display their logs in the active Antigravity IDE UI. This is by design (Headless Remote Control).
