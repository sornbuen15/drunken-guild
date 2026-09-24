# Skill Index

Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.

- `project-docs` — The one contract for finding a project's own documents: the map in AGENTS.md, the defaults when there is no map, what two copies of one document mean, and what
  Path: $HOME/.claude/skills/project-docs/SKILL.md

- `audit` (`/audit`) — The last step of the flow: trace every requirement in PRD.md through to a ticket, a test, and a green run on the merged tree, turn each gap into a ticket, and w
  Path: $HOME/.claude/skills/audit/SKILL.md

- `breakdown` (`/breakdown`) — Turns PRD.md and DOMAIN.md into the Jira hierarchy — one Epic per bounded context, Stories from the requirements it serves, Tasks sized to a day — with every le
  Path: $HOME/.claude/skills/breakdown/SKILL.md

- `build` (`/build`) — The flow step that executes one task: read the ticket, check its plan still holds against the code, write the test from its ACCEPTANCE and watch it fail, implem
  Path: $HOME/.claude/skills/build/SKILL.md

- `clarify` (`/clarify`) — The second step of the flow: read the PRD and put a short, ranked list of decisions to the Boss — each one naming its REQ-xxx, the ambiguity, and two or three c
  Path: $HOME/.claude/skills/clarify/SKILL.md

- `ddd` (`/ddd`) — Produces the project's DOMAIN.md from a clarified PRD.md — the bounded contexts that become Epics, the shared vocabulary the whole team spells the same way, and
  Path: $HOME/.claude/skills/ddd/SKILL.md

- `prd` (`/prd`) — The first step of the flow: write or update the project's PRD — the brief and the numbered requirements in one file, each requirement carrying an id REQ-xxx and
  Path: $HOME/.claude/skills/prd/SKILL.md

- `replan` (`/replan`) — The step for when a requirement is added, cut or changed after the backlog exists: amend PRD.md by /prd's rules, then show which tickets to add, amend and close
  Path: $HOME/.claude/skills/replan/SKILL.md

- `ask-boss` — Ask the Boss for permission without stopping: ask in the conversation when they are reading it, otherwise send one notification, park the task, and keep working
  Path: $HOME/.claude/skills/ask-boss/SKILL.md

- `git-workflow` (`/git-workflow`) — Best-practice Git discipline — branch naming, commit conventions, PR lifecycle, which merge strategy belongs to which target, and release hygiene. Apply wheneve
  Path: $HOME/.claude/skills/git-workflow/SKILL.md

- `jira-tickets` — How to write and run a ticket in this project: the hierarchy a ticket sits in, the five shapes — Epic, Story, Task, Subtask, Bug — the labels that make work tra
  Path: $HOME/.claude/skills/jira-tickets/SKILL.md

- `think-analyze-isolate` (`/isolate`) — Discipline against blind execution during end-to-end runs, server startup, deployment, and integration work — check the prerequisites, verify the thing is actua
  Path: $HOME/.claude/skills/think-analyze-isolate/SKILL.md
