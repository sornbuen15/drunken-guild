# Session Checkpoint

This file acts as the short-term memory and context handoff between AI coding sessions.
**AIs must read this file at the start of a session and update it before ending their turn.**

## 1. Current Objective
- Realize the fully autonomous, frictionless "Agentic SDLC V2" pipeline for `drunken-team`.
- Ensure strict Jira (SSOT) workflow adherence: `TODO` -> `IN PROGRESS` -> `IN REVIEW` -> `DONE`. **No exceptions, even for trivial/no-diff tickets.**
- **New hard rule this session:** no ticket/PR is "done" on tests passing alone. A real adversarial code review (not just the author's own tests) is required before merge -- see "Review discipline" in Known Issues. This was learned the hard way: a fix (DT-93's first pass) that made all tests pass still had a live regression, only caught by a second independent review pass.
- **Time pressure context (carried over):** grant funding deadline for `beta` (~/Projects/beta) was ~14 days out as of 2026-07-18. This session ran long and crossed into 2026-07-19. Round-1 is now essentially closed out -- next session should confirm with the Boss whether to start round-2 on drunken-team or pivot to `beta`.

## 2. Completed This Session (2026-07-18 -> 2026-07-19)

### DT-67: Discord approval daemon -- full rewrite (was previously closed prematurely, reopened and actually finished)
The old "Silent Wait Protocol" (agent writes JSON to `.agents/discord_outbox.json`, calls `schedule`, ends its turn, hopes to be woken later) is retired. Replaced with a real persistent daemon:
- **New `src/service/approval_manager.py`**: `ApprovalManager` state machine. `request_boss_approval` now genuinely blocks (Unix socket IPC, `src/service/discord_listener.py` runs the server) until the Boss reacts, or 2 unanswered 15-min reminders trigger auto-escalation (scoped task kill, Jira comment **without closing the ticket**, Discord notification, task-generation-checked so it never kills an unrelated task).
- **`.mcp.json` created at project root** -- there was previously no working MCP registration anywhere in this repo; confirmed live and working in a real Claude Code session (`request_boss_approval`/`jira_*` tools showed up as usable MCP tools mid-session).
- **`scripts/setup_daemon_service.py`**: macOS launchd LaunchAgent for 24/7 local persistence. Installed and running (`com.drunkenteam.agy-daemon`). Two real bugs found and fixed only by actually running it: launchd resolves `ProgramArguments[0]` via its own minimal PATH (not the plist's `EnvironmentVariables`), so a bare `"uv"` silently failed with exit 78 -- needed an absolute path; and escalated snapshot entries were never cleared, so every daemon restart re-escalated the same request (duplicate Jira comments/Discord messages) -- fixed.
- **Pre-commit safety net**: `scripts/check_pending_approval.py` blocks commits on a ticket with an unresolved approval (warn-only if daemon unreachable).
- Fixed `pyproject.toml`'s `requires-python` (was `>=3.8`, `mcp` needs `>=3.10` -- this was silently breaking `uv run`/`uv sync` for the whole project). `uv.lock` now committed (excluded from the large-file pre-commit check, not the size ceiling raised for everything).
- **Two full adversarial-review rounds** (8-angle diff scan + independent verification of every candidate, not just the author's own read) found **15 + 2 more confirmed bugs** across the daemon and the QA gate (wrong-task-kill on escalation, reconnect race causing duplicate messages, event-loop-blocking I/O, orphaned-process handling via a PID registry, unanchored ticket-PR substring matching risking merging the wrong PR, and more). All fixed, all independently re-verified, all with regression tests. Full list in commit `6d0117d`.
- Live-tested end-to-end against the real Discord bot + Jira after every round of fixes, not just unit tests.
- Landed via PR **#55** (closed **#54** to restart review clean -- it had bundled two unrelated bodies of work confusingly) and follow-up **#57**, **#58**. All merged to `develop`.

### DT-93: validated the round-integration QA gate against a real PR -- found 2 more real bugs
Built a disposable scratch ticket (DT-129, later marked Done by the automation, kept as historical record) + scratch PR (#56, closed unmerged) and ran the **actual, unmodified** `scripts/qa_automation.py` end-to-end (only the `gh pr review` call was no-op'd -- GitHub does not allow a PR's author to approve/request-changes their own PR, and since PRs here are opened via the Boss's own `gh` auth, self-review is structurally impossible, not a bug).
- **First run found a real bug**: `run_tests()` called bare `ruff`/`mypy`/`pytest` (whatever's on the runner's PATH), while `.pre-commit-config.yaml`'s ruff was still pinned to the ancient `v0.1.6` -- disagreeing with the modern version (0.15.20) everything else resolves to, causing the two to flip-flop the same import-order edits back and forth on every commit. Fixed: `run_tests()` now uses `uv run`; pre-commit's ruff pin bumped to match (PR #57).
- **A follow-up review of that fix found a second real bug** (regression introduced by the fix itself): `uv run` requires resolving the branch's own environment first. `review_issue()` checks out each ticket's branch in isolation -- a branch cut before the `pyproject.toml`/`uv.lock` fix (confirmed: DT-41, DT-42, DT-43, DT-44, DT-68 all still predate it) can't resolve at all, and that was getting reported as `"Pytest failed"`, wrongly blaming the ticket's code for a stale-branch/tooling problem. Fixed and distinguished in the report message (PR #58).
- **Known, not fixed (lower priority, documented in the PR #58 description)**: `scripts/qa_automation.py` and `src/service/discord_runner.py` still shell out to bare `python scripts/jira_bridge.py` in several places -- same PATH-resolution risk class, but lower actual severity since `jira_bridge.py` only uses stdlib, no pinned third-party deps.
- DT-93 closed Done with the full validation writeup as a Jira comment.

### Branch protection / process changes
- `develop`'s branch protection `required_approving_review_count` was lowered from 1 to **0** by the Boss directly (Claude Code's safety layer correctly refused to make this change itself even with explicit consent -- flagged as "should be suggested to the user to perform themselves"). Reason: GitHub structurally disallows a PR author from approving their own PR, and since every PR this session was opened via the Boss's own `gh` auth, the review requirement was an unsatisfiable deadlock for a solo-authored repo. **`enforce_admins` is still `true`** (unchanged) -- direct pushes to `develop` are still blocked regardless.
- Established pattern for future sessions: open PR -> ask the Boss explicitly before merging, every single time, even though the technical gate is now 0-review. Merging is never a standing permission from one "yes."

## 3. Current Round ("round-1") -- Jira label `round-1`
| Key | Status | What |
|---|---|---|
| DT-89 | Done | (carried over, unchanged) |
| DT-91 | Done | (carried over, unchanged) |
| DT-92 | Done | (carried over, unchanged) |
| DT-67 | **Done** | Discord approval daemon, fully rewritten and live-verified this session (see above) |
| DT-93 | **Done** | QA round-integration gate validated against a real PR, 2 real bugs found and fixed (see above) |
| DT-94 | In Progress | **Still not started this session.** Credential/.env-dev prerequisite was already done. The actual decision + implementation of re-enabling Discord task-commanding (`_dispatch_swarm` in `src/service/discord_router.py`) needs Boss scoping conversation first. Also now has a concrete new blocker to check: whether the external `agy` binary actually reads this repo's `.mcp.json` the same way stock `claude` does -- unverified, can't be tested until Discord dispatch is re-enabled. |
| DT-90 | To Do | Reconcile `Drunken-Team-Guide.md`/`README.md` with reality. **Not started this session** -- and there's now more to reconcile than before (new daemon architecture, `.mcp.json`, launchd setup all need documenting). Still partially blocked on DT-94 for the Discord-commanding wording. |

Backlog (label-less, not this round): **DT-95** -- token/cost tracking tech debt, still deferred.

## 4. Pending / Next Steps
1. Round-1 is now down to just **DT-94** (needs a Boss scoping conversation, not more solo coding) and **DT-90** (docs reconciliation -- straightforward, can be picked up directly). Ask the Boss which first, or whether to start round-2 / pivot to `beta`.
2. The Discord approval daemon is live and running (`launchctl list com.drunkenteam.agy-daemon` to check). If it's ever not running, `python scripts/setup_daemon_service.py install` re-installs it; `status`/`uninstall` also available.
3. Nothing is currently open/unmerged -- PRs #55, #57, #58 all merged to `develop`. #54 and #56 closed (superseded/scratch).

## 5. Known Issues & Context
- **Review discipline (new, important):** tests passing is necessary but not sufficient. Every non-trivial change this session that skipped an independent adversarial review (not just the author's own tests) turned out to have a real bug, twice in a row (the DT-93 uv-run fix, then its own regression). Going forward: run a real review pass (8-angle diff scan + independent verification, see this session's PR #55/#57/#58 for the pattern) before considering anything done, proportional to the size of the change -- not just for the big stuff.
- **Self-approval / self-merge structural limit:** since PRs are opened via the Boss's own `gh` auth, the agent can never satisfy a "requires approval" gate on its own PRs, and running automation (like `qa_automation.py`'s `gh pr review`) against a PR the agent itself opened is also blocked as a self-approval conflict. Both are expected, not bugs to work around.
- **`.env-dev` is still temporary** (carried over from last session, unchanged this session -- still worth folding into `.env` eventually).
- **Discord task-commanding is still disabled by design**, pending DT-94 (carried over, unchanged).
- **Dashboard is still intentionally gone** (carried over, unchanged).
- **`GITHUB_MINABOT`, Jira team-managed-project findings, branch strategy** -- all carried over from last session, unchanged, see git history of this file if needed.
