# Session Checkpoint

This file acts as the short-term memory and context handoff between AI coding sessions.
**AIs must read this file at the start of a session and update it before ending their turn.**

## 1. Current Objective
- Realize the fully autonomous, frictionless "Agentic SDLC V2" pipeline for `drunken-team`.
- Ensure strict Jira (SSOT) workflow adherence: `TODO` -> `IN PROGRESS` -> `IN REVIEW` -> `DONE`. **No exceptions, even for trivial/no-diff tickets.**
- **Review discipline (carried over, still binding):** no ticket/PR is "done" on tests passing alone -- see "Known Issues" below.
- **Round-1 is now fully closed** (2026-07-22) -- every ticket under the `round-1` label is Done. **Next session's first job: confirm with the Boss whether to open round-2 on `drunken-team` or pivot to `isac`.** The `isac` grant-funding deadline was ~14 days out as of 2026-07-18; this has now cost 4 calendar days, leaving roughly 10.

## 2. Completed This Session (2026-07-21 -> 2026-07-22)

### DT-94: decided and implemented -- scoped Discord Jira/PR commands, free-text commanding stays disabled
The decision: keep free-form natural-language task-commanding off (cost, latency, and prompt-injection surface of a free-text router weren't worth it), but add a deterministic command set covering the actual day-to-day need instead. Two rounds, both live-verified against the real bot + Jira before merging:
- **Round 1 (read-only, no LLM/agent involved):** `/tasks` `/inprogress` `/review` `/backlog` `/pr` `/pending` -- direct `jira_bridge.py`/`gh` subprocess calls via `sys.executable` (not bare `python`, to dodge the exact daemon-PATH bug class DT-93 found), output capped/truncated to stay under Discord's 2000-char limit.
- **Round 2 (mechanical + one real dispatch):** `/project [name]` (switch target project for the above + `/next`/`/refine`), `/next` (pick up top To Do -> In Progress, refuses if something's already In Progress), `/refine` (auto-promotes Critical backlog issues, reports the rest without auto-acting), `/approve <ticket>` (clears an escalated approval block and re-dispatches via the existing `agent_runner.run_command_async` plumbing -- ack now, truncated reply later, no new blocking path), `/qa` (backgrounds `scripts/qa_automation.py`'s round-integration gate, replies threaded to its own ack message when done).
- Collapsed the free-text (non-slash) fallback to one consistent message; deleted the now-dead `PERSONA_MAPPING`/project-matching code from the pre-disable era.
- **`/qa` has never been live-tested** -- see Known Issues.
- Landed via PR **#60** (`feature/DT-94-discord-commands` -> `develop`). 149 tests, ruff, mypy all clean at merge.

### DT-90: docs reconciled with reality, in English, full project doc scan
- Rewrote `Drunken-Team-Guide.md` and `Integration-Guide.md` end to end: removed the retired "Mina" NL router and the Dashboard from the architecture description, removed every "Silent Wait Protocol" reference (replaced with the real `request_boss_approval`/reactions mechanism from DT-67), fixed the fictional `drunken-mcp` binary and bare-function-name tool calls to the real entrypoints/tool names, bumped the stated Python prereq from 3.8+ to the real 3.10+, documented the full DT-94 command set with worked examples.
- Same "Silent Wait Protocol"/`drunken-mcp` fixes applied to `.guild_templates/CLAUDE.md`, `.cursorrules`, `CONVENTIONS.md` -- these get copied into every newly-integrated project, so they were teaching the wrong protocol going forward.
- Filled in two tools missing from `src/jira_mcp/README.md` (`jira_start_task`, `jira_submit_for_review`) plus a missing resource.
- Scanned the whole repo for stale docs. First pass wrongly moved several `.agents/` files (old duplicate `SESSION_CHECKPOINT.md`, `SPRINT_PLAN.md`, the deprecated local Kanban board, two dated audit snapshots) into `not_use/agents-legacy/` -- this pulled previously-gitignored, never-tracked content into git history for the first time. **Corrected per explicit direction: nothing Antigravity-related gets touched or archived by this project's own hand** (see Known Issues) -- reverted, those files are back at their original `.agents/` paths, still correctly gitignored, untouched.
- Also added `.claude/` to the tracked `.gitignore` (was previously only excluded via this machine's local `.git/info/exclude` -- other clones had no protection).
- Landed via PR **#61** (`feature/DT-90` -> `develop`).

### Full git-history secret audit (before merging either PR)
Swept every commit on every local + remote branch (`git log --all -G<pattern>`) for Atlassian/GitHub/Discord/AWS token shapes and private-key headers, plus filename checks for `.env*`/`jira.json`/`discord_config.json`/`.claude`/`ANTIGRAVITY.md`. **Zero matches anywhere, ever.** Worth re-running this same sweep before any future merge that touches previously-gitignored content.

### Round-1 closeout
DT-94 and DT-90 both manually transitioned to Done with full summary comments after merging -- their feature branches were deleted on merge, so `qa_automation.py`'s round-integration gate (which needs a live branch per ticket) couldn't run against them; this was a reasoned manual closeout, not a skipped gate. **All of round-1 is now Done: DT-89, DT-91, DT-92, DT-67, DT-93, DT-94, DT-90.**

## 3. Round-1 Final Status -- Jira label `round-1`
| Key | Status |
|---|---|
| DT-89 | Done |
| DT-91 | Done |
| DT-92 | Done |
| DT-67 | Done |
| DT-93 | Done |
| DT-94 | **Done** (this session) |
| DT-90 | **Done** (this session) |

Backlog (label-less, not this round): **DT-95** -- token/cost tracking tech debt, still deferred.

The stale "Silent Wait Protocol" string inside `src/jira_mcp/server.py`'s `init_project` MCP prompt (found while auditing docs, scoped out of DT-90 as source code rather than a doc) was fixed by a separate spawned session and merged via **PR #64**. No other stale protocol references remain anywhere tracked (`git grep` confirms -- the only two remaining "Silent Wait Protocol" mentions are `approval_manager.py`'s own docstring and this file, both correctly describing it in the past tense as retired/replaced).

### `.env-dev` folded into `.env`, plus two real onboarding bugs found and fixed
Later the same session, the Boss confirmed all needed vars were already migrated, so `.env-dev` was renamed to `.env` and the transitional fallback removed from all 5 places that had it. Before merging, verified the whole system actually works for a new user by cloning the branch into an isolated directory with zero local state and following the documented setup literally -- this found two real bugs:
- `register_project.py` writes `.agents/jira.json` with a snake_case `project_key` field, but `jira_bridge.py` and `jira_mcp/config.py` both read it back as camelCase `projectKey` -- silently dropped the project key for anyone who registered via `drunken-register` without also setting `JIRA_PROJECT_KEY` as an env var. Reproduced, fixed both readers, reproduced again to confirm resolution. Added regression tests (`tests/test_jira_mcp_config.py`, zero prior coverage of this path). Fixed the matching wrong doc example too.
- `register_project.py`'s success message told users to "start the dashboard" (removed earlier session) -- pointed at the real next step instead.

Also added `.env.example` (every real env var the project reads, `.gitignore` negation so it's actually trackable) since previously there was only inline markdown, no copyable template. Re-audited the full git history across all branches for leaked secrets after every change this session -- clean throughout, including after these last fixes.

Landed via **PR #63** (`chore/fold-env-dev-into-env` -> `develop`).

## 4. Pending / Next Steps
1. **Decide round-2 vs. `isac` pivot** -- round-1 has no open tickets left. This is the first thing to raise with the Boss.
2. **`/qa` has never been live-tested.** Every other Discord command (round 1 + round 2) was verified against the real bot; `/qa` does real `git checkout`/merge/branch-delete operations on the working tree, so it needs a ticket that's In Review with a genuinely open, unmerged PR to test meaningfully (DT-94/DT-90 no longer qualify -- their branches are gone). Follow DT-93's own precedent: a disposable scratch ticket + scratch PR, not a live one.
3. **The running Discord daemon (PID checked at ~08:57 this session) predates PRs #63/#64/#65** -- confirmed harmless (the credential/protocol changes only affect fresh process starts, not already-loaded `os.environ` state), but it is not literally running the same bytes as `develop`'s HEAD. Restart it to true up: `launchctl kickstart -k gui/$(id -u)/com.drunkenteam.agy-daemon` (`launchctl list com.drunkenteam.agy-daemon` to check status first) -- this exact command has been blocked by the auto-mode permission classifier before, so the Boss may need to run it manually.
4. **No Jira ticket exists for the PR #63/#64 work** (the `project_key` bug, `.env.example`, the `register_project.py` message fix, the `jira_mcp` protocol fix) -- all of it surfaced organically during a pre-merge verification pass rather than from a planned backlog item. Ask the Boss whether it's worth a retroactive ticket for the record, given the project's Jira-SSOT discipline, or fine to leave as git-history-only.
5. Nothing is currently open/unmerged -- PRs #60, #61, #63, #64 (from a separate spawned session), and #65 all merged to `develop`. Full suite (152 tests)/ruff/mypy clean on `develop` as of this checkpoint.

## 5. Known Issues & Context
- **Review discipline:** tests passing is necessary but not sufficient -- see this session's `.agents/`-tracking mistake (caught and corrected only because the Boss questioned it, not because of a test) and prior sessions' DT-93 regression-in-the-fix. Keep treating "it passed CI" as a floor, not a ceiling.
- **Never touch anything Antigravity-related (new, important):** don't clean up, delete, or move-to-`not_use/` any Antigravity git worktrees (`~/.gemini/antigravity-cli/brain/*/worktrees/`), `subagent-*`/`feature/DT-4x`-era branches tied to old Antigravity subagent runs, or `.agents/` content that documents Antigravity-specific behavior -- even when it looks like abandoned cruft in a project-hygiene scan. The Boss's stated plan is a future multi-agent setup running both Claude Code and Antigravity side by side; this is deliberately preserved groundwork, not debris. If genuinely unsure whether something is Antigravity-infrastructure-relevant, ask before touching it.
- **Self-approval / self-merge structural limit:** unchanged from prior sessions -- PRs are opened via the Boss's own `gh` auth, so the agent can never satisfy a "requires approval" gate on its own PRs, and `qa_automation.py`'s `gh pr review` step is a no-op against a PR the agent itself opened. Expected, not a bug.
- **`.env-dev` has been folded into `.env`** (later the same session, once the Boss confirmed all needed vars were already migrated) -- `.env-dev` renamed to `.env`, and the transitional fallback removed from all 5 places that had it (`jira_bridge.py`, `confluence_bridge.py`, `discord_utils.py` x2, `jira_mcp/config.py`, plus one test comment). `load_dotenv()` everywhere now just checks `.env`.
- **Old Antigravity-era git worktrees/branches** (`feature/DT-41`..`DT-44`, `subagent-*-self-*`) are still registered locally under `~/.gemini/antigravity-cli/brain/*/worktrees/` -- explicitly left alone per the policy above, not cleanup debt.
- **Dashboard is still intentionally gone** (carried over, unchanged).
- **`GITHUB_MINABOT`, Jira team-managed-project findings, branch strategy** -- all carried over from earlier sessions, unchanged, see git history of this file if needed.
