# DOMAIN — drunken-guild

Accepted by the Boss, 2026-09-23. Built from `.ai/PRD.md` (REQ-001–016; REQ-005 dropped).

## Bounded contexts

| context | requirements served | what it owns |
|---|---|---|
| **Flow** | REQ-001, REQ-004, REQ-012, REQ-016 | The ordered steps from requirement to validation, and how each step hands to the next |
| **Routing** | REQ-002, REQ-010, REQ-011, REQ-013 | How an agent decides, unprompted, which skill, role or MCP tool a situation needs, and proof that it does |
| **Instructions** | REQ-006, REQ-007, REQ-015 | The one instruction file every agent reads, and the adapters that lead each agent to it |
| **Distribution** | REQ-003, REQ-008, REQ-009, REQ-014 | The one source of skills and roles, and installing it into each supported agent its own way |

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

**Adapter** — Instructions / Distribution
- An adapter holds nothing that the instruction file or the role's skill does not.
- An adapter is produced by install, never written by hand.

**Role** — Distribution
- A role is defined once, as a skill; any agent-specific definition only points at it.

**Install** — Distribution
- One install covers every supported agent; the Boss runs it.
- An update is the same install, run again.
