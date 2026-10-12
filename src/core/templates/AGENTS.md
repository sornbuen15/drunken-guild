# AGENTS.md — {project}

<!-- guild-block:start -->
## The guild block — what to pick up, where, when

Pointers only — read the skill, role or tool named; do not reason from this table alone.

| situation | pick up |
|---|---|
| **new project** | `/prd` → `/clarify` → `/ddd` → `/breakdown` in that order, then `/replan` once a requirement changes after the backlog already exists. |
| **an approved task ready to build** | `/build` via the **worker** role. |
| **a plan, tests, or proposed change to review** | the **reviewer** role. |
| **planning or breaking work into tasks** | the **manager** role. |
| **git — branch, commit, PR, merge strategy** | `/git-workflow` (`skills/workflow/git-workflow/SKILL.md`). |
| **a Jira issue — write, read, or move it** | Optional: `/jira-tickets` plus registered `jira_*` MCP tools. |
| **end of day / closing a session** | `/audit`. |
| **something destructive, irreversible or merge-worthy needs the Boss's approval** | `/ask-boss` (`skills/workflow/ask-boss/SKILL.md`). |
| **unsure which skill, role or tool fits** | `skills/INDEX.md` — read it rather than guessing a name from memory. |
<!-- guild-block:end -->

The instructions every coding agent reads in this project, whichever agent it is. Rules that bind
every agent live here and nowhere else; an agent-specific file (CLAUDE.md, …) only points here.

Written by `drunken-init`, which never overwrites it. Edit it freely.

Instruction files are not disposable. Never delete, untrack, overwrite, or ignore project agent
files because they look AI-specific. Change them only at the owner's request. Excluding a guild AI
layer from Git preserves its files on disk and requires an explicit, reviewed migration.

## Documents

Where this project keeps the documents the flow reads and writes. The `project-docs` skill reads
this table; change a path here and every step follows it.

| document | path |
|---|---|
| PRD — brief and numbered requirements | `.ai/PRD.md` |
| DOMAIN — contexts, vocabulary, entities | `.ai/DOMAIN.md` |
| audit reports | `.ai/audit/` |
| guides and reference | `docs/` |
| decisions (ADRs) | `docs/decisions/` |
| LESSONS — this project's own recorded lessons | `.ai/LESSONS.md` |

## Jira

- Project id, the first argument of every `drunken-jira-mcp` tool: `{project}`
- Jira project key: {jira_key}

## Deploy

Not recorded yet. The first time a merged task should reach an environment, `/build` asks the
project owner and records the answer here.

## Commands

<!-- How to install, test, lint and run this project. One command per line. -->
