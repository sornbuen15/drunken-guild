# Workspace Rules for Antigravity

## Core Directives & Policies
1. **JIRA SSOT**: Jira Cloud is the absolute Single Source of Truth. The word "Board" strictly means Jira Cloud. ALWAYS read and write task states using `python scripts/jira_bridge.py`.
2. **Destructive Commands (`rm`, `rm -rf`, `drop`)**: You MUST NOT delete files/directories immediately.
   - **Notice/List**: Present a Markdown **Table** (Columns: Path/Target, Reason).
   - **Async Workflow**: If there are other tasks you can do without deleting those files, **SKIP** the deletion for now.
   - **The Silent Wait Protocol (No Scan นิ้ว)**: If you MUST delete files, you MUST write your question to `.agents/discord_outbox.json` using the `write_to_file` tool (e.g. `{"req_1": {"question": "ขอลบไฟล์...?"}}`). Then, you MUST use the `schedule` tool (e.g. `DurationSeconds=15`, `Prompt="Check .agents/discord_inbox.json for req_1"`) and **IMMEDIATELY STOP CALLING TOOLS (End Turn)**. When you wake up, read `discord_inbox.json`. If approved, proceed. DO NOT use `run_command` for approvals!
3. **Ask Boss for Permissions**: For explicit approval or logic clarification, NEVER use `run_command` (it triggers security blocks). ALWAYS use **The Silent Wait Protocol** (write to `discord_outbox.json` + `schedule` + End Turn).
4. **Releases**: Milestone releases only. ALWAYS use the `release-notes-writer` skill format (Emoji table).

## Daily Routine
- **Auto-Start**: On a new session, proactively act as Scrum Master. Run `jira_bridge.py get-in-progress`. If empty, check `get-todo`. Propose the highest priority task to the Boss.

**Project Purpose:** To evolve Drunken-Agy into an immersive, state-of-the-art **"AI Guild Platform for Devs"**.

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

## 🧠 The "Ai-ขี้เมา" (Drunken AI) Core Mindset: ค.ว.ย. Protocol
All agents in the **drunken-team** MUST apply the **ค.ว.ย. (คิด วิเคราะห์ แยกแยะ)** skill before executing any End-to-End (E2E) testing, Server Startups, or Complex Integrations:
1. **ค (คิด - Think/Contextualize)**: Validate paths, ports, env vars, and prerequisites *before* executing commands. Do not assume or blindly execute.
2. **ว (วิเคราะห์ - Analyze/Verify)**: Analyze logs and runtime states (e.g., HTTP 200 OK). Do not assume a background command succeeded just because it didn't instantly crash.
3. **ย (แยกแยะ - Differentiate)**: If a failure occurs, isolate the root cause (code bug vs path issue vs permissions). Do not blindly retry without fixing the root cause.
# Global Rules - Local-First Jira Sync Pipeline

This configuration defines the system instructions for handling Jira workflows across all projects.

---

## Local-First Jira Sync Pipeline

Follow this exact 3-step pipeline for task planning and execution:

### PHASE 1: LOCAL PLANNING (Memory/Temp)
When a new project or brief is assigned, DO NOT contact Jira immediately. Brainstorm, break down the work, and create a comprehensive task list. Store this list locally in a temporary markdown file (e.g., '.local_backlog.md').

### PHASE 2: DEPENDENCY TRIAGE (Local State Triage)
Analyze the tasks in '.local_backlog.md':
- Tasks that have NO dependencies and can be executed immediately MUST be marked as `[IN_PROGRESS]`.
- Tasks that are blocked, dependent on others, or for later MUST be marked as `[TODO]`.

### PHASE 3: BATCH PUSH VIA LIGHTWEIGHT SCRIPT
Once the local triage is done, push the tasks to the actual Jira board:
- DO NOT use native heavy Jira plugins that read full JSON contexts.
- INSTEAD, use or write a lightweight custom CLI script (e.g., 'jira-lite-cli.sh' or python script) in the workspace to sequentially push the `[TODO]` and `[IN_PROGRESS]` tasks to Jira via REST API.
- Only push 'summary' and 'description' fields.
- Once the batch push is successful, clear the temporary file and begin executing the `[IN_PROGRESS]` tasks locally.

### PHASE 4: TRACEABILITY & COMMIT BINDING
Once tasks are pushed to Jira, Jira becomes the Absolute Source of Truth for project history.
- Every git branch created MUST include the Jira Ticket ID (e.g., feature/PROJ-123).
- Every git commit message MUST start with the Jira Ticket ID (e.g., 'fix(PROJ-123): update logic in auth.js').

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
2. Route the list back into PHASE 1 (LOCAL PLANNING).
3. Convert each bug/issue into a structured task and add it to your '.local_backlog.md'. Clarify and understand by task name: please use prefix labels like `[BUG]` or `[ISSUE]` for feedback tasks (e.g. `[BUG] 500 error on home page`).
4. Perform triage, then push these new issues to the Jira [TODO] board via the lightweight script.
5. ONLY AFTER the issues are officially on the Jira board, you may begin pulling them into [IN_PROGRESS] and fixing them one by one following the strict Git branching (feature/<Ticket-ID>) and QA workflow.

---

## Approval Channel

Whenever a workflow requires an explicit Tech Lead or User approval gate (e.g., approving an execution plan, sprint backlog transition, codebase audit cleanup, or merging a PR):
- **Requirement:** You MUST use **The Silent Wait Protocol**. Write your request to `.agents/discord_outbox.json` using `write_to_file`. (e.g. `{"req_2": {"question": "Do you approve...?"}}`).
- **Wait for Response:** You MUST then use the `schedule` tool (e.g. `DurationSeconds=20`, `Prompt="Check .agents/discord_inbox.json for req_2"`) and **IMMEDIATELY STOP CALLING TOOLS (End Turn)**. Do not loop or poll manually. When you wake up, check `discord_inbox.json` for the result. DO NOT use `run_command` for `ask_boss.py`!
