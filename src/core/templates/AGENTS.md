# AGENTS.md — {project}

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

## Jira

- Project id, the first argument of every `drunken-jira-mcp` tool: `{project}`
- Jira project key: {jira_key}

## Deploy

Not recorded yet. The first time a merged task should reach an environment, `/build` asks the
project owner and records the answer here.

## Commands

<!-- How to install, test, lint and run this project. One command per line. -->
