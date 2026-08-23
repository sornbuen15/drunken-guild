# Workspace Rules for Antigravity

## Where your skills and agents come from

**They are not authored here, and they are not yours to edit in place.** Every skill and every
agent in `~/.gemini/config/skills/` that belongs to this project is *generated* from one source:

| you read | generated from | by |
|---|---|---|
| `~/.gemini/config/skills/<agent>/SKILL.md` | `agents/<agent>.md` | `scripts/install/install_agents.sh` |
| `~/.gemini/config/skills/<skill>/` | `skills/<category>/<skill>/` | `scripts/install/install_skills.sh` |

Editing an installed copy is writing to a file the next install overwrites. Change the source in
the repository and ask the Boss to re-run the installer.

This replaces `.agents/skills/`, which held fifteen hand-maintained copies of `agents/`. Twelve <!-- drift-ok: naming what was replaced is the point of the sentence -->
matched their source; three had drifted, and `principal-engineer` had fallen to 78 lines against
311 while still describing an orchestrator retired two tickets earlier. Nothing announced it. The
copy is gone because the copy was the problem.

**Anything in `~/.gemini/config/skills/` that this project did not put there is not ours.** That
directory also holds ~30 Apache-2.0 skills shipped by Google and Antigravity's own template. Do
not move, overwrite or tidy them.

**Claude and you read the same rules.** `CLAUDE.md` is the same standard written for the other
agent; where this file and that one disagree, that is a bug — report it rather than picking one.

---

