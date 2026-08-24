# Drunken-Guild Conventions for Aider

These are the strict coding conventions for Drunken-Guild that Aider must follow:

## Workflow & Git
1. **Never commit directly to `main`:** You must create a feature branch (`feature/<ISSUE_KEY>`).
2. **Commit Messages:** Every commit message must start with the Jira Issue Key (e.g., `[DG-123] Fix authentication issue`).
3. **No destructive commands:** Do not delete files or directories without explicit permission.

## Testing & Quality
1. **Zero-Defect Pipeline:** Tests (`pytest`) are mandatory.
2. **Mocking:** All `mocker.patch()` and `MagicMock()` calls must include `autospec=True`.
3. **Typing:** Strict Python type annotations (`mypy`) are required everywhere. No missing method calls.
4. **Error Handling:** Centralize error handling. Do not swallow exceptions silently. Return UX-friendly JSON messages.

## Integration with Guild & Memory
1. **Context Handoff:** Always read `SESSION_CHECKPOINT.md` at the start of your session. Update it before finishing your task.
2. Always base your work on tasks assigned from the Guild (via Jira).
2. When completing work, you are expected to stop, push the branch, and let the user open a Pull Request.
3. If an issue requires Boss approval and the Boss is reading the conversation, ask them there. Otherwise call `request_boss_approval_async` (`drunken-discord-mcp`) with `action`, `reason`, and `ticket_key` -- it returns a `req_id` immediately rather than an answer. Don't perform the action yet, carry on with something unblocked (there is no local board, so "parking" a task is just not doing that step), and collect the verdict with `check_approvals` when you finish a task or start a session, never mid-task.
