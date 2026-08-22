---
name: next-task
description: Pulls the highest-priority task from todo/ into in-progress/ using the Jira bridge script. Trigger on `/next`, "pick next task", "start next task", "what is next".
---

# Next Task Picker & Initiator (Jira Board Only)

Your objective is to safely pull the highest-priority task from the Jira Todo lane into In Progress, and formulate a strict Execution Plan for approval BEFORE making any code changes.

## Action Sequence

1. **Verify Jira In-Progress Lane**:
   - Call `jira_bridge.py get-in-progress`.
   - If any issues are returned, **refuse** to start a new task. Inform the user they must complete the active Jira issue (e.g. `PROJ-101`) first.

2. **Select Highest Priority Jira Issue**:
   - Call `jira_bridge.py get-todo`.
   - Select the first issue in the list (already sorted by priority DESC, created ASC).

3. **Transition Issue to In Progress**:
   - Call `jira_bridge.py transition <issue_key> "In Progress"`.
   - Print a success message: `Moved Jira Issue <issue_key> to In Progress`.

---

### Plan Mode & Approval Gate

1. **Inspect Codebase**:
   - Identify affected files from the task/issue description.
   - Use read-only tools (`list_dir`, `view_file`, `grep_search`) to inspect target code.

2. **Propose Execution Plan**:
   - Open a `<thinking>` block and outline:
     - **Objective**: Task description and Jira Issue Key.
     - **Analysis**: Target files, potential regressions, and architectural rules.
     - **Action Plan**: Detailed, numbered, step-by-step code modifications.
   - Close the block and present the plan.

3. **Tech Lead Approval Gate**:
   - Halt execution completely and ask the user:
     *"Tech Lead, do you approve this plan, or would you like to make adjustments before I write the code?"*
