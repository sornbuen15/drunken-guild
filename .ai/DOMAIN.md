# DOMAIN — drunken-guild

Accepted by the Boss, 2026-09-23. Built from `.ai/PRD.md` (REQ-001–022; REQ-005 dropped).

## Bounded contexts

| context | requirements served | what it owns |
|---|---|---|
| **Flow** | REQ-001, REQ-004, REQ-012, REQ-016, REQ-017, REQ-018, REQ-021 | The ordered steps from requirement to validation, how each step hands to the next, and the checks — including a schedule independent of any step, such as a dependency audit — that keep the work trustworthy |
| **Routing** | REQ-002, REQ-010, REQ-011, REQ-013 | How an agent decides, unprompted, which skill, role or MCP tool a situation needs, and proof that it does |
| **Instructions** | REQ-006, REQ-007, REQ-015, REQ-023 | The one instruction file every agent reads, the adapters that lead each agent to it, and the floor an agent cannot talk its way past, including the guard that keeps a registered id out of the repository |
| **Layering** | REQ-019, REQ-020 | Where a project's AI layer lives and how it gets there: kept out of the project's repository, held in one private config repo, put in place by init |
| **Distribution** | REQ-003, REQ-008, REQ-009, REQ-014, REQ-022 | The one source of skills and roles, and installing it into each supported agent its own way |

## Shared vocabulary

| term | definition | synonyms rejected |
|---|---|---|
| **Agent** | A coding tool that does the work: Claude Code, Antigravity, Aider, Gemini CLI | "agent" meaning a role |
| **Supported agent** | An agent the standard must work under: Claude Code, Antigravity, Aider (Must); Gemini CLI (Could) | "every agent" |
| **Role** | A responsibility in the flow: manager, worker, reviewer | "agent", "subagent" |
| **Step** | One stage of the flow, owned by exactly one skill and started by one command | "command", "stage" |
| **Replan** | The step that revises scope and tickets when a requirement is added, cut or changed | — |
| **Skill** | A packaged workflow in the SKILL.md format, the same content on every agent | — |
| **Description** | The part of a skill an agent reads to decide whether to use it | "trigger" |
| **Route** | One rule: a situation, and which skill, role or MCP tool it must use | — |
| **Routing table** | All routes a description cannot carry, kept in the instruction file | — |
| **Scenario** | A plain-language request together with the route it must produce, or "none" | "test case" |
| **Instruction file** | The project's AGENTS.md: the single place for rules that bind every agent | "the map" |
| **Adapter** | An agent-specific file that only points an agent at the standard and holds nothing of its own | "plumbing" |
| **Source** | The one central copy of skills and roles, which anyone can use | "one place", "central source" |
| **Install** | Putting the source into a supported agent's own location; running it again is an update | "deploy", "update script" as a separate thing |
| **Preload** | Loading the instruction file and every description at session start, for an agent with no skill discovery | — |
| **Brief** | The project-level agreement: what, who for, stack, constraints | "constitution" |
| **Project** | A body of work the Boss runs under the guild, in its own repository | — |
| **Work** | What a project builds: its code, requirements, stack and domain. Lives in the project's repository and says nothing about how the AI works | "content", "the product" |
| **AI layer** | Everything about how the AI works on a project rather than what is built: AGENTS.md, the CLAUDE.md adapter, `.claude/`, hooks, Jira configuration | "wrapper", "AI config", "setup" |
| **Config repo** | The one private repository that holds the AI layer of every project | "AI repo", "settings repo" |
| **Init** | The step that puts a project's AI layer into its folder from the config repo; not Install, which puts the guild's own source into an agent | "install" |

## Core entities

**Step** — Flow
- There are seven steps; each is owned by exactly one skill.
- Every step names the step that follows it, and the skills, roles and tools it calls.
- Replan revises scope and tickets against a changed requirement; it never re-orders work.
- No step decides the order of work; that is the Boss's.

**Brief** — Flow
- A project has exactly one brief, and it lives in the PRD; no separate constitution exists.

**Route** — Routing
- A route leads to exactly one skill, one role, one MCP tool, or nothing.
- Every route's target exists.
- Every skill is reachable from its description or from at least one route.

**Scenario** — Routing
- A scenario expects exactly one route, or none.
- A scenario passes when the expected choice is made in at least 2 of 3 runs.
- The standard holds only when every scenario passes on every supported agent.

**Skill** — Routing / Distribution
- Its description names the situations and plain-language requests it is for.
- It has one source; every supported agent gets the same content.

**Instruction file** — Instructions
- Any project that points an agent at it has one.
- A rule that must bind every agent lives here and nowhere else.
- In a project under the guild it is part of the AI layer.

**Adapter** — Instructions / Distribution
- An adapter holds nothing that the instruction file or the role's skill does not.
- An adapter is produced by install or by init, never written by hand.

**AI layer** — Layering
- It belongs to exactly one project and comes from the config repo.
- The project's own git never tracks any of it.
- It holds instructions about how the AI works, never facts about what is built.
- Exception: this repository, whose AI layer is the product, keeps it tracked.

**Config repo** — Layering
- There is one, private, for all projects.

**Init** — Layering
- Until init has run in a folder, the agent does not read AGENTS.md there.
- After init, the project's git tracks none of the AI layer.

**Role** — Distribution
- A role is defined once, as a skill; any agent-specific definition only points at it.

**Install** — Distribution
- One install covers every supported agent; the Boss runs it.
- An update is the same install, run again.
