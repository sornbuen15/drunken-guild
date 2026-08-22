# Drunken AI Team
*Brought to you by Drunken Programmer*

> **EXPERIMENTAL WARNING:** This project is a work-in-progress. **Do NOT use in a production environment** — it may cause unexpected errors, delete files, or produce unintended consequences.

An AI-powered development team toolkit using Claude — skills, agents, and workflows that assemble a disciplined engineering squad for any software project.

A collection of **29 skills**, **5 specialist agents**, and a **10-agent engineering squad** that transforms Claude Code into a structured, team-based engineering system. Work is coordinated on **Jira** through the typed `drunken-jira-mcp` server — agents call its tools natively instead of composing shell commands.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Companion Repo (optional)](#companion-repo-optional)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [macOS / Linux](#macos--linux)
  - [Windows](#windows)
- [How It Works](#how-it-works)
  - [Skills vs Agents](#skills-vs-agents)
  - [The Three-Tier System](#the-three-tier-system)
- [Tier 1 — Domain Specialists](#tier-1--domain-specialists)
- [Specialty AI Agents](#specialty-ai-agents)
- [Tier 2 — Principal Engineer](#tier-2--principal-engineer)
- [Tier 3 — Engineering Squad](#tier-3--engineering-squad)
- [Skill Catalog](#skill-catalog)
- [Leader's Guidebook](#leaders-guidebook)
- [Workflows](#workflows)
- [Repository Structure](#repository-structure)
- [Known Limitations](#known-limitations)

---

## Quick Start

**1. Clone and install**

```bash
# macOS / Linux
git clone <repo-url> drunken-ai-team
cd drunken-ai-team
bash scripts/install/sync_skills.sh
bash scripts/install/sync_agents.sh
```

```powershell
# Windows (PowerShell — run as Administrator if needed)
git clone <repo-url> drunken-ai-team
cd drunken-ai-team
.\scripts\install\sync_skills.ps1
.\scripts\install\sync_agents.ps1
```

**2. Set up your project context**

```bash
cp templates/PROJECT_BRIEF.md  your-project/
cp templates/REQUIREMENTS.md   your-project/
# Fill in both files — agents read them before every session
```

**3. Start the orchestrator**

```bash
claude --agent principal-engineer
```

> "Read `PROJECT_BRIEF.md` and `REQUIREMENTS.md`. Give me a platform strategy, initial ADR, and squad plan."

**4. Generate your backlog**

```
/init-project
```

**5. Pick the first task and build**

```
/next
```

That's it. See [GETTING_STARTED.md](./GETTING_STARTED.md) for a step-by-step walkthrough.

---

## Installation

### Prerequisites

- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- Git
- **[Node.js](https://nodejs.org/) v18 or v24** *(required for the kanban MCP server and CLI fallback scripts)*
- **macOS / Linux:** Bash 3.2+, `rsync`
- **Windows:** PowerShell 5.1+ or [PowerShell Core 7+](https://github.com/PowerShell/PowerShell/releases)

### macOS / Linux

```bash
# Clone the repo
git clone <repo-url> drunken-ai-team
cd drunken-ai-team

# Install skills to ~/.claude/skills/
bash scripts/install/sync_skills.sh

# Install agents to ~/.claude/agents/
bash scripts/install/sync_agents.sh
```

Re-run both scripts after any skill or agent update.

### Windows

Open PowerShell (5.1+ or Core 7+) and run:

```powershell
# Clone the repo
git clone <repo-url> drunken-ai-team
cd drunken-ai-team

# If script execution is blocked, enable it first (one-time, current user):
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install skills to %USERPROFILE%\.claude\skills\
.\scripts\install\sync_skills.ps1

# Install agents to %USERPROFILE%\.claude\agents\
.\scripts\install\sync_agents.ps1
```

Re-run both scripts after any skill or agent update.

> **Coordination needs one MCP server, and it is not authored here.** See [Companion Repo](#companion-repo-optional) — 21 of the 29 skills need nothing but this repo. The old local-board scripts and their server are retired to [`_not_used/scripts/`](./_not_used/scripts/).

---

## Companion Repo (optional)

**21 of the 29 skills need nothing but this repo.** Architecture, testing, security, UI/UX,
Electron, git discipline — all of it installs and works standalone. If you have no Jira, install
this repo and stop reading here.

The other **8** coordinate work on Jira — `spec-to-backlog`, `backlog-refinement`,
`issue-intake`, `audit-to-backlog`, `task-estimation`, `local-progress-reporter`,
`test-report-generator`, `project-audit-reviewer` — along with the `principal-engineer` agent.
They need **[`sornbuen15/drunken-team`](https://github.com/sornbuen15/drunken-team)** (MIT):

| what it provides | why |
|---|---|
| `drunken-jira-mcp` | the `jira_*` tools every coordination skill calls |
| `.agents/skills/jira-tickets/SKILL.md` | ticket-writing rules those skills treat as authoritative and link to rather than copy |
| `.agents/skills/ask-boss/SKILL.md` | the approval protocol |

```bash
git clone https://github.com/sornbuen15/drunken-team.git ~/Projects/drunken-team
```

**Clone it to `~/Projects/drunken-team` specifically** — the skills reference that path
absolutely. Full setup, the `.mcp.json` snippet, and what degrades without it are in
[`GETTING_STARTED.md`](./GETTING_STARTED.md#optional--the-companion-repo-for-coordination-only).

---

## How It Works

### Skills vs Agents

| | Skills | Agents |
|---|---|---|
| **What it is** | A domain standard loaded into the current context | A standalone AI instance with its own context window |
| **How to invoke** | Slash command: `/clean-arch`, `/secure`, `/tdd` | `claude --agent <name>` or `@"name (agent)"` |
| **Runs in** | Your current conversation | Its own isolated context — starts fresh every time |
| **Memory** | Shares your conversation history | No conversation history unless passed explicitly |
| **Tools** | Same as your session | Only the tools declared in the agent definition |
| **Purpose** | Enforce a specific standard or workflow during a task | Execute a category of work autonomously |
| **Best for** | "While I'm coding, apply this architecture standard" | "Go implement this feature and come back with the result" |

**In practice, agents USE skills.** When a squad agent starts a task, it reads the skills index and loads the relevant skill (e.g., `clean-architecture`, `anti-regression`) before writing code.

### The Three-Tier System

```
┌─────────────────────────────────────────────────────────┐
│  TIER 1 — Domain Specialists                            │
│  WHAT to build · domain rules · regulations · data      │
│  fintech-specialist · insurance-specialist              │
└──────────────────────────┬──────────────────────────────┘
                           │ Domain Brief
                           ▼
┌─────────────────────────────────────────────────────────┐
│  TIER 2 — Principal Engineer                            │
│  HOW to structure the team · technical direction        │
│  platform strategy · ADRs · squad assembly              │
└──────────────────────────┬──────────────────────────────┘
                           │ Delegation
                           ▼
┌─────────────────────────────────────────────────────────┐
│  TIER 3 — Engineering Squad                             │
│  EXECUTION · code · infra · tests · security · mobile   │
│  fullstack · devops · qa · security · ios · android     │
│  cross-platform · laravel · desktop                     │
└─────────────────────────────────────────────────────────┘
```

**Tier 1** is optional — skip it for general engineering work. Required when building in a regulated or domain-heavy space (finance, insurance, health).

**Tier 2** is always the orchestrator. It reads domain context, makes platform decisions, assembles the squad, and synthesizes results back to you.

**Tier 3** are the executors. Each specialist loads the relevant skills before starting work.

---

## Tier 1 — Domain Specialists

Domain specialists carry deep industry knowledge: regulations, protocols, data models, and compliance patterns. They advise on **what to build** and what constraints apply. They do not write code.

| Agent | Model | Invoke when... |
|---|---|---|
| `fintech-specialist` | Sonnet 5 | Building payments, banking, wallets, lending, KYC/AML, or anything touching PCI-DSS, PSD2, SWIFT, ACH, ISO 20022 |
| `insurance-specialist` | Sonnet 5 | Building policy admin, claims, underwriting, or anything touching NAIC, HIPAA, ACA, Solvency II, IFRS 17 |

```bash
claude --agent fintech-specialist
claude --agent insurance-specialist

# Or invoke mid-conversation
@"fintech-specialist (agent)" review this payment API design
```

---

## Specialty AI Agents

Standalone consultants for technical AI domains. Invoke when the task requires expertise in voice, memory, or agentic system design — not general engineering judgment.

| Agent | Model | Invoke when... |
|---|---|---|
| `agentic-systems-specialist` | Opus 5 | Designing agentic loops, tool calling schemas, autonomy boundaries, IoT/API orchestration, or action audit trails |
| `ai-memory-specialist` | Opus 5 | Designing RAG pipelines, vector DB selection, memory taxonomy, context injection strategy, or retrieval relevance scoring |
| `voice-ai-specialist` | Opus 5 | Designing voice pipelines, STT/TTS selection, real-time audio streaming, latency budgets, or graceful degradation in audio systems |

```bash
claude --agent agentic-systems-specialist
claude --agent ai-memory-specialist
claude --agent voice-ai-specialist
```

> These agents enter plan mode at the start of every session and require approval before advising — they are consultative, not executors.

---

## Tier 2 — Principal Engineer

The orchestrator. A hybrid Technical Director and Product Manager: it defines **what to build and why**, assembles the right squad, sets technical direction, and surfaces risks. It does not write code.

```bash
claude --agent principal-engineer
```

The principal engineer:
1. Reads your project context files (`PROJECT_BRIEF.md`, `REQUIREMENTS.md`)
2. Reads the domain brief from Tier 1 (if applicable)
3. Makes the platform decision (web, native mobile, cross-platform)
4. Assembles the squad and delegates with scoped, context-rich prompts
5. Tells each specialist which skills to load
6. Synthesizes results back to you

---

## Tier 3 — Engineering Squad

Ten specialists that execute focused work. The principal engineer routes to them; you can also invoke them directly for single-discipline tasks.

```
principal-engineer
  ├── fullstack-engineer      ← any language, any framework, frontend + backend
  ├── devops-engineer         ← CI/CD, infra, containers, networking, observability
  ├── qa-engineer             ← test strategy, test writing, quality gates
  ├── security-engineer       ← threat modeling, security review, vulnerability fixes
  ├── native-ios              ← Swift, SwiftUI, UIKit, App Store
  ├── native-android          ← Kotlin, Jetpack Compose, Play Store
  ├── cross-platform-mobile   ← Flutter (primary), React Native, KMM
  ├── laravel-developer       ← PHP 8.2+, Laravel 11, FilamentPHP v3
  └── desktop-frontend-dev    ← Electron, React, Tailwind, secure IPC
```

| Agent | Model | Role | Invoke directly when... |
|---|---|---|---|
| `principal-engineer` | Opus 5 | Technical Director + PM | You need strategic direction, roadmap, or architecture guidance |
| `fullstack-engineer` | Sonnet 5 | All application code (any language/framework) | Focused implementation or code review task |
| `devops-engineer` | Sonnet 5 | Infrastructure, CI/CD, containers, observability | Focused infra or pipeline task |
| `qa-engineer` | Sonnet 5 | Test strategy, test writing, quality gates | Writing tests or auditing coverage |
| `security-engineer` | Sonnet 5 | Threat modeling, security review | Security audit or sensitive change review |
| `native-ios` | Sonnet 5 | Swift, SwiftUI, UIKit, App Store delivery | iOS-specific implementation or App Store compliance |
| `native-android` | Sonnet 5 | Kotlin, Jetpack Compose, Play Store delivery | Android-specific implementation or Play Store compliance |
| `cross-platform-mobile` | Sonnet 5 | Flutter (primary), React Native, KMM | Shared-codebase mobile app, platform trade-off analysis |
| `laravel-developer` | Sonnet 5 | PHP 8.2+, Laravel 11, FilamentPHP v3, strict types | Laravel backend work, Filament resources, repository-pattern services |
| `desktop-frontend-dev` | Sonnet 5 | Electron + React + Tailwind, main/renderer split | Desktop app work, secure IPC, tray/menus/auto-update |

---

## Skill Catalog

Skills enforce domain standards. Load them via slash command during any task.

### Architecture & Design

| Skill | Command | Purpose |
|---|---|---|
| `system-design-rules` | `/system-design` | API-first design, Mermaid diagrams, trade-off analysis, CAP theorem |
| `clean-architecture` | `/clean-arch` | DDD, Dependency Rule, DTO boundaries, rich domain models |

### Frontend

| Skill | Command | Purpose |
|---|---|---|
| `universal-ui` | `/ui` | Visual hierarchy, contrast rules, touch targets, responsive layout |
| `universal-ux` | `/ux` | State-View decoupling, idempotency, form resilience, UX lifecycle |
| `electron-ipc-protocol` | `/electron-ipc` | Context isolation, preload bridge, channel naming, IPC validation |

### Infrastructure & DevOps

| Skill | Command | Purpose |
|---|---|---|
| `cloud-native` | `/infra` | Stateless containers, IaC idempotency, TLS, graceful degradation |

### Security

| Skill | Command | Purpose |
|---|---|---|
| `secure-by-design` | `/secure` | Zero Trust, PoLP, IDOR prevention, rate limiting, secret management |

### Testing

| Skill | Command | Purpose |
|---|---|---|
| `test-strategy` | `/test-types` | 4 core levels, functional types, non-functional types, Test Pyramid |
| `test-architecture` | `/test-arch` | BDD/ATDD/Contract/Mutation/Property-Based + CI/CD gates |
| `test-report-generator` | `/test-report` | Run suite, triage failures, write dated merge-gate report |

### Product & Analytics

| Skill | Command | Purpose |
|---|---|---|
| `product-midset` | `/product` | Product mindset, FinOps, ROI-driven decisions |
| `business-telemetry` | `/telemetry` | Event schema design, funnel tracking, PII-safe analytics |

### Project Management (Jira)

| Skill | Command | Purpose |
|---|---|---|
| `issue-intake` | `/issue` | Triage a reported bug into a classified Jira ticket |
| `spec-to-backlog` | `/init-project` | Day 0: spec → labelled Jira backlog |
| `backlog-refinement` | `/refine` | Move backlog tickets onto the board, critical-first |
| `task-estimation` | `/estimate` | T-shirt sizing, AI turns estimate, human review effort |
| `local-progress-reporter` | `/report` | Ticket status report with progress bar and blockers |
| `audit-to-backlog` | `/audit` | Post-mortem / code audit → report + backlog tasks |
| `project-audit-reviewer` | `/audit-project` | Full codebase health check, scored by dimension |

### Workflow & Engineering Discipline

| Skill | Command | Purpose |
|---|---|---|
| `git-workflow` | `/git-workflow` | Branching strategy, commit conventions, PR lifecycle |
| `core-engineering` | `/tdd` | TDD Red-Green-Refactor cycle, debugging mantra |
| `anti-regression` | `/surgical` | Blast radius assessment, surgical edits, no silent deletions |
| `ai-output` | `/discipline` | Token efficiency, atomic code blocks, execution safety |
| `project-hygiene` | `/git` | Conventional commits, squash merge, ADR, branch strategy |
| `zero-defect-mindset` | `/zero-defect` | Shift-left: design and threat model before code, not after |
| `think-analyze-isolate` | `/isolate` | Anti-blind-execution for E2E, startup and deploys; anti-loop mandate |

### Leadership & Culture

| Skill | Command | Purpose |
|---|---|---|
| `incident-response` | `/incident` | Triage, rollback, stakeholder comms, blameless RCA |
| `servant-leadership` | `/lead` | Code reviews, mentorship, psychological safety |

### Documentation

| Skill | Command | Purpose |
|---|---|---|
| `standard-playbook-generator` | `/playbook` | Generate anonymized engineering playbooks and workflow guides |

---

## Leader's Guidebook

How to start any project using this toolkit — from domain consultation to squad execution.

### Step 1 — Prepare project context files

Before starting any agent session, create these files in your project root:

```
your-project/
├── PROJECT_BRIEF.md    ← project goals, users, platform, constraints
├── REQUIREMENTS.md     ← functional + non-functional requirements
└── DESIGN.md           ← architecture, tech stack, domain models (optional)
```

Copy the templates from this repo:

```bash
cp drunken-ai-team/templates/PROJECT_BRIEF.md your-project/
cp drunken-ai-team/templates/REQUIREMENTS.md  your-project/
```

Fill them out before running any agent.

### Step 2 — Domain consultation (skip for general projects)

If your project is in a regulated or domain-heavy space, start here.

```bash
claude --agent fintech-specialist
# or
claude --agent insurance-specialist
```

Tell the specialist what you are building. It will output:
- Applicable regulations and standards
- Required data models (with correct field types)
- Architecture constraints and patterns
- Compliance checklist

**Save the output as `DOMAIN_BRIEF.md` in your project root.** This becomes input for the principal engineer.

### Step 3 — Principal engineer kickoff

```bash
claude --agent principal-engineer
```

> "Read `PROJECT_BRIEF.md`, `REQUIREMENTS.md`, and `DOMAIN_BRIEF.md`. Analyze the project and give me a platform strategy, initial ADR, and squad plan."

The principal engineer will:
1. Confirm the platform decision (web / native mobile / cross-platform)
2. Decide which squad agents are needed
3. Run `/init-project` to generate a prioritized backlog from your spec
4. Produce an Architecture Decision Record
5. Brief each specialist on what to build and which skills to load

### Step 4 — Squad execution

Squad agents work from tasks on the kanban board (`backlog/` → `todo/` → `in-progress/` → `done/`).

```bash
# Pick the next task and start work
claude --agent fullstack-engineer
# "Read PROJECT_BRIEF.md and pick up the next task in todo/"

# Run parallel tracks
claude --agent qa-engineer       # write tests
claude --agent security-engineer # threat model
```

---

## Workflows

### Squad Workflow — Greenfield Feature

```mermaid
flowchart TD
    U([User Request]) --> PE[principal-engineer\nAnalyze + Route]
    PE --> |"SDLC: Design"| SD["/system-design\nApprove HLD + API contract"]
    SD --> |"SDLC: Build"| FE[fullstack-engineer\nImplement feature]
    FE --> |Load skills| FS1["clean-architecture\ncore-engineering\nanti-regression"]
    FE --> |"SDLC: Test"| QA[qa-engineer\nWrite tests + coverage report]
    QA --> |Load skills| QS1["test-strategy\ntest-architecture"]
    FE --> |Parallel| SEC[security-engineer\nThreat model + review]
    SEC --> |Load skill| SS1["secure-by-design"]
    QA --> GATE{Quality Gate}
    SEC --> GATE
    GATE --> |Pass| DO[devops-engineer\nCI/CD + deploy]
    DO --> |Load skill| DS1["cloud-native\nsecure-by-design"]
    GATE --> |Fail| FE
    DO --> PE2[principal-engineer\nSynthesize + report to user]
```

### Skill Workflow 1 — Greenfield Project Kickoff

```mermaid
flowchart TD
    A([Project Spec Files]) --> B
    B["/init-project\nspec-to-backlog\nGenerate prioritized backlog"]
    B --> C["/system-design\nApprove HLD + API contracts"]
    C --> D["/clean-arch\nDesign domain layers"]
    D --> E["/test-arch\nChoose test approach"]
    E --> F["/refine\nPromote Critical+High tasks"]
    F --> G["/estimate\nSize tasks"]
    G --> H["/next\nPick highest priority task"]
    H --> I["/tdd\nRed-Green-Refactor"]
    I --> J{Frontend?}
    J -- Yes --> K["/ui + /ux\nLayout + State logic"]
    J -- No --> L["/secure\nThreat model"]
    K --> L
    L --> M["/telemetry\nInstrument user journeys"]
    M --> N["/test-report\nMerge-gate report"]
    N --> O["/git-workflow\nConventional commit"]
    O --> P{More tasks?}
    P -- Yes --> H
    P -- No --> Q["/report\nSprint summary"]
```

### Skill Workflow 2 — Feature Development Cycle

```mermaid
flowchart TD
    A([Feature Request]) --> B["/task\nCreate task file\nNO code yet"]
    B --> C{Architectural\nchange needed?}
    C -- Yes --> D["/system-design\nUpdate HLD + API contract"]
    C -- No --> E
    D --> E["/surgical\nAssess blast radius"]
    E --> F["/tdd\nWrite failing test first"]
    F --> G{Has UI?}
    G -- Yes --> H["/ui\nConstraint + contrast"]
    H --> I["/ux\nState decoupling + error states"]
    G -- No --> J
    I --> J["/secure\nMini threat model"]
    J --> K["/telemetry\nAdd event tracking"]
    K --> L["/test-types\nVerify correct test level"]
    L --> M["/git-workflow\nConventional commit"]
```

### Skill Workflow 3 — Bug Fix

```mermaid
flowchart TD
    A([Bug Report]) --> B["/task\nCreate bug task"]
    B --> C["/tdd\nHypothesis → Trace → Verify"]
    C --> D["/surgical\nBlast radius check"]
    D --> E["/tdd\nWrite failing regression test\nthen apply fix"]
    E --> F["/test-types\nVerify: unit + sanity + smoke"]
    F --> G{Tests pass?}
    G -- No --> C
    G -- Yes --> H["/git-workflow\nfix/: Conventional Commit"]
    H --> I["/test-report\nPre-merge report"]
```

### Skill Workflow 4 — Production Incident Response

```mermaid
flowchart TD
    A([ALERT: Production Down]) --> B["/incident\nTriage — assess blast radius"]
    B --> C{System\nstill active?}
    C -- Yes --> D["Mitigate First\nRollback / Feature flag / Hotfix"]
    C -- No --> E
    D --> E["/incident\nDraft stakeholder update"]
    E --> F["/lead\nCheck on affected engineer\nBlameless culture"]
    F --> G["System Stable"]
    G --> H["/incident\nFull RCA — Timeline + 5 Whys"]
    H --> I["/audit\nGenerate post-mortem report"]
    I --> J["/task\nAuto-generate backlog tasks"]
    J --> K["/refine\nPromote CRITICAL action items"]
```

### Skill Workflow 5 — Code Quality Audit

```mermaid
flowchart TD
    A([Existing Codebase]) --> B["/audit-project\nScore: Architecture, Security\nCode Quality, Dependencies, Docs"]
    B --> C{Score < 3/5\nin any dimension?}
    C -- Yes --> D["/task\nCreate backlog task for each finding"]
    C -- No --> E["Document passing score"]
    D --> F["/refine\nPrioritize remediation tasks"]
    F --> G["/next\nPick top task"]
    G --> H["/surgical\nApply fix with blast radius check"]
    H --> I["/test-types\nVerify no regression"]
    I --> J["/test-report\nBefore/after evidence"]
    J --> K{All critical\nissues resolved?}
    K -- No --> G
    K -- Yes --> L["/playbook\nDocument new standards"]
```

---

## Repository Structure

```
drunken-ai-team/
├── agents/
│   ├── INDEX.md                   # ← GENERATED by sync_agents.sh — do not hand-edit
│   ├── principal-engineer.md      # Orchestrator — routes to specialists
│   ├── fintech-specialist.md      # Fintech domain expert (payments, KYC, PCI-DSS)
│   ├── insurance-specialist.md    # Insurance domain expert (NAIC, HIPAA, claims)
│   ├── agentic-systems-specialist.md # Tool calling, agent loops, autonomy boundaries
│   ├── ai-memory-specialist.md    # RAG, vector stores, long-term memory
│   ├── voice-ai-specialist.md     # STT/TTS, real-time audio, latency budgets
│   ├── fullstack-engineer.md      # Full-stack developer (any language/framework)
│   ├── devops-engineer.md         # CI/CD, infra, containers, networking
│   ├── qa-engineer.md             # Test strategy and test writing
│   ├── security-engineer.md       # Threat modeling and security review
│   ├── native-ios.md              # iOS specialist (Swift, SwiftUI, App Store)
│   ├── native-android.md          # Android specialist (Kotlin, Compose, Play Store)
│   ├── cross-platform-mobile.md   # Flutter/RN/KMM cross-platform specialist
│   ├── laravel-developer.md       # PHP 8.2+ / Laravel 11 / FilamentPHP v3
│   └── desktop-frontend-dev.md    # Electron + React desktop, secure IPC
├── examples/
│   ├── README.md                  # Walkthrough guide
│   ├── 00-setup/                  # Filled project context templates (TaskFlow)
│   ├── 01-spec-to-backlog/        # Output of /init-project
│   ├── 02-backlog-refinement/     # Output of /refine
│   ├── 03-task-estimation/        # Output of /estimate
│   └── contributing/              # Annotated SKILL.md for skill authors
├── scripts/
│   ├── install/                   # ← INSTALL SCRIPTS (deploy to ~/.claude/)
│   │   ├── sync_skills.sh         #   Deploy skills — macOS / Linux
│   │   ├── sync_skills.ps1        #   Deploy skills — Windows (PowerShell)
│   │   ├── sync_agents.sh         #   Deploy agents — macOS / Linux
│   │   └── sync_agents.ps1        #   Deploy agents — Windows (PowerShell)
├── skills/
│   ├── architecture/
│   │   └── system-design-rules/
│   ├── backend/
│   │   └── clean-architecture/
│   ├── documents/
│   │   └── standard-playbook-generator/
│   ├── frontend/
│   │   ├── electron-ipc-protocol/
│   │   ├── universal-ui/
│   │   └── universal-ux/
│   ├── infrastructure/
│   │   └── cloud-native/
│   ├── kanban/
│   │   ├── audit-to-backlog/
│   │   ├── backlog-refinement/
│   │   ├── issue-intake/
│   │   ├── local-progress-reporter/
│   │   ├── spec-to-backlog/
│   │   └── task-estimation/
│   ├── leadership/
│   │   ├── incident-response/
│   │   └── servant-leadership/
│   ├── product/
│   │   ├── business-telemetry/
│   │   └── product-midset/
│   ├── security/
│   │   └── secure-by-design/
│   ├── testing/
│   │   ├── test-architecture/
│   │   └── test-strategy/
│   └── workflow/
│       ├── ai-output/
│       ├── anti-regression/
│       ├── core-engineering/
│       ├── git-workflow/          # ← branching + commit conventions
│       ├── project-audit-reviewer/
│       ├── project-hygiene/
│       ├── test-report-generator/
│       ├── think-analyze-isolate/
│       └── zero-defect-mindset/
├── _not_used/                     # ← RETIRED, KEPT (see _not_used/README.md)
│   ├── skills/                    #   4 orchestration skills, each with RETIRED.md
│   ├── examples/                  #   their recorded outputs
│   ├── scripts/                   #   the local board server and CLI fallback
│   └── templates/                 #   mcp-settings.json, which registered that server
├── templates/
│   ├── CLAUDE.md                  # ← COPY THIS to your project root as CLAUDE.md
│   ├── PROJECT_BRIEF.md           # Project goal, users, platform, constraints
│   └── REQUIREMENTS.md            # Functional + non-functional requirements
├── CLAUDE.md                      # Master instructions for this repo
├── GETTING_STARTED.md             # Step-by-step user guide
└── README.md                      # This file
```

---

## Known Limitations

1. **Token Cost & Latency:** Running multiple agents consumes significant tokens. Handing a specialist a Jira issue key rather than a paraphrased brief keeps each delegation small, but a sequence of them still adds up.
2. **Jira MCP Required for Coordination:** 8 skills and `principal-engineer` need the [companion repo](#companion-repo-optional) — both its MCP server and its `jira-tickets` rules file, which they reference at `~/Projects/drunken-team/...` by absolute path. Clone it elsewhere and that reference dangles; the skills carry the essential ticket rules inline, so they degrade rather than fail, but they will not say they are working from a summary. The other 21 skills stand on their own.
3. **No Claim Expiry:** A Jira assignee never expires. If an agent stops mid-ticket the ticket stays assigned until a human reassigns it — the retired board released a claim after 1800s, and that is the one capability the move to Jira gave up.
4. **Process Heavy for Small Tasks:** The strict three-tier architecture is designed for complex features. Using the full squad for a minor CSS tweak is overkill.
5. **Retry Loops:** Autonomous agents can enter retry cycles. `/isolate` (`think-analyze-isolate`) carries an anti-loop mandate — stop after two identical failures — but monitor execution and intervene if tasks fail repeatedly.

---

## Why This Exists

I'm a computer engineer, but I don't feel confident I'm good enough — and I don't have much time to develop my skills the way I'd like to.

I built this toolkit to learn the fundamentals properly and try building an agent system from my own perspective. It's part study, part experiment.

The skills were drafted by me, then **reviewed and improved with AI assistance** — I used Claude to audit the reasoning, tighten the constraints, and sharpen the output format of each `SKILL.md`.

I'm sharing this because I wanted a review. I'm not sure I'm still where I need to be as a software engineer, and this project is my honest attempt to find out.

---

## Getting Started

New here? Read **[`GETTING_STARTED.md`](./GETTING_STARTED.md)** — step-by-step guide from setup through your first completed task.

**Examples:** [`examples/`](./examples/) walks through the full project lifecycle using a fictional app called **TaskFlow**.
