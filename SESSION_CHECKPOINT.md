# Session Checkpoint

This file acts as the short-term memory and context handoff between AI coding sessions.
**AIs must read this file at the start of a session and update it before ending their turn.**

## 1. Current Objective
- Realize the fully autonomous, frictionless "Agentic SDLC V2" pipeline for `drunken-team`.
- Ensure strict Jira (SSOT) workflow adherence: `TODO` -> `IN PROGRESS` -> `IN REVIEW` -> `DONE`. **No exceptions, even for trivial/no-diff tickets** -- this was violated once this session (DT-65) and is now a hard rule (see memory `feedback_workflow_discipline`).
- Implement End-to-End automated testing and validation gates involving the Boss (via Discord) and QA agents.
- **Time pressure context:** The Boss has ~14 days (as of 2026-07-18) until a grant funding deadline for a separate project, `beta` (~/Projects/beta). Goal is to close out `drunken-team` housekeeping within days, then pivot fully to getting `beta` demo-ready. Do not scope-creep on `drunken-team` beyond what's already tracked in the round-1 backlog below.

## 2. Completed This Session (2026-07-18)
- **DT-65 closed:** FastMCP decorator typing tech debt -- `# type: ignore[misc]` workaround confirmed already applied everywhere in `src/`, `mypy src/` verified clean. (Note: this was mistakenly transitioned To Do -> Done directly, skipping In Progress/In Review -- documented as an accepted one-off exception, not to be repeated.)
- **Jira backlog cleanup (deleted for real, not just transitioned):**
  - DT-51..DT-63: unrelated "ALPHA localhost:8080" hotfix cascade + duplicate ticket, nothing to do with this project.
  - DT-41..DT-44: content was actually about `beta` (WebSocket telemetry, Raspberry Pi module, multi-tenant DB, device subscription) mistakenly tracked under drunken-team's Jira project. Branches for these were also deleted (never merged anywhere).
  - DT-68: superseded duplicate of DT-74 (QA Validation Loop) -- closed as Done with an explanatory comment, its stale branch deleted.
