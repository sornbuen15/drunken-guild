# Jira MCP v2: Kanban & Git Workflow Plan

This document outlines the proposed new tools and features to be added to the `drunken-jira-mcp` (in `src/jira_mcp`) to fully automate the Drunken-Team's Kanban and Git workflows.

## 📋 1. Kanban Workflow Extensions

Currently, we can transition issues, but we need tools that mimic how an Agile team works on a Kanban board.

**Proposed New MCP Tools:**
1. **`jira_pull_next_task`**
   - **Action:** Automatically queries the board for the highest priority `To Do` item, assigns it to the current agent, and transitions it to `In Progress`.
   - **Benefit:** Agents don't need to manually search and transition; they just say "Give me the next task."
2. **`jira_mark_blocked(issue_key, reason)`**
   - **Action:** Adds a blocker comment and optionally transitions the issue to a `Blocked` column or adds a `Blocker` label.
3. **`jira_kanban_metrics` (Resource)**
   - **Action:** Provides the current WIP (Work In Progress) count. If there are too many items in "In Progress", the agent is instructed to finish existing work before pulling new tasks.

## 🌿 2. Git Workflow Integration

Our global rules dictate strict Git branching (`feature/<Ticket-ID>`) and commit messages (`fix(PROJ-123): ...`). We can bake these rules directly into the MCP tools so agents never make a mistake.

**Proposed New MCP Tools:**
1. **`jira_start_work(issue_key)`**
   - **Action:** Transitions the ticket to `In Progress` and returns the **exact Git commands** the agent must execute (e.g., `git checkout -b feature/{issue_key}`).
   - **Benefit:** Enforces the branching standard programmatically.
2. **`jira_generate_commit_msg(issue_key, summary)`**
   - **Action:** Takes a brief summary of the work done and returns a strictly formatted commit message (e.g., `feat({issue_key}): {summary}`).
3. **`jira_submit_for_review(issue_key, pr_link, files_changed)`**
   - **Action:** Transitions the Jira ticket to `In Review` and automatically posts a formatted Jira comment containing the PR link and a summary of files changed.

## 🗣 Discussion Points
- Do we want `jira_mcp` to actually execute the `git` commands locally using `subprocess`, or should it just return the command strings for the AI Agent to execute via its terminal tool?
- Should we add automated regression checks (reading past closed tickets) when a bug is pulled?
