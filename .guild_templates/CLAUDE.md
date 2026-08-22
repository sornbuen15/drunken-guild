# Drunken-Guild Instructions for Claude Code

When working in this repository, follow these core directives:

## 1. Interaction with Guild AI (Jira) & Memory
You are part of an AI Guild Platform.
- **Context Handoff:** Always read `SESSION_CHECKPOINT.md` at the start of your session. Update it before finishing your task.
- You MUST NOT push code to the `main` branch directly.
- Use `python3 scripts/jira_bridge.py get-todo` (or the `jira_search_issues`/`jira_start_task` tools from the `drunken-jira-mcp` MCP server) to identify your next task.
- Branch off using the format `feature/<TICKET-ID>`.
- When work is done and tests pass, commit with `<TICKET-ID>: <message>`, push your branch, open a PR, and alert the QA Agent.

## 2. Guardrails (Safety & Approvals)
- **Destructive Operations:** You are strictly forbidden from running destructive shell commands (like `rm -rf`) without explicit Boss approval.
- If you need to delete files or you hit a blocked state: **if the Boss is reading the conversation, just ask them there.** Discord is for when they are not.
- Otherwise call `request_boss_approval_async` (from `drunken-discord-mcp`) with `action`, `reason`, and `ticket_key`. It returns a `req_id` immediately, not an answer. Park the task with `board_block_task`, take the next unblocked one, and collect the verdict with `check_approvals` **when you finish a task or start a session -- never mid-task.** Asking must never stop the other work, and a half-applied approval leaves the repo in a state nobody can reason about.
- There is no timeout and nothing is killed for going unanswered. An approval is bound to the commit it was granted against; from a different HEAD it reads `stale` and must be asked again.
- Do not poll daemon state files, do not use `schedule`, do not end your turn to wait.

## 3. Code Quality (100% Quality)
- **Zero-Defect:** Run `pytest` and ensure tests cover exceptions/errors, not just happy paths.
- **Type Checking:** Comply with strict `mypy` typing.
- **Mocking:** Always use `autospec=True` when mocking in tests.
- Run `pre-commit run --all-files` before finalizing your changes.

## 4. Think, Analyze, Differentiate (ค.ว.ย.)
- Do not blindly execute E2E tests, server startups, or commands without checking context, paths, and environment variables.
- Verify logs of background processes. Do not assume a command succeeded if it didn't instantly crash.
- Isolate root causes before applying random fixes.
