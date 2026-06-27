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

Whenever a workflow requires an explicit Tech Lead or User approval gate (e.g., approving an execution plan, sprint backlog transition, or codebase audit cleanup):
- **Requirement:** You MUST send the approval request directly to Discord using the `ask_boss.py` script (e.g. `python3 scripts/ask_boss.py "Do you approve..."`).
- **Wait for Response:** The script will block and wait for the user to react (👍 for Approval / 👎 for Rejection). Respect the exit status of the script (0 for Approved, 1 for Rejected) to proceed or abort.
