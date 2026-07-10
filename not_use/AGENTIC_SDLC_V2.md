# Drunken-Team: Agentic SDLC & Jira MCP (v2) Architecture

This document defines the complete, strict Software Development Life Cycle (SDLC) for the Drunken-Team AI agents, powered by the custom `drunken-jira-mcp` (FastMCP) server. This ensures agents work reliably, avoid hallucination loops, and enforce 100% test-driven quality.

## 🎯 1. The Core Principles
1. **Jira is the Single Source of Truth:** All work is tracked, planned, and moved through Jira statuses via MCP tools.
2. **Fail-Fast & TDD:** Code is driven by tests. If it breaks, we fail fast. Agents do not guess; they analyze.
3. **Boss-in-the-Loop:** The AI executes the heavy lifting, but the Boss controls the deployment gates, architecture approvals, and sprint confirmations via Discord (The Silent Wait Protocol).

---

## 🛠️ 2. The Four Core MCP Commands (Prompts)

The SDLC is driven by four primary commands exposed by the `jira_mcp` server.

### 1. `init-project`
*   **Action:** The agent reads `PROJECT_SPEC.md` and `DESIGN.md` (and existing source code).
*   **Output:** Generates a high-level Domain-Driven Design (DDD) architecture document.
*   **The Feasibility Checkpoint (Spike):** Before proceeding, the agent MUST build a "Walking Skeleton" (a minimal, end-to-end code spike) to prove the chosen tech stack and architecture are technically feasible.
*   **Gate:** The Boss must review the DDD and Spike. (No Jira tickets are created until approved).

### 2. `refinement`
*   **Action:** Based on the approved DDD, the agent breaks the project down into structured Jira tasks.
*   **Output:** Creates the Backlog using `jira_create_issue`. Every task MUST have strict Acceptance Criteria (AC) which will be used for testing.

### 3. `sprint-planning`
*   **Action:** The agent reviews all tasks in the Backlog and the active board, adjusts priorities, and moves selected tasks into `TODO`.
*   **Dependency Triage:** The agent analyzes tasks to determine if they touch the same files.
    *   *No conflicts:* Can be executed in **Parallel** (by different roles).
    *   *Shared files:* Must be executed in **Sequence** to prevent Git merge conflicts.
*   **Gate:** The agent presents the Sprint Plan to the Boss and asks: *"Execute in Sequence or Parallel?"*

### 4. `review-retro`
*   **Action:** Evaluates the completed sprint. Identifies areas for improvement.
*   **Tech Debt Control:** Any improvements are tagged strictly as `[TECH-DEBT]` or `[ENHANCEMENT]` and placed at the bottom of the Backlog. They are not pulled into the next sprint unless commanded by the Boss.
*   **Gate:** Asks the Boss: *"Proceed with next sprint planning? (Yes/No)"*. Advises the Boss to create a session checkpoint and close the current AI session to clear memory context.

---

## 🚦 3. The Execution Workflow & Board Statuses

The active Sprint Board contains exactly four statuses. The transition between them is protected by strict rules.

### A. `TODO` (Awaiting Execution)
*   Tasks planned for the sprint.
*   Agents use `jira_start_task` to pull a task, auto-assign it, create the Git branch (`feature/<Task-ID>`), and move it to `IN PROGRESS`.

### B. `IN PROGRESS` (TDD & The 2-Strike Rule)
*   **TDD First:** The QA Agent (or Dev acting as QA) writes the Unit Tests based on the Acceptance Criteria *before* feature coding begins.
*   **Development:** The Developer Agent writes code strictly to pass the failing tests.
*   **The 2-Strike Loop Protection:**
    *   If tests fail, the developer attempts a fix.
    *   If it fails a *second* time, the agent MUST STOP executing code.
    *   It must use the **ค.ว.ย.** (Think, Analyze, Differentiate) protocol to find the root cause, or escalate to the Boss via Discord. No infinite guessing loops allowed.
*   *Only when isolated tests pass 100% does the task transition to `IN REVIEW`.*

### C. `IN REVIEW` (The MVP Staging Area)
*   Tasks in this column are fully developed and have passed isolated Unit/QA testing.
*   **No "Mini-Waterfall":** While developers work on other `IN PROGRESS` tasks, the QA Agent can prepare Integration/E2E test scripts for the `IN REVIEW` batch.
*   **The Integration Gate:** When *all* active tasks for the sprint have reached `IN REVIEW`, the QA Agent executes the full Integration/E2E test suite across the combined `develop` branch.
*   *If integration breaks, agents use Git isolation to pinpoint the culprit and send it back to `IN PROGRESS`.*

### D. `DONE` (Fully Verified)
*   Tasks move here ONLY after the batch Integration/E2E tests pass flawlessly.

---

## 🌿 4. Strict Git Workflow

*   **Branch Naming:** Every task is executed on an isolated branch named `feature/<Ticket-ID>`.
*   **Commits:** Every commit must start with the Jira ID (e.g., `feat(DAGY-29): implement MCP hooks`).
*   **Pull Requests:** Automated merges are ONLY allowed into the `develop` branch (via `jira_submit_for_review`).
*   **Production Deployment:** Merging `develop` into `main` / `master`, and generating Release Tags, are **strictly manual actions** that must be initiated or commanded by the Boss. The AI will never deploy to production autonomously.
