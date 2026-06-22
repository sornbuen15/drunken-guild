---
name: project-audit-reviewer
description: Performs a codebase health audit covering architecture compliance, code quality, security posture, dependency risk, and technical debt — producing a scored report and proposing backlog tasks (Jira issues or local files) for Tech Lead approval. Trigger on `/audit`, "Project audit", "Codebase review", "Architecture compliance", "technical debt".
---

# Project Code Audit & Health Check (Jira with Local Fallback)

Your objective is to conduct a structured review of the codebase, score the project health across 5 dimensions, write a permanent audit report, and propose a prioritized backlog of remediation tasks.

## Action Sequence

1. **Incremental Context Loading**:
   - Check the project guidelines in `.agents/AGENTS.md` and `engineering-standards.md`.
   - Use read-only tools (`list_dir`, `view_file`, `grep_search`) to inspect the source code, routes, configurations, and test suites.

2. **Audit Dimensions**:
   Audit the codebase against these 5 dimensions:
   - **Architecture compliance**: Separation of concerns (Presentation, Service, Infrastructure), strict inward dependencies, final classes, constructor injection.
   - **Security posture**: Hardcoded secrets, missing/weak auth gates, lack of IDOR prevention, logging of PII/secrets, missing security headers.
   - **Code quality**: declare(strict_types=1) usage, native PHP Enums cast, Slim controllers, Eloquent fillable protection, guard clauses.
   - **Dependency risk**: Composer audit violations, outdated packages.
   - **Documentation gaps**: Readme, missing comments.

3. **Score & Report**:
   - Score each dimension from 1 to 5. Calculate the overall health score.
   - Write a detailed Markdown report to `.agents/reports/audit/YYYY-MM-DD_project-audit.md`. Ensure every finding references a specific file path and line number range.

4. **Propose Backlog Tasks**:
   - Present a Dry-Run Proposal Table of recommended cleanup tasks:
     | # | Finding ID | Proposed Title | Type | Priority | Assigned To | Rationale |
   - **Gate**: Stop and ask the Tech Lead:
     *"Dry-Run complete. N task(s) proposed. Reply: Approve all / Approve #N / Reject all."*

5. **Generate Backlog Issues**:
   - Check if Jira is configured in `.agents/AGENTS.md` and is reachable (using the `jira-board` MCP server tools).
   - **If Jira is reachable**:
     - For each approved task, call `jira_create_issue` (or `create_issue`) to create an issue on Jira with the project key (as configured) and type `Task` or `Bug`. Set the description to include acceptance criteria and a reference to the audit report.
   - **If Jira is NOT reachable / enabled**:
     - Create a `.md` task file in `.agents/board/backlog/` using the canonical task template.
   - Summarize the final board status and task IDs or Jira Issue Keys created.
