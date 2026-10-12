# Reference

Detail moved out of README.md and GETTING_STARTED.md so both could stay short (DG-517, round 4).
Copied verbatim from the versions of those two files at the commit this branch forked from
(`origin/develop`, `1459e3a`) — nothing here is paraphrased or re-derived.

## Contents

1. [Skills, agents and the three roles](#skills-agents-and-the-three-roles)
2. [The optional extras — 16 skills, 15 agents](#the-optional-extras--16-skills-15-agents)
3. [The flow, step by step](#the-flow-step-by-step)
4. [Mid-sprint scenarios](#mid-sprint-scenarios)
5. [Known limitations](#known-limitations)
6. [Why this exists](#why-this-exists)

---

## Skills, agents and the three roles

*(from the old README.md, "How the AI layer is organised")*

### Skills vs agents

A **skill** is a standard — how to write a ticket, how to review for security, how to debug. It
loads into whatever agent is already working. An **agent** is a role with its own model, tool set
and system prompt. Skills are the craft; agents are the craftsmen.

### Three roles

```
manager   — reads the project's documents, proposes the plan and its order; the Boss approves
worker    — implements one approved task: test first, smallest change, PR for a human to merge
reviewer  — one round on the plan, tests before implementation, the PR before merge; never merges
```

One agent can play all three, or a team can split them. The fifteen specialist agents that came
before these roles — fintech, insurance, mobile, desktop, voice, AI systems and the original
generalists — live on unchanged as the optional `drunken-extras` plugin in
[`plugins/drunken-extras/`](../plugins/drunken-extras/).

### Skill categories

`flow` · `workflow` · `documents` — the skills the flow uses. The general engineering standards
(architecture, security, UI/UX, testing, cloud, product, leadership) moved unchanged to the optional
`drunken-extras` plugin in [`plugins/drunken-extras/`](../plugins/drunken-extras/).

Full catalogue with triggers: [`skills/INDEX.md`](../skills/INDEX.md).

---

## The optional extras — 16 skills, 15 agents

*(from the old GETTING_STARTED.md, "Older skills and agents")*

### 7 of the 12 skills need nothing else

`/prd`, `/clarify` and `/ddd` write markdown and ask you questions; `project-docs`, `git-workflow`
and `/isolate` are standards that read files and nothing else; `jira-tickets` is the reference for
the shape of a ticket, and it reads as documentation whether or not a server is there. All seven
install and work standalone. The general engineering standards — architecture, security, UI/UX,
testing and the rest — are in the optional `drunken-extras` plugin, and need nothing else either.

The other 5 coordinate work. `/breakdown`, `/replan`, `/build` and `/audit` call `jira_*` tools and name
`drunken-jira-mcp` in their own constraints — without the runtime declared they will **say so and
stop** rather than silently falling back to a file or a shell script. `ask-boss` needs
a notification webhook only for the case where the Boss is not reading the conversation; when they
are, it tells you to just ask them there.

If you have no Jira, you can still run `/prd`, `/clarify` and `/ddd` — skip the next section and
stop the flow at `DOMAIN.md`.

### Older skills and agents

Sixteen general engineering skills and fifteen domain-specialist agents from before the 2.0.0
re-scope live in `plugins/drunken-extras/` but were never wired into any installer (DG-512) — they
reach no machine until you ask for them:

```bash
drunken-install extras            # plan — what would install, by name
drunken-install extras --apply    # write them into ~/.claude/skills and ~/.claude/agents
drunken-install extras --only acronym-namer,laravel-developer --apply   # just these
```

It never removes anything, and a file you already have that differs from the packaged one is
reported, not overwritten. `drunken-install status` lists them too, separately from the core
skills and agents, since they stay optional.

**The 16 skills:**

| skill | one line |
|---|---|
| `acronym-namer` | Generates thematic backronyms for naming a project, bot or module. |
| `business-telemetry` | Structured event tracking and full-funnel analytics standard. |
| `clean-architecture` | Clean Architecture / DDD — layer separation, dependency rules, domain models. |
| `cloud-native` | Cloud-native infra standard — Docker, Kubernetes, CI/CD, IaC. |
| `electron-ipc-protocol` | The IPC contract for Electron apps — context isolation, preload bridge, channel naming. |
| `incident-response` | Crisis leadership for outage mitigation, comms, and blameless RCA. |
| `product-midset` | Product thinking, FinOps, and data-driven feature decisions. |
| `release-notes-writer` | Standardized, markdown-table release notes and tag descriptions. |
| `secure-by-design` | Zero Trust security, network to application layer. |
| `servant-leadership` | Empathetic communication, code review feedback, blameless culture. |
| `standard-playbook-generator` | Generates anonymized engineering playbooks from the skill files themselves. |
| `system-design-rules` | System design standard — trade-offs, API contracts, diagrams before code. |
| `test-architecture` | Architectural test strategy — BDD, ATDD, contract, mutation, property-based. |
| `test-strategy` | Reference for choosing the right test type across four test levels. |
| `universal-ui` | Visual standard against "developer UI" anti-patterns. |
| `universal-ux` | Frontend architecture — state/view separation, resilience, full UX lifecycle. |

**The 15 agents:**

| agent | one line |
|---|---|
| `agentic-systems-specialist` | Agentic AI design, tool-calling architecture, autonomous action boundaries. |
| `ai-memory-specialist` | Long-term memory architecture, RAG pipelines, vector DB selection. |
| `cross-platform-mobile` | Flutter/React Native/Kotlin Multiplatform, shared vs. platform-specific code. |
| `desktop-frontend-dev` | Electron desktop apps — main/renderer split, secure IPC, native menus. |
| `devops-engineer` | Infra, CI/CD, containers, Terraform/Helm/GitHub Actions, observability. |
| `fintech-specialist` | Payments, banking, KYC/AML, PCI-DSS/PSD2/ISO 20022 domain accuracy. |
| `fullstack-engineer` | General frontend/backend implementation, APIs, database design. |
| `insurance-specialist` | Policy, claims, underwriting; NAIC/HIPAA/ACORD domain accuracy. |
| `laravel-developer` | PHP 8.2+/Laravel 11 — repositories, type safety, FilamentPHP v3. |
| `native-android` | Kotlin, Jetpack Compose, Gradle, Play Store delivery. |
| `native-ios` | Swift, SwiftUI, UIKit, Xcode, App Store delivery. |
| `principal-engineer` | Direction, not execution — roadmap, trade-offs, priority, risk. |
| `qa-engineer` | Test strategy, unit/integration/E2E tests, pre-merge quality gates. |
| `security-engineer` | Security review, threat modeling, auth/authz design, dependency risk. |
| `voice-ai-specialist` | Voice pipelines, TTS/STT selection, real-time audio, latency budgets. |

**What is *not* restored, and why** (full detail in `RETIRED.md`): the local-board kanban skills
(`agentic-kanban`, `kanban-io`, `next-task`, `squad-workflow`) are not — a board beside Jira is a
second surface that can disagree with the first (DG-265), and that reason applies regardless of
which installer ships the file. The four vendored, unlicensed skills (`debug-mantra`,
`post-mortem`, `scrutinize`, `management-talk`) are not — they carry no licence and no reachable
upstream, so this repository cannot redistribute them under its own MIT licence (DG-263). Recover
either set from git with the commit named in `RETIRED.md`'s table, e.g.
`git show abe5df1:skills/<name>/SKILL.md` or `git show d41d99d:skills/workflow/<name>/SKILL.md`.

---

## The flow, step by step

*(from the old README.md's arrow-diagram detail, and the old GETTING_STARTED.md's step-by-step)*

```
/prd        →  PRD.md: the brief and the requirements in one file, every requirement
               carrying an id REQ-xxx and a MoSCoW class
/clarify    →  a short ranked list of decisions only the Boss can make, answered back
               into PRD.md
/ddd        →  DOMAIN.md: bounded contexts, shared vocabulary, core entities.
               Each context becomes an Epic
/breakdown  →  the Jira hierarchy — REQ → Epic → Story | Task → Subtask, Story and Task
               both siblings under the Epic — every level labelled req:REQ-xxx. Nothing
               is created until the Boss approves the plan
/build      →  one task, one branch, one PR. The test comes from the ticket's acceptance
               and is seen failing first. The Boss merges
/audit      →  every requirement traced to a task and to a test that passes on the merged
               tree. Gaps become tickets; the day's report is written
/replan     →  a requirement moved after the backlog exists: PRD.md first, then only the
               tickets whose req: label names it. Never orders the work — the Boss does
```

A Task is a vertical slice finishable in a day. Where a project's documents live is the
`project-docs` skill's contract — the project's root `AGENTS.md` is the map, and the defaults
when there is no map are `.ai/PRD.md`, `.ai/DOMAIN.md`, `.ai/audit/`, `docs/` and
`docs/decisions/`.

**Where to deploy is deliberately not part of the standard.** No skill assumes a target; the
first time it matters, the AI asks the project owner and records the answer in that project's
`AGENTS.md`.

Three rules are worth knowing before you read the draft:

- **Ids are allocated once and never reused.** A dropped requirement is struck through and keeps
  its id. Jira labels, branches and merged tickets already point at those numbers; renumbering
  silently repoints history at the wrong requirement.
- **Anything the AI inferred lands under `## Inferred — not yet accepted`**, with no id, until you
  accept it. A generated requirement in the numbered list reads to `/breakdown` as a decision
  nobody made.
- **Nothing is written until you say yes.** You see the whole draft, or the diff against an
  existing PRD, first.

`/breakdown`'s urgency and ticket rules: urgency lands as a **label** — `critical`, `high`,
`medium`, `low`, lower case — mapped from the requirement's MoSCoW class: Must → `critical` or
`high`, Should → `medium`, Could → `low`. **A Won't gets no ticket at all.** Jira's `priority`
field cannot be set on a team-managed project and reads `Medium` on every issue, and there are no
story points, so neither is used.

`/build`'s rules: `jira_start_task` moves the ticket to `IN PROGRESS` and hands back the branch
command; the agent puts `agent:<its name>` in `labels`, because the assignee is the accountable
human, not the thing doing the typing. **The failing run is the evidence, so it gets reported.**
Not "tests added" — the test id and what the assertion actually said:
`AssertionError: expected 401, got 200`. A test written after the fix proves only that it
compiles. **1 task = 1 owner = 1 branch = 1 worktree = 1 PR.**

`/audit`'s gap types: every gap has a name, because they have different causes and different
fixes: `no-ticket` (nobody was ever asked to build it) · `no-test` (built, unproven) ·
`unverified` (green on a branch, never run on the merged tree) · `not-merged` (`DONE`, but the
branch is not in `origin/develop`) · `not-deployed` (merged, and the thing a person can look at is
still older than the merge). One run writes two dated files under the audit directory: the
**audit report** (the engineering half) and the **daily report** (plain language, can be handed
to a customer unedited).

---

## Mid-sprint scenarios

*(from the old GETTING_STARTED.md)*

### A bug arrives while a ticket is in flight

Do **not** interrupt the current ticket.

```
/breakdown
```

A bug comes through the same skill that cut the backlog, and it is a small job there: **one Bug
ticket against the `REQ-xxx` it breaks**, carrying that `req:` label and an urgency label. It does
not re-read the whole PRD, does not re-cut the hierarchy, and does not touch the work in flight.
You decide whether it jumps the queue — pick it up when the current ticket reaches `IN REVIEW`, or
sooner if it outranks what you are holding.

The same applies to a defect noticed *by* `/build` while it is working: its own ticket, and the
task in flight continues. Widening scope mid-branch is how one task stops being finishable in a day.

### End-of-day snapshot

```
/audit
```

The **daily report** it writes is the one to read or forward: what shipped today in plain
language, which requirement each piece serves, what is still open and what it waits on, and where
to go and look at it. Progress is counted in **requirements traced, not tickets closed** — tickets
closed is a number that rises steadily while the thing you asked for is still missing.

---

## Known limitations

*(from the old README.md)*

1. **Token cost and latency.** Running multiple agents consumes significant tokens. Handing a
   specialist a Jira issue key rather than a paraphrased brief keeps each delegation small, but a
   sequence of them still adds up. `drunken-usage` will tell you what a run actually cost.
2. **Coordination needs the MCP server.** `/breakdown`, `/build`, `/audit` and the `manager` role
   need `drunken-jira-mcp`; `ask-boss` needs a notification webhook for the case where the Boss is
   not reading the conversation. Without the server the three flow steps say so and stop rather
   than falling back to a file or a shell script. The other seven skills — `/prd`, `/clarify`,
   `/ddd`, `jira-tickets`, `project-docs`, `git-workflow` and `/isolate` — stand alone;
   `jira-tickets` is the ticket reference those Jira steps follow, and it reads as documentation
   with or without a server.
3. **No claim expiry.** A Jira assignee never expires. If an agent stops mid-ticket the ticket stays
   assigned until a human reassigns it. The retired local board released a claim after 1800s, and
   that is the one capability the move to Jira gave up.
4. **Process-heavy for small tasks.** The three roles are designed for complex features. Running
   manager, worker and reviewer for a CSS tweak is overkill.
5. **Retry loops.** Autonomous agents can enter retry cycles. `/isolate` carries an anti-loop
   mandate — stop after two identical failures — but monitor long runs and intervene.
6. **Not on PyPI.** Nothing has been released yet. Install from a checkout.

---

## Why this exists

*(from the old README.md)*

I wanted to know where AI-assisted delivery actually holds and where it breaks, so I built a system
to find out rather than read about it.

The constraints came first, from 16 years of engineering: work items live in one place, agents never
merge, credentials are references and not tokens. Everything else was built around those.

The skills were drafted by me and reviewed with AI assistance — I used Claude to audit the
reasoning, tighten the constraints, and sharpen the output format of each `SKILL.md`.

Review and criticism are welcome.
