# DOMAIN — drunken-guild

Accepted by the Boss, 2026-09-23; reframed 2026-11-02. Built from `.ai/PRD.md`.

## Bounded contexts

| context | requirements served | what it owns |
|---|---|---|
| **Flow** | REQ-001, REQ-004, REQ-012, REQ-016, REQ-017, REQ-021, REQ-024, REQ-026 | The iterative steps from requirement to validation, and the proportionate path through them |
| **Authority** | REQ-027, REQ-028, REQ-033 | What the human authorised, what the agent may do, and which action class controls it |
| **Evidence** | REQ-029, REQ-030, REQ-034 | How observations, hypotheses, verification and measured value support engineering decisions |
| **Communication** | REQ-031, REQ-036 | How answers and durable artifacts give each reader sufficient decision-relevant information |
| **Routing** | REQ-002, REQ-010, REQ-011, REQ-013, REQ-032 | How agents classify intent, load and compose methods, select roles and access tools |
| **Instructions** | REQ-006, REQ-007, REQ-015 | The one instruction file every agent reads, and the adapters that lead each agent to it |
| **Layering** | REQ-019, REQ-020 | Where a project's AI layer lives and how it gets there: kept out of the project's repository, held in one private config repo, put in place by init |
| **Distribution** | REQ-003, REQ-008, REQ-009, REQ-014, REQ-022 | The shared source, installation and evidence for each provider's use |
| **Safety** | REQ-018, REQ-023, REQ-025 | What keeps projects safe and honest about provider capability |
| **Core boundary** | REQ-035 | Which runtime product surfaces remain outside the core; dropped requirements remain PRD history, not active domain mappings |

## Shared vocabulary

| term | definition | synonyms rejected |
|---|---|---|
| **Agent** | A coding tool that does the work: Claude Code, Antigravity, Aider, Gemini CLI | "agent" meaning a role |
| **Supported agent** | An agent/version/configuration with evidence recorded in `docs/AGENT-COMPATIBILITY.md` | "every agent" |
| **Role** | A responsibility in the flow: manager, worker, reviewer | "agent", "subagent" |
| **Specialization** | A technical lens such as backend, QA, security, DevOps or principal engineering; not a separate role unless isolation is justified | "persona" as automatic agent |
| **Step** | One stage of the flow, owned by exactly one skill and started by one command | "command", "stage" |
| **Replan** | The step that revises scope and tickets when a requirement is added, cut or changed | — |
| **Skill** | A packaged workflow in the SKILL.md format, the same content on every agent | — |
| **Description** | The part of a skill an agent reads to decide whether to use it | "trigger" |
| **Route** | One rule: a situation, and which skill, role or MCP tool it must use | — |
| **Intent** | What the human is asking for: question, explanation, analysis, review, plan, implementation or external action | "keyword" |
| **Authorization** | The human instruction that permits a bounded state-changing action | "discussion", "agreement" |
| **Path** | Fast, Standard or Controlled handling selected from work and risk | "process size" |
| **Evidence** | An observed source that can support or refute a claim: code, test output, revision, runtime observation or accepted decision | "confidence" |
| **Hypothesis** | An explanation still requiring a test; never reported as an observed fact | "root cause" before proof |
| **Routing table** | All routes a description cannot carry, kept in the instruction file | — |
| **Scenario** | A plain-language request together with the route it must produce, or "none" | "test case" |
| **Instruction file** | The project's AGENTS.md: the single place for rules that bind every agent | "the map" |
| **Adapter** | An agent-specific file that only points an agent at the standard and holds nothing of its own | "plumbing" |
| **Source** | The one central copy of skills and roles, which anyone can use | "one place", "central source" |
| **Install** | Putting the source into a supported agent's own location; running it again is an update | "deploy", "update script" as a separate thing |
| **Preload** | Loading the instruction file and every description at session start, for an agent with no skill discovery | — |
| **Lightweight** | Appropriate and sufficient for the work and risk, with no overhead lacking a justified user, safety or evidence purpose | "fewest steps", "shortest docs" |
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
- Replan records a changed requirement, preserves valid work, identifies affected or retired work,
  and proposes the changed plan before implementation; it never re-orders work by itself.
- No step decides the order of work; that is the Boss's.

**Path** — Flow / Authority
- Fast is for low-risk reversible work and retains the applicable verification and safety boundary.
- Standard adds planning and review where coordination or change size justifies them.
- Controlled adds impact analysis, explicit approval and independent verification for consequential
  or hard-to-reverse work.
- A human can change the proposed path; no path grants authority that the request did not.

**Intent** — Routing / Authority
- A request is classified before a skill, role or tool is selected.
- A question, explanation, analysis, review and plan are non-implementing intents.
- Implementation and external action require an instruction to act within a bounded scope.

**Authorization** — Authority / Safety
- Discussion, agreement with an idea and discovery of a relevant skill are not authorization.
- Materially ambiguous state-changing work stops for a human decision.
- Completion evidence names the authorising request and the surfaces changed.

**Evidence** — Evidence / Communication
- Facts, expected and actual results, hypotheses, unknowns, tests and inferred conclusions remain
  distinguishable in working notes and reports.
- A claim uses evidence appropriate to its scope: a unit test does not prove deployment, and a
  process start does not prove service health.
- Workflow expansion is a hypothesis until delivery, rework, defect, routing or correction evidence
  shows value.

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
- Excluding it from Git does not authorize deleting files from the working tree; migration preserves files and requires owner approval.
- Projects that do not opt into the guild retain their own instruction-file and tracking policy; agents do not remove or alter those files without an explicit request.
- Exception: this repository, whose AI layer is the product, keeps it tracked.

**Config repo** — Layering
- There is one, private, for all projects.

**Init** — Layering
- Until init has run in a folder, the agent does not read AGENTS.md there.
- After init, the project's git tracks none of the AI layer.

**Role** — Distribution
- A role is defined once, as a skill; any agent-specific definition only points at it.
- Manager, worker and reviewer are the core roles.
- A specialization remains a lens unless separate context, authority, independent review or useful
  parallel work justifies another agent.

**Install** — Distribution
- One install covers every supported agent; the Boss runs it.
- An update is the same install, run again.

**Guidance** — Communication / Distribution
- Quick start, daily use, safety, provider setup, troubleshooting and reference are separate layers
  for separate reader needs.
- A short first-use path does not remove prerequisites, effects, limits or recovery information.
- Commands and links are verified against the release they describe.
