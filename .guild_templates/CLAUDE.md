# Drunken-Team Instructions for Claude Code

When working in this repository, follow these core directives:

## 1. Interaction with Guild AI (Jira) & Memory
You are part of an AI Guild Platform.
- **Context Handoff:** Always read `SESSION_CHECKPOINT.md` at the start of your session. Update it before finishing your task.
- You MUST NOT push code to the `main` branch directly.
- Use `python3 scripts/jira_bridge.py get-todo` (or connect to MCP `uv run drunken-mcp`) to identify your next task.
- Branch off using the format `feature/<TICKET-ID>`.
- When work is done and tests pass, commit with `<TICKET-ID>: <message>`, push your branch, open a PR, and alert the QA Agent.

## 2. Guardrails (Safety & Approvals)
- **Destructive Operations:** You are strictly forbidden from running destructive shell commands (like `rm -rf`) without explicit Boss approval.
- If you need to delete files or if you encounter a blocked state, run `python3 scripts/ask_boss.py "Your Question Here"` to send an approval request to Discord. Block and wait for exit code `0` before proceeding.

## 3. Code Quality (100% Quality)
- **Zero-Defect:** Run `pytest` and ensure tests cover exceptions/errors, not just happy paths.
- **Type Checking:** Comply with strict `mypy` typing.
- **Mocking:** Always use `autospec=True` when mocking in tests.
- Run `pre-commit run --all-files` before finalizing your changes.

## 4. Think, Analyze, Differentiate (ค.ว.ย.)
- Do not blindly execute E2E tests, server startups, or commands without checking context, paths, and environment variables.
- Verify logs of background processes. Do not assume a command succeeded if it didn't instantly crash.
- Isolate root causes before applying random fixes.
