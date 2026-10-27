# Skill Index

Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.

- `clear-responses` (`/clear-responses`) — Use for ordinary conversation that needs an explanation, comparison, progress update, troubleshooting, or a decision. Answer with relevant substance and evidenc
  Path: $HOME/.claude/skills/clear-responses/SKILL.md

- `concise-docs` — Use when writing a guide, a test case, a report, a release note, a Jira ticket body or a chat/session summary for a human to read — "write the install guide", "
  Path: $HOME/.claude/skills/concise-docs/SKILL.md

- `project-docs` — Use when a step has to find, create or reconcile a project's own documents — "where does this project keep its PRD?", "there are two PRD.md files, which one win
  Path: $HOME/.claude/skills/project-docs/SKILL.md

- `audit` (`/audit`) — Use when a work cycle ends, before anyone calls a requirement done, or when asked what is complete — "what shipped?", "does this requirement have evidence?", "w
  Path: $HOME/.claude/skills/audit/SKILL.md

- `breakdown` (`/breakdown`) — Use when agreed requirements need to become reviewable implementation tasks, or when a defect needs separate follow-up — "turn the PRD into tasks", "break this
  Path: $HOME/.claude/skills/breakdown/SKILL.md

- `build` (`/build`) — Use when an approved task or bug is ready for implementation — "implement this task", "fix this bug", "pick up DG-…". Accepts a user request, project task file
  Path: $HOME/.claude/skills/build/SKILL.md

- `clarify` (`/clarify`) — Use when a PRD reads cleanly but is not actually decided, after /prd and before /ddd — "what in the requirements is still undecided?", "ask me whatever you need
  Path: $HOME/.claude/skills/clarify/SKILL.md

- `ddd` (`/ddd`) — Use when a clarified PRD needs its domain modelled before /breakdown, or when one concept goes by two names — "work out the bounded contexts for this project",
  Path: $HOME/.claude/skills/ddd/SKILL.md

- `prd` (`/prd`) — Use when a project is starting, when the Boss describes something to build, or when a requirement is added before any backlog exists — "help me write down what
  Path: $HOME/.claude/skills/prd/SKILL.md

- `replan` (`/replan`) — Use when an existing requirement or task changes — "we also need…", "remove this requirement", "the customer changed their mind", "a requirement was added", or
  Path: $HOME/.claude/skills/replan/SKILL.md

- `manager` — This is the reusable manager role for planning work — not an agent-specific subagent contract. Use it to understand project requirements, propose tasks and depe
  Path: $HOME/.claude/skills/manager/SKILL.md

- `reviewer` — The reusable reviewer role — quality and security in one. Use to review a manager's plan (one round, as comments), to review a worker's tests before implementat
  Path: $HOME/.claude/skills/reviewer/SKILL.md

- `worker` — This is the reusable worker role. Use it to implement one approved task from user-provided context, project files or an optional registered tracker, validate ac
  Path: $HOME/.claude/skills/worker/SKILL.md

- `ask-boss` (`/ask-boss`) — Use when an action is destructive, irreversible or merge-worthy and needs the Boss's OK — "you need my approval before dropping that database", "I'm away this a
  Path: $HOME/.claude/skills/ask-boss/SKILL.md

- `git-workflow` (`/git-workflow`) — Use when planning a Git change, branch, commit, review request or release — "what does this repo require before I commit?", "how do I hand this change off?". Re
  Path: $HOME/.claude/skills/git-workflow/SKILL.md

- `jira-tickets` (`/jira-tickets`) — Use when writing, labelling, moving or closing a Jira ticket in this project — "what sections does a Bug ticket need?", "can I mark this Done now the PR is open
  Path: $HOME/.claude/skills/jira-tickets/SKILL.md

- `session-checkpoint` (`/session-checkpoint`) — Use when starting or ending a project work session, switching sessions, or saving or restoring project handoff context. Reads and updates the local, ignored roo
  Path: $HOME/.claude/skills/session-checkpoint/SKILL.md

- `think-analyze-isolate` (`/isolate`) — Use when running, starting, deploying or integrating something, when a backgrounded command is reported working without evidence, or when a fix fails the same w
  Path: $HOME/.claude/skills/think-analyze-isolate/SKILL.md
