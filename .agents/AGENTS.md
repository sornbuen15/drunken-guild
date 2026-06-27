# Workspace Rules for Antigravity

## Core Directives & Policies
1. **JIRA SSOT**: Jira Cloud is the absolute Single Source of Truth. The word "Board" strictly means Jira Cloud. ALWAYS read and write task states using `python scripts/jira_bridge.py`.
2. **Destructive Commands**: You MUST NOT delete files/directories immediately. Present a markdown **Table** (Left: Path, Right: Command) and wait for Boss's explicit approval (👍).
3. **Ask Boss for Permissions**: For explicit approval or terminal blocks, use the `ask-boss` skill (`python scripts/ask_boss.py "question"`).
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