- **`scripts/jira_bridge.py` gained several new actions** (none existed before this session except transition/create/get-*): `delete`, `comment`, `label`, `get-by-label`. Also fixed `get-backlog`, which queried a Jira status (`'Backlog'`) that doesn't exist in this project's workflow (see "Known Issues" below) -- it's now `status != Done AND labels is EMPTY`.
- **`scripts/qa_automation.py` rewritten** to add a round-level integration gate: every ticket that passes its own isolated QA run now gets merged onto a shared scratch branch with the rest of the round, the full suite (pytest/ruff/mypy) reruns against the combination, and a ticket only reaches Jira `Done` if that combined run passes. A round report (per-ticket result + integration verdict) is posted as a Jira comment either way. **This has only been type/lint-checked, never exercised against a real open PR** -- that's DT-93, still pending.
- **Git branch cleanup:** deleted 15 stale/merged/dead remote branches (`feat/DT-11...`, `feat/DT-45...`, `feature/DT-64`, `refactor/cleanup`, `feature/DT-41..44`, `feature/DT-68`, `feature/phase-1-completion`, `feature/phase-1-completion-v2`). Verified via git history each was either already merged or a genuinely abandoned dead-end fork before deleting (full analysis: v1 phase-1-completion forked before v2, v2 continued and merged into `main` via PR#32; v1's own 4 unique commits were never carried forward and are all superseded by later work -- nothing was lost).
- **Process/safety fixes:**
  - Fixed a workflow violation: this session accidentally committed directly to `develop` once -- caught, the commit was moved onto a proper feature branch (`feature/DT-65-qa-round-integration-gate`) and PR **#54** was opened instead (still open, unmerged, awaiting Boss review -- do NOT self-merge).
  - Enabled `enforce_admins` on the `develop` branch protection rule (was `false`, meaning admin tokens could bypass the PR-only requirement -- this is exactly how the accidental direct commit above happened).
  - Discovered `.gitignore` didn't cover the `.env-dev` filename pattern (only `.env`/`.env.*`) -- added `.env-*` before any secret could leak into git.
- **Credential/env migration started (DT-94, partial):** Created `.env-dev` (gitignored) as a transitional credential file, sourced from existing scattered configs (`~/.gemini/config/jira_config.json`, `.agents/discord_config.json`, `~/.gemini/config/gemini_config.json`, `gh auth token`). Updated all 4 duplicated `load_dotenv()` implementations (`jira_bridge.py`, `jira_mcp/config.py`, `discord_utils.py`, `confluence_bridge.py`) to check `.env-dev` before `.env`. All 9 needed keys confirmed filled (JIRA_URL/EMAIL/TOKEN/PROJECT_KEY, DISCORD_BOT_TOKEN/CHANNEL_ID, GEMINI_API_KEY, GITHUB_PERSONAL_ACCESS_TOKEN, CONFLUENCE_EMAIL). `GITHUB_MINABOT` was removed -- confirmed not needed (optional, only consumed by the currently-disabled `_dispatch_swarm`). **`.env-dev` is transitional and will be collapsed into a plain `.env` once fully confirmed working -- don't build anything that assumes `.env-dev` is permanent.** Investigation found NO actual 1Password CLI calls anywhere in the active codebase -- the "fingerprint scan" the Boss experienced is believed to come from their personal `~/.zshrc`, outside this repo.
- **Jira project structure findings (important, don't re-litigate):**
  - This Jira project (`DT`) is a **team-managed ("next-gen") project**. It has NO native "Backlog" status (only To Do / In Progress / In Review / Done exist for every issue type), and there is **no public REST API to move issues between the Board and Backlog panel**, nor to add new workflow statuses. Both were tested directly (rank API, `/rest/agile/1.0/backlog/{id}/issue`, `/rest/api/3/workflows`) and confirmed unsupported for this project type. Don't waste time re-trying this.
  - Because of the above, "which tickets are this round's active focus" is tracked via a **Jira label**, not Jira's native Board/Backlog feature. Convention: label a ticket `round-1` (or `round-2`, etc. for the next round) to mark it in-focus. `jira_bridge.py get-by-label <label>` queries it; `jira_bridge.py get-backlog` returns everything else (status != Done, no round label).
- **Two new persistent memory files saved** (`~/.claude/projects/.../memory/`): `feedback_workflow_discipline.md` (never skip In Review; round-level integration test + report required before Done) and `project_drunken_team_goal.md` (the three-pillar SDLC goal, for context in future sessions).

## 3. Current Round ("round-1") -- Jira label `round-1`
| Key | Status | What |
|---|---|---|
| DT-89 | **Done** | Enforce `enforce_admins` on develop branch protection |
| DT-91 | **Done** | Delete stale branches (phase-1-completion, -v2, DT-68) |
| DT-92 | **Done** | Findings: no working agent-dispatch-to-other-project mechanism exists at all (Discord path disabled, no CLI equivalent ever built) -- manual `cd` + open a session in the target project is the only way right now, which is sufficient for beta work |
| DT-94 | **In Progress** | Credential/.env-dev prerequisite done (see above). The actual decision + implementation of re-enabling Discord task-commanding (`_dispatch_swarm` in `src/service/discord_router.py`) has **not** been started -- Boss wants to discuss scope/capabilities before implementing. Direction so far: yes, re-enable it eventually. |
| DT-93 | To Do | Validate the new `qa_automation.py` round-integration gate against a real open PR. **PR #54 is a live, real candidate to test against.** Not started. |
| DT-90 | To Do | Reconcile `Drunken-Team-Guide.md`/`README.md` with reality (dashboard removed -- confirmed intentionally not needed; Discord task-commanding disabled -- pending DT-94 outcome before finalizing wording). Partially blocked on DT-94. Not started. |

Backlog (label-less, not this round): **DT-95** -- token/cost tracking tech debt, explicitly deferred, not blocking beta.

## 4. Pending / Next Steps
1. Continue round-1: pick up DT-93, DT-90, or resume the DT-94 scoping conversation (Boss's choice each time -- ask, don't assume).
2. PR #54 (`feature/DT-65-qa-round-integration-gate` -> `develop`) is open and unmerged. It contains: the round-integration QA gate, jira_bridge.py's delete/comment/label/get-by-label actions, the .env-dev credential migration, and the gitignore fix. Needs Boss review/approval before merge -- do not self-merge.
3. Once round-1 is fully Done, decide round-2 scope (or just move to `beta` per the time-pressure goal above).

## 5. Known Issues & Context
- **GitHub MCP Dependency:** Agents MUST use the globally loaded `github` MCP server for all source control tasks (`create_branch`, `create_pull_request`, `merge_pull_request`, etc.) where available. In this session, direct `gh` CLI / `git` commands were used instead and worked fine -- both are acceptable, but PR-only-into-develop is the hard rule regardless of tool.
- **Branch Strategy:** `develop` is the active target, protected (PR required, `enforce_admins: true`, no force-push/delete). `feature/*` branches for work. Merges to `main`/`master` are explicitly out of scope for now per the Boss ("ยังไม่ต้องเข้า master หรือ main ไม่ต้อง pr") -- don't worry about main.
- **Jira ticket deletion/labeling:** `scripts/jira_bridge.py delete <key>`, `comment <key> <body>`, `label <key> <label>`, `get-by-label <label>` all exist now. Deletion is irreversible -- use with care, but it's the correct tool for genuinely out-of-scope/duplicate tickets (established this session with DT-41-44, DT-51-63).
- **Resolved Technical Debt:** DT-65 (untyped `mcp` decorators) is closed. The `# type: ignore[misc]` pattern is the permanent convention until upstream `mcp` SDK ships type stubs.
- **Workflow rule (hard requirement):** No ticket goes `-> Done` without passing through `In Review`, and for code changes, a round-level integration test per `qa_automation.py`. Never hand-transition a ticket straight to Done as a shortcut, even for verification-only/no-diff tickets. See memory `feedback_workflow_discipline`.
- **`.env-dev` is temporary.** Once the Boss confirms everything works and removes the 1Password "skip" from their shell, fold `.env-dev` into `.env` and delete `.env-dev`. Don't build new features that hard-depend on the `.env-dev` filename specifically -- `load_dotenv()` already checks both, in that priority order.
- **Discord task-commanding is disabled by design** since the 2026-07-02 restructure (`e43e582`), not a bug. Bot replies "disabled, use CLI" -- but there is no actual CLI dispatch equivalent (see DT-92 finding). Re-enabling is agreed in principle (DT-94) but scope/implementation is undecided -- ask the Boss before writing `_dispatch_swarm` changes.
- **Dashboard is intentionally gone.** Moved to `not_use/` previously; confirmed this session the Boss doesn't want it back (Jira alone covers monitoring needs). Don't resurrect it. `Drunken-Team-Guide.md`/`README.md` still reference it -- that's exactly what DT-90 fixes.