## Core Directives & Policies
1. **JIRA SSOT**: Jira Cloud is the absolute Single Source of Truth. The word "Board" strictly means Jira Cloud. Read and write task states with the `drunken-jira-mcp` tools (`jira_search_issues`, `jira_start_task`, `jira_transition_issue`, `jira_submit_for_review`, `jira_add_comment`). `scripts/jira_bridge.py` still works for shell use, but the MCP tools are the supported path. **How to write and run a ticket — the FINDING/SCOPE/ACCEPTANCE shape, the fields this Jira can actually set, and what must be verified before Done — is in the `jira-tickets` skill. Read it before opening or closing one.**
   - **Attribution**: Assignee needs a real email, so it cannot say which agent is on a ticket. A ticket you are actively working carries the label `agent:antigravity` (Claude's is `agent:claude`); Assignee still names the accountable human (DG-293).
2. **Destructive Commands (`rm`, `rm -rf`, `drop`)**: You MUST NOT delete files/directories immediately.
   - **Notice/List**: Present a Markdown **Table** (Columns: Path/Target, Reason).
   - **Async Workflow**: If there are other tasks you can do without deleting those files, **SKIP** the deletion for now.
   - **If you MUST delete files**: ask the Boss first — see directive 3 for how. Do NOT write to `.agents/discord_outbox.json` directly; that file is internal daemon state, not an API. <!-- drift-ok: naming the retired file is the point — this says not to use it -->
3. **Ask Boss for Permissions**: For explicit approval or logic clarification, NEVER use `run_command` (it triggers security blocks).
   - **If the Boss is watching this conversation live, just ask directly.** Discord is for when they are not.
   - Otherwise call `request_boss_approval_async` (`action`, `reason`, `ticket_key`), which returns a `req_id` immediately. Park the task, take the next unblocked one from Jira, and collect the answer with `check_approvals` **when you finish a task or start a session — never mid-task.** Half-applied approvals leave the repo in a state nobody can reason about. See the `ask-boss` skill.
   - **Asking must never stop the other work.** There is no timeout and nothing is killed for going unanswered; reminders back off 15 min → 1 h → daily and survive a daemon restart.
   - An approval is bound to the commit it was granted against. From a different HEAD it reads `stale` and must be asked again.
   - The blocking `request_boss_approval` still works and is kept until 3.0.0. Prefer the async pair.
4. **Releases**: Milestone releases only. ALWAYS use the `release-notes-writer` skill format (Emoji table).

## Daily Routine
- **Auto-Start**: On a new session, proactively act as Scrum Master. Call `check_approvals` for anything still outstanding, then `jira_search_issues` for `status = "In Progress"`. If empty, look at `To Do`. Propose the highest priority task to the Boss.

**Project Purpose:** `drunken-guild` — the skills, agents and MCP servers that direct AI coding agents. One repository, two deliverables: the AI layer in `skills/` and `agents/`, the runtime in `src/`.

## Google Code Assist & Code Quality Standard (100% Quality)
1. **Shift-Left Quality & Security**: Code quality and security are NOT just pre-commit checks. They must be embedded from the very beginning:
   - **Design First**: Before writing code, analyze architecture, address security risks (e.g., OWASP, injections, secrets), and plan the test coverage.
   - **Clean Code (No Spaghetti)**: Adhere strictly to SOLID principles, modular design, DRY, and high readability. Code must be elegant and maintainable, not just functional.
   - **Security Built-in**: Prevent vulnerabilities during implementation (e.g., strict input validation, proper error handling, no hardcoded secrets).
2. **Pre-commit is merely the Final Gatekeeper**: `pre-commit` (or Google Code Assist linting) is just the final safety net to catch minor typos. The code must be structurally sound and 100% high-quality *before* it even hits the pre-commit hook.
3. **Strict Development Workflow**:
   - `To Do` -> `In Progress`
   - **Design & Security Plan** -> **Implement Clean Code** -> **Write Tests (`pytest`)**
   - **Final Gatekeeper Check** (`pre-commit run --all-files`)
   - `In Review` (Report test results and code quality to Boss)
   - PR Merge (if approved) -> `Done`

## 🛡️ The Zero-Defect Pipeline (Enterprise-Grade Quality)
1. **Automated Guardrails (Machine Verified):**
   - **Type Checking**: Strict `mypy` enforcement. No missing method calls allowed.
   - **Coverage Gate**: `pytest-cov` must be utilized. Tests must cover exceptions (Negative Testing), not just happy paths.
   - **Code Smells**: `ruff` strict rules (e.g., complexity, bugbear) must be adhered to.
2. **Strict Mocking (`autospec=True`)**:
   - `mocker.MagicMock()` and `mock.patch()` without `autospec=True` or `spec=` are STRICTLY FORBIDDEN. All mocks must perfectly mirror the real API contract.
3. **Global Exception Architecture**:
   - Centralize error handling. Log technical stack traces for Devs, but return clean, UX-friendly JSON messages to Users. No silent deadlocks.
4. **The Pragmatic Escape Hatch (5-10% Tech Debt):**
   - If blocked by a third-party library or an extreme edge case, you may bypass a rule (e.g., `# type: ignore` or `# noqa`) **ONLY IF** you immediately log a Technical Debt ticket in Jira and append the ticket ID in the comment.
5. **The Pre-Flight Mantra**:
   - Before any `git commit`, the Agent MUST scrutinize its own logic ("Did I actually test this, or did I hallucinate it?") and verify Jira states are strictly adhered to.

## 🧠 The Drunken AI Core Mindset: think, analyze, isolate
Every agent MUST apply the **`think-analyze-isolate`** skill before any end-to-end test, server startup, or complex integration:
1. **Think / contextualize**: Validate paths, ports, env vars and prerequisites *before* executing commands. Do not assume, do not blindly execute.
2. **Analyze / verify**: Read logs and runtime state (e.g. an actual HTTP 200). A background command that did not instantly crash has not succeeded.
3. **Isolate**: On failure, separate the root cause — code bug vs path vs permissions. Do not retry without fixing it.

This is the English rendering of the Thai-language skill that carried the same discipline. That original is retired to `_not_used/agent-layer-stubs/khit-wikhro-yaekyae/` and is no longer installed; load `think-analyze-isolate` by name from the skill index.
# Global Rules - Local-First Jira Sync Pipeline

This configuration defines the system instructions for handling Jira workflows across all projects.

---

## Planning work

**Superseded 2026-08-19.** This section used to describe a "Local-First Jira
Sync Pipeline": brainstorm into a local `.local_backlog.md`, mark tasks
`[TODO]`/`[IN_PROGRESS]` there, then batch-push them to Jira with a hand-written
REST script, explicitly avoiding the MCP tools because they "read full JSON
contexts".

Both halves are now wrong, and each for a measured reason.

**The local file was a second board.** DG-250 retired exactly that: a list
beside Jira that carries its own statuses is a surface that can disagree with
the real one, which is the failure DG-248 and DG-249 each cost a session to.
This project's own local board held three cards, last touched 2026-07-22, still
using a ticket prefix retired months earlier — while every real ticket of that
period went through Jira and never touched it.

**The token argument no longer holds.** It was a fair objection when a
six-issue search cost 5,697 tokens, 95% of it raw ADF nobody read. DG-255
measured and fixed that: the same search is now 894 characters, and a
hand-written REST script is a second Jira client that can disagree with the
first.

### What to do instead

Plan in the conversation, then file directly with the MCP tools. `jira_create_issue`
accepts `parent`, `duedate`, `start_date` and `labels` — the old "only push
summary and description" limit is gone, and `parent` is what stops an Epic
having no children and Timeline drawing nothing.

Read the `jira-tickets` skill for the
ticket shape and the lifecycle. Nothing is stored locally; the assignee says
whose the work is and the status says where it is.

### PHASE 4: TRACEABILITY & COMMIT BINDING
Once tasks are pushed to Jira, Jira becomes the Absolute Source of Truth for project history.
- Every git branch created MUST include the Jira Ticket ID (e.g., feature/PROJ-123).
- Every git commit message MUST start with the Jira Ticket ID (e.g., 'fix(PROJ-123): update logic in auth.js').
- Every commit you make passes `--author="Antigravity <antigravity@drunken.local>"` — a local-only
  address that resolves to no real account, so `git log` tells your commit from the operator's on
  sight (DG-293). Claude's equivalent is `Claude Code <claude@drunken.local>`.

### PHASE 5: AUDIT TRAIL & COMPLETION
- When you finish a task and use the lightweight script to transition it to [DONE], you MUST automatically send a brief comment to the Jira ticket. The comment must include:
  1. The files changed.
  2. A 1-sentence summary of the logic updated or bug fixed.

### PHASE 6: REGRESSION CHECK (BEFORE FIXING BUGS)
- If you are assigned to fix a bug or update a feature, before writing any code, you must use the lightweight script to quickly search closed Jira tickets for related keywords.
- Read the audit trail of past tickets to understand how it was 'fixed' previously. This prevents you from re-introducing old bugs or undoing previous architectural decisions.

### PHASE 7: FEEDBACK LOOP & ISSUE TRIAGE
Whenever the user provides a list of bugs, feedback, or issues (no matter how urgent), you MUST NOT start writing code or fixing them immediately.
1. STOP executing code.
2. Triage the list first: what is one ticket, what is several, what the repository already records and therefore is not a ticket at all.
3. File each one with `jira_create_issue`, in the FINDING/SCOPE/ACCEPTANCE shape the `jira-tickets` skill defines. Summary lines carry an area prefix: `[BUG] 500 error on home page`.
4. Give related tickets a `parent` so the Epic has children and Timeline is not empty. Use `labels` for urgency — priority cannot be set on this project.
5. ONLY AFTER the tickets exist in Jira, pull them into In Progress one at a time, following the branch convention (`feature/<Ticket-ID>-slug`) and the QA workflow.

---

## Approval Channel

Whenever a workflow requires an explicit Tech Lead or User approval gate (e.g., approving an execution plan, sprint backlog transition, codebase audit cleanup, or merging a PR):
- **If the Boss is watching this conversation live**, skip the tool entirely and just ask them directly — Discord is only needed when nobody may be reading this conversation right now.
- **Otherwise:** call `request_boss_approval_async` (`action`, `reason`, `ticket_key`) — see the `ask-boss` skill for details. It returns a `req_id` straight away rather than an answer. Park the work, carry on with something unblocked, and read the verdict with `check_approvals` at the next task boundary: `approved`, `rejected`, `pending`, `stale` (approved against a different commit — ask again) or `unknown` (never submitted; re-submit rather than assume).
- **Force-push, hard reset, `rm -rf` and reading `.env` are refused by `.claude/settings.json` regardless of what comes back over Discord.** Do not route around it; raise it with the Boss.
- Do NOT write to `.agents/discord_outbox.json` or read `.agents/discord_inbox.json` directly; those are internal daemon state, not an API, and this protocol (write file + `schedule` + end turn) is retired. <!-- drift-ok: the prohibition has to name what it prohibits -->
