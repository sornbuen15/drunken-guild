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

## Away mode — the other layer that asks (DT-236)

Everything above is the agent deciding it needs permission. The **harness** also asks, before the
model runs at all: *"Allow this tool call?"* The model never sees that one, which is why saying
"I'm going out, send it to Discord" in chat never worked and never could.

`drunken-away` is the switch that reaches the machine:

```bash
uv run drunken-away on --note "out until 6"   # prompts go to Discord
uv run drunken-away off                       # back to the terminal
uv run drunken-away status
```

With it on, the PreToolUse hook resolves each call in this order, and the order is the design:

1. **On the deny list → denied.** It never reaches Discord. A 👍 cannot authorise `rm -rf`.
2. `bypassPermissions` mode, or an approval tool → no decision. Asking for permission must not
   itself need permission.
3. **On the allow list → no decision**, not `allow`. The hook never *widens* permission; the
   harness's own list already covers it.
4. Not away → no decision. The terminal prompt is the better interface when you are at it.
5. Otherwise → ask on Discord, wait, and map 👍/👎 onto allow/deny.

Things worth knowing before you turn it on:

- **A timed-out hook does not block the call** — it falls through to the normal permission flow. So
  the hook answers *before* its own deadline (`WAIT_BUDGET_SECONDS`, 25 min) rather than waiting to
  be killed at the `timeout` in `.claude/settings.json` (30 min). A test asserts the gap; do not
  change one number without the other.
- **`uv run drunken-away off` is allowlisted on purpose.** Away mode routes everything else,
  including the command that would switch it off — found the hard way during DT-236's acceptance
  run, with the agent stranded. Do not remove that rule.
- **It is noisy by design.** Anything not on the allow list becomes a Discord question, `Edit` and
  `Write` included. If that is too much for a long unattended run, widen the allow list deliberately
  rather than reaching for `bypassPermissions`.

## Things that will bite you

- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal.
  gitleaks scans full history and `.env` is deliberately not allowlisted.
- **Never let import-time failure be a failure mode.** Anything that can fail must fail inside a tool
  call, so the caller reads a message instead of watching a server vanish. Use `core/errors.py` —
  every error carries a remediation, because "unknown project 'alpha'" only tells an agent to give up.
- **An agent does not delete.** Boss's standing rule. Anything that would need a recursive
  force-delete becomes a **list handed to the Boss to run**, and *marking a thing unused beats
  removing it*. A recorded authorisation from an earlier session is not permission to delete today —
  the vendored-tooling teardown was authorised weeks before anyone noticed that ALPHA's copies sit
  outside any git repository. See §10.6 of the checkpoint.
- **Do not touch `.agents/` state files or `~/.gemini/antigravity-cli/brain/*/worktrees/`.** Those
  belong to Antigravity. `.agents/skills/` is tracked and editable; the rest is not yours.
- **Every outbound HTTP call goes through `core/http.py`.** One `# nosec`, on the guard itself.
- Antigravity reviews and runs client-side acceptance tests. It does **not** edit this repo's source
  while security work is in flight.

## The board

`.mcp.json` declares all three servers, `drunken-board-mcp` included since DT-242. The board tools
work from inside this project — `board_summary` answers, and the `blocked` lane and
`board_available_tasks` from DT-233 are callable.

Board state lives in `.agents/board/<lane>/`, so **the cards are Antigravity's and you do not edit
them by hand.** Go through the tools. `.claude/board/` is preferred when it exists; today it does
not, and the resolver falls back to `.agents/board/`.
