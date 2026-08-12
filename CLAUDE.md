# drunken-team — instructions for Claude Code

Loaded automatically by Claude Code. Keep it short enough that it is actually read.

`SESSION_CHECKPOINT.md` is the other half of this: **read it at the start of a session.** It says
what is merged, what only *looks* merged, and what to pick up next. This file says how to work; that
file says where things stand.

## Commands

```bash
uv run pytest -q                    # 2s -- e2e is deselected by default, on purpose
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src                     # --strict via pyproject
./scripts/verify_clean_install.sh   # 22 clean-room checks, touches nothing of yours
```

`pytest -m e2e` runs the tests that talk to **live Jira and file real tickets**. Run it deliberately
or not at all. It is deselected because for months it was not, and it filed 52 junk tickets before
anyone noticed — see §6 of the checkpoint.

`bandit -ll` and `pip-audit --strict` also gate CI; `uvx bandit -ll -q -r src/` runs it locally.

## Jira is the source of truth

`TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW**, including for your own work.

Use the `drunken-jira-mcp` tools (`jira_search_issues`, `jira_start_task`, `jira_transition_issue`,
`jira_submit_for_review`, `jira_add_comment`). `scripts/jira_bridge.py` still exists for shell use,
but the MCP tools are the supported path.

One ticket per phase, and each phase must merge on its own without breaking the one before it.

**A ticket marked IN REVIEW is not merged code.** DT-225 sat in review for weeks while its branch was
never merged and the trunk stayed vulnerable; every surface said it was done. If a ticket claims
something is fixed, verify against `origin/develop` before believing it.

## Git

Work lands on `develop` through a PR. Never push to `main` — `main` is deliberately behind and stays
that way until the current work is finished. Branch as `feature/DT-123-slug`, `bugfix/...`, `chore/...`,
`docs/...`.

Do not stack a PR on another PR's branch: when the base merges and is deleted, GitHub closes the
stacked one. Branch from `develop` and cherry-pick if you need something that has not landed yet.

Pre-commit runs ruff, ruff-format, mypy, and a check that blocks committing while the current
ticket has an unresolved Discord approval. Do not bypass it.

## Tests

**A test for a bug or a security finding must be seen failing first.** A test written after the fix
proves only that it compiles. Say so in the PR when you have done it.

Match the surrounding test style. Assertions carry the reason they exist, not just the expectation.

## Approvals — ask without stopping

Full protocol in `.agents/skills/ask-boss/SKILL.md`; the short version:

- The Boss is reading this conversation → **just ask them here.** Discord is for when they are not.
- Otherwise `request_boss_approval_async(action, reason, ticket_key)`, which returns a `req_id`
  immediately. Park the task, take the next unblocked one, and collect with `check_approvals` **when
  you finish a task or start a session — never mid-task.** Half-applied approvals leave the repo in a
  state nobody can reason about.
- There is no timeout and nothing is killed for going unanswered. Reminders back off 15 min → 1 h →
  daily and survive a daemon restart.
- An approval is bound to the commit it was granted against. From a different HEAD it reads `stale`
  and must be asked again.
- Force-push, hard reset, `rm -rf`, and reading `.env` are denied by `.claude/settings.json`
  **regardless of what comes back over Discord.** Do not route around it; raise it with the Boss.

`request_boss_approval` (blocking) still works and is kept until 3.0.0. Prefer the async pair.

## Things that will bite you

- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal.
  gitleaks scans full history and `.env` is deliberately not allowlisted.
- **Never let import-time failure be a failure mode.** Anything that can fail must fail inside a tool
  call, so the caller reads a message instead of watching a server vanish. Use `core/errors.py` —
  every error carries a remediation, because "unknown project 'twa'" only tells an agent to give up.
- **Do not touch `.agents/` state files or `~/.gemini/antigravity-cli/brain/*/worktrees/`.** Those
  belong to Antigravity. `.agents/skills/` is tracked and editable; the rest is not yours.
- **Every outbound HTTP call goes through `core/http.py`.** One `# nosec`, on the guard itself.
- Antigravity reviews and runs client-side acceptance tests. It does **not** edit this repo's source
  while security work is in flight.

## Known gap

`.mcp.json` declares only `drunken-jira-mcp` and `drunken-discord-mcp`. **`drunken-board-mcp` is not
wired up**, so the board tools — including the `blocked` lane and `board_available_tasks` from
DT-233 — cannot be called from inside this project yet.
