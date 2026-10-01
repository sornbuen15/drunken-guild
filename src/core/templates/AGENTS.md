# AGENTS.md — {project}

<!-- guild-block:start -->
## The guild block — what to pick up, where, when

Pointers only — read the skill, role or tool named; do not reason from this table alone.

| situation | pick up |
|---|---|
| **new project** | `/prd` → `/clarify` → `/ddd` → `/breakdown`, in that order. `/replan` when a requirement is added, cut or changed after the backlog already exists. |
| **a ticket ready to build** | `/build`, run by the **worker** role. The pull request it opens is read by the **reviewer** role before a human merges it. |
| **planning or breaking work into tickets** | the **manager** role. |
| **git — branch, commit, PR, merge strategy** | `/git-workflow` (`skills/workflow/git-workflow/SKILL.md`). |
| **a Jira ticket — write it, read it, move it** | `/jira-tickets` (`skills/workflow/jira-tickets/SKILL.md`) plus the `jira_*` MCP tools. |
| **end of day / closing a session** | `/audit`. |
| **unsure which skill, role or tool fits** | `skills/INDEX.md` — read it rather than guessing a name from memory. |
<!-- guild-block:end -->

The instructions every coding agent reads in this project, whichever agent it is. Rules that bind
every agent live here and nowhere else; an agent-specific file (CLAUDE.md, …) only points here.

Written by `drunken-init`, which never overwrites it. Edit it freely.

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
