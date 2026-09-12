# Skill Index

Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.

- `project-docs` — The one contract for a project's own documents — which ones exist, where to look for them, how to read them together, and what to do when one is missing or two
  Path: $HOME/.claude/skills/project-docs/SKILL.md

- `audit-to-backlog` (`/audit`) — Analyzes failures or audits, writes a permanent post-mortem report, and converts every action item into a Jira backlog ticket via drunken-jira-mcp. Apply whenev
  Path: $HOME/.claude/skills/audit-to-backlog/SKILL.md

- `backlog-refinement` (`/refine`) — Moves backlog tickets onto the board by urgency tier, always selecting critical tickets first. Apply whenever the user wants to plan a sprint, choose what to wo
  Path: $HOME/.claude/skills/backlog-refinement/SKILL.md

- `issue-intake` (`/issue`) — Captures user-reported bugs and problems as properly classified Jira tickets via drunken-jira-mcp. Apply whenever the user reports a bug, says something is brok
  Path: $HOME/.claude/skills/issue-intake/SKILL.md

- `jira-tickets` — How to write and run a ticket in this project: the three-part shape, the fields this Jira can actually set, the status lifecycle, and what must be verified befo
  Path: $HOME/.claude/skills/jira-tickets/SKILL.md

- `local-progress-reporter` (`/report`) — Aggregates Jira ticket data into a structured project status report. Apply whenever the user asks about progress, wants a status update, asks what's done or in-
  Path: $HOME/.claude/skills/local-progress-reporter/SKILL.md

- `spec-to-backlog` (`/init-project`) — Reads every project document that exists — brief, requirements, spec, architecture, policy — on Day 0 and generates a comprehensive, labelled Jira backlog of at
  Path: $HOME/.claude/skills/spec-to-backlog/SKILL.md

- `task-estimation` (`/estimate`) — Estimates complexity, AI execution cycles, and human review effort for the TODO tickets on the Jira board. Apply whenever the user asks how long something will
  Path: $HOME/.claude/skills/task-estimation/SKILL.md

- `anti-regression` (`/surgical`) — Surgical modification standard to prevent regressions during refactoring or bug-fixing. Apply whenever the user is modifying existing code, especially shared fi
  Path: $HOME/.claude/skills/anti-regression/SKILL.md

- `ask-boss` — Ask the Boss for permission without stopping: submit the question, park the task, keep working on what isn't blocked, and collect the answer at the next task bo
  Path: $HOME/.claude/skills/ask-boss/SKILL.md

- `core-engineering` (`/tdd`) — Engineering discipline for TDD, systematic debugging, and safe refactoring. Apply this skill whenever the user is fixing a bug, writing or updating tests, debug
  Path: $HOME/.claude/skills/core-engineering/SKILL.md

- `git-workflow` (`/git-workflow`) — Best-practice Git discipline — branch naming, commit conventions, PR lifecycle, which merge strategy belongs to which target, and release hygiene. Apply wheneve
  Path: $HOME/.claude/skills/git-workflow/SKILL.md

- `project-audit-reviewer` (`/audit-project`) — Comprehensive codebase health audit — architecture compliance, security, code quality, dependencies, and docs — with a scored report and dry-run backlog proposa
  Path: $HOME/.claude/skills/project-audit-reviewer/SKILL.md

- `release-notes-writer` — Standardizes the generation of professional, readable Release Notes and Tag Version descriptions using markdown tables and clear categorizations.
  Path: $HOME/.claude/skills/release-notes-writer/SKILL.md

- `test-report-generator` (`/test-report`) — Runs the full test suite live, audits Jira ticket state, checks architecture compliance, and writes a dated Markdown test report as the pre-merge quality gate r
  Path: $HOME/.claude/skills/test-report-generator/SKILL.md

- `think-analyze-isolate` (`/isolate`) — Discipline against blind execution during end-to-end runs, server startup, deployment, and integration work — check the prerequisites, verify the thing is actua
  Path: $HOME/.claude/skills/think-analyze-isolate/SKILL.md
