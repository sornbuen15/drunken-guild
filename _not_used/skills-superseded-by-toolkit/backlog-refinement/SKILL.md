---
name: backlog-refinement
description: Scans tasks from the Jira backlog to promote to Jira "To Do" status based on priority levels, with a rule to always auto-promote CRITICAL tasks first. Trigger on `/refine`, "sprint planning", "sprint refinement", "prioritize backlog".
---

# Backlog Refinement & Sprint Planning (Jira Board Only)

Your job is to analyze the Jira backlog tasks, group them by priority, and propose moving tasks to the sprint queue (Todo lane) in priority-based groups.

## Action Sequence

1. **Scan Jira Board Lanes**:
   - Retrieve issues in the active sprint or backlog using the Jira bridge:
     - Active / In Progress issues: `jira_bridge.py get-in-progress`
     - Selected / Sprint Todo issues: `jira_bridge.py get-todo`
     - Backlog issues: `jira_bridge.py get-backlog`

2. **Auto-Promote Critical Issues**:
   - If any issue in the `Backlog` has priority `Critical`, automatically transition it to `To Do` (Selected for Sprint) immediately using `jira_bridge.py transition <issue_key> "To Do"`. Notify the user.

3. **Propose Refinement Group**:
   - Propose promoting a group of issues from `Backlog` to `To Do` by priority (e.g. promoting all `High` priority issues).
   - Show a summary of the current sprint board status:
     - **Active Issues** (In Progress)
     - **Selected Issues** (To Do)
     - **Proposed Issues to Promote** (Backlog -> To Do transition)
     - **Remaining Backlog**
   - **Gate**: Stop and ask the Tech Lead:
     *"Tech Lead, do you approve transitioning these Jira issues to 'To Do' (Sprint Backlog)?"*

4. **Execute Transition**:
   - Upon approval, call `jira_bridge.py transition <issue_key> "To Do"` on the approved issues.
   - Output the finalized Sprint Board status.
