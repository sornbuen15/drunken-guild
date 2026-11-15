# PRD — drunken-guild

## Brief
**What:**         Drunken Guild is a lightweight, evidence-driven, human-governed AI engineering
                  workflow. It helps one person work with coding agents through a process that is
                  appropriate to the work and its risk, rather than applying the largest process
                  to every request.
**Who for:**      One person (the Boss) running a project with one or more AI coding agents doing
                  the work — and the agents themselves, which read this standard.
**Stack:**        Portable SKILL.md methods and role adapters; a Python runtime for install,
                  doctor, safety, registry, usage and optional Jira integration; Git and project
                  documents as durable evidence. No background service is required.
**Constraints:**  Every claim about a standard, agent capability or completed result carries its
                  evidence. A question, discussion, review request or request for a plan is not
                  authorization to implement. The human owns goals, priority, scope and
                  consequential decisions. Guidance and controls are appropriate and sufficient,
                  not minimized for their own sake. (Boss, 2026-09-23; amended 2026-11-02)
**Out of scope:** Runtime orchestration or machine-wide monitoring of every agent/session/subagent;
                  a simulated organization with an agent for every job title; mandatory Jira,
                  Scrum ceremonies, sprints, time-boxes or estimates; autonomous merge or deploy;
                  and blanket multi-provider compatibility claims without provider-specific
                  evidence. Teams of more than one person remain outside the primary use case.

## Requirements

### REQ-001 — The flow follows the standard sequence
**Class:** Must
**Acceptance:** The flow runs in the order the standard uses — requirement, spec, plan, and on to
build and validation — and each stage maps to one step.
**Decided:** 2026-09-23 (Q5-A, amended by Q7) — the flow is seven commands: the six plus
`/replan` as a skill of its own. DG-353's six-command definition is amended accordingly.
**Amended:** 2026-11-02 — REQ-026 selects how much of the flow the work needs. When more than one
stage is required, their dependency order remains the standard sequence; proportionate handling
does not create a second flow or force every request through all seven commands.

### REQ-002 — The agent knows when to use a skill, an agent or an MCP tool
**Class:** Must
**Acceptance:** The Boss describes the work in plain words — e.g. "fix the UX of screen X" or
"design a screen for …" — and the agent picks the matching skill or agent without being told
which one.
The observed problem: agents follow the written rules, but do not work out when a skill, an agent
or an MCP tool is needed.
**Decided:** 2026-09-23 (Q6-A) — measured by a fixed scenario list, run on each supported agent:
two plain-language requests per skill and role (about 30), plus about 5 requests that should
trigger nothing. Each scenario runs 3 times and passes when the right choice is made in at least
2 of 3; every scenario must pass on every agent.
**Decided:** 2026-10-09 — for 2.0.0 the scenario list runs on Claude Code; the other agents follow
REQ-003's deferral.
**Amended:** 2026-10-27 — ordinary conversation needing an explanation, comparison,
progress update, troubleshooting or decision routes to `clear-responses`. Simple
facts, acknowledgments and trivial edits still need no skill. The former
`task-answers` covered only ongoing technical work and is retired.
**Amended:** 2026-11-02 — selection begins with intent and authority, then work type and risk.
The agent distinguishes a question, explanation, analysis, review, plan, implementation request
and external action before selecting a route. It may compose more than one method when the routes
do not conflict; it does not treat discovery of a relevant skill as permission to act.

### REQ-003 — Compatibility is claimed per provider and capability
**Class:** Should
**Acceptance:** The portable standard can be delivered through provider-specific adapters, and
each named provider/version/configuration is classified Verified, Partial, Experimental or
Unsupported from recorded evidence for instruction loading, discovery, routing, tools, subagents,
human gates and safety. No shared file format alone counts as support.
**Decided:** 2026-09-23 (Q1-A) — Aider is supported in full, by preload: `.aider.conf.yml` reads
AGENTS.md and every skill's description at session start, so REQ-002 holds on Aider too. Cost
accepted: those tokens are spent in every Aider session.
**Decided:** 2026-10-09 — the Boss: Antigravity, Aider and Gemini CLI move out of 2.0.0 to 2.1.
2.0.0 is Claude Code in full. Must → Should; the Aider and Antigravity parts of REQ-008 and
REQ-011 go with it. Reason: no evidence yet of where those agents keep their skills (DG-394,
DG-399), and the Boss's own projects run Claude Code.
**Amended:** 2026-11-02 — a provider is classified Verified, Partial, Experimental or Unsupported
for a named version/configuration and scenario. Portable Markdown is a shared source, not proof of
equal discovery, routing, tools, subagents, approvals or safety. Claude Code and Codex are verified
separately first; Antigravity and Aider remain no stronger than their recorded evidence.

### REQ-004 — Replan is its own step
**Class:** Must
**Acceptance:** When a requirement is added, cut or changed, replan re-plans: scope and tickets
are revised against the change.
**Decided:** 2026-09-23 (Q5-A) — `/replan` is its own command.
**Amended:** 2026-11-02 — replan records what was added, changed or removed; identifies accepted
work that remains valid, affected work to revise, and work to retire; checks for duplicate work;
and proposes the changed plan before implementation. It preserves decision evidence and continues
from the current state: change the plan, not restart the project.

### ~~REQ-005 — Refine is its own step, separate from replan~~
**Dropped** 2026-09-23 (Q7, a /prd change): ordering work is the Boss's decision — the person who
knows what comes first is the human. No `/refine` command; the existing rule that the Boss decides <!-- drift-ok: records the dropped /refine step -->
what moves onto the board stands. Id retained.

### REQ-006 — Instruction files follow the real standard
**Class:** Must
**Acceptance:** Where CLAUDE.md is not needed, the project follows the standard instead; any
agent-specific file that remains has cited evidence for why it is still needed.
**Decided:** 2026-09-23 (Q3-A) — DG-349 is amended: a one-line adapter that only points at the
standard is allowed, and is generated by the installer rather than written by hand.
**Decided:** 2026-09-23 (Q9-A) — path-scoped `.claude/rules/` stay as a Claude-only extra for
work on this repository; any rule that must bind every agent moves into the root AGENTS.md.
**Decided:** 2026-10-02 — for a project under the guild these files (AGENTS.md, the CLAUDE.md
adapter, `.claude/`) are that project's AI layer: init copies them in from the config repo
(REQ-020), lists them in `.git/info/exclude`, and the project's own git never tracks them
(REQ-019). AGENTS.md holds instructions to the AI only; facts about the work — what is built, the
stack, requirements, the domain — live in the project repository's own documents (`.ai/PRD.md`,
`.ai/DOMAIN.md`, README). This repository is the exception: here the AI layer is the product and
stays tracked.

### REQ-007 — Nothing points at a file that does not exist
**Class:** Must
**Acceptance:** Pointing an agent at AGENTS.md means something: the file it is pointed at exists
and is read. In a project under the guild, the file is there because init put it there (REQ-020).
Found 2026-09-23: skills, a jira-mcp error message, README and GETTING_STARTED all name a
project's AGENTS.md as "the map"; no template or `drunken-init` creates one, and this repository
has none.
**Decided:** 2026-10-02 — init is the step that makes the pointer true in a project whose AI
layer is kept outside its repository.

### REQ-008 — One central source, installed into each agent its own way
**Class:** Must
**Acceptance:** Skills and agents live in one place anyone can use; each agent gets its own
installed copy in its own location, and an update is applied per agent.
**Decided:** 2026-09-23 (Q2-A) — installed globally, per agent: `~/.claude/skills` (Claude Code),
`~/.gemini/config/skills` (Antigravity), `~/.gemini/skills` (Gemini CLI), and Aider's preload.
One install script and one update script cover every agent; the Boss runs them, as today.
**Decided:** 2026-10-03 — installed and updated by one cross-platform command from a release tag on
GitHub, without cloning the repository; skills and roles ship inside the installed package; the
command is code, never a model call, so installing and updating costs no tokens. GitHub tags are
the only channel for now; PyPI is a later decision. Built after the Layering work (REQ-019,
REQ-020).
**Decided:** 2026-10-09 — for 2.0.0 the install target is `~/.claude/` only; the Antigravity,
Gemini CLI and Aider targets are 2.1 (REQ-003).

### REQ-009 — Gemini CLI is supported too
**Class:** Could
**Acceptance:** The same standard works under Gemini CLI, if it can be included.

### REQ-010 — Skill descriptions say when to use them
**Class:** Must
**Acceptance:** Each skill's description states the situations and plain-language requests it is
for, since every supported agent that selects skills does so from the description.

### REQ-011 — AGENTS.md carries a routing table
**Class:** Must
**Acceptance:** AGENTS.md states, for each situation a description cannot carry — which step
hands to which role, which work must go through which MCP tool — what to use.
**Decided:** 2026-09-23 (Q4-A) — whether Antigravity reads a root AGENTS.md is settled by one real
Antigravity run before the delivery is chosen. Until that run, how Antigravity receives the
routing table is open.
**Decided:** 2026-10-09 — the Antigravity delivery is 2.1 (REQ-003); for 2.0.0 the table in
AGENTS.md read by Claude Code is the whole requirement.

### REQ-012 — Each skill names its next step
**Class:** Must
**Acceptance:** Every flow skill ends by naming the next step and the skills, roles and tools it
calls.

### REQ-013 — A check that every route resolves
**Class:** Must
**Acceptance:** drunken-doctor or CI fails when a routed skill, role or tool does not exist, or
a skill is reachable from nowhere.

### REQ-014 — Agent roles are portable skills
**Class:** Must
**Acceptance:** Manager, worker and reviewer are written as skills; an agent-specific definition
such as `agents/*.md` only points at them.
**Decided:** 2026-09-23 (Q8-A) — the Claude subagents stay, as thin adapters that load the role
skill, for their separate context; Gemini CLI gets the same where it has subagents; on Aider the
roles run in sequence in one session. The installer generates the adapters.
**Amended:** 2026-11-02 — Manager, worker and reviewer are the only core ownership roles. Backend,
QA, security, DevOps and principal-engineering viewpoints are specializations or decision lenses
by default. A specialist becomes a separate agent only when isolated context, separate authority,
independent review or useful parallel work justifies the coordination cost.

### REQ-015 — CLAUDE.md is a one-line adapter
**Class:** Must
**Acceptance:** A project's CLAUDE.md contains `@AGENTS.md` and nothing that AGENTS.md does not.
Evidence: Claude Code reads AGENTS.md on its own only from v2.1.277, and never while a CLAUDE.md
is present; this machine runs 2.1.270. Anthropic's docs say keep the import while any session
cannot load AGENTS.md directly (https://code.claude.com/docs/en/memory).
**Decided:** 2026-09-23 (Q3-A) — allowed under the amended DG-349; the installer generates it.
**Decided:** 2026-10-02 — still one line and still generated, now by init from the config repo
(REQ-020); in a project under the guild it is excluded from the project's git (REQ-019).

### REQ-016 — Constitution lives in the PRD brief
**Class:** Must
**Acceptance:** The project-level agreement — what, who for, stack, constraints — is the PRD's
Brief; no separate constitution file exists. The roadmap is Jira.

### REQ-017 — A project's lessons flow back into the guild
**Class:** Should
**Acceptance:** At the end of a run, the lessons a project has recorded are proposed back to the
guild as tickets — each naming whether it is a skill, a rule or a template change — for the Boss
to approve. Nothing authors a skill or rule by itself, and nothing is proposed without evidence
from the project's own work.
**Decided:** 2026-10-01 — the Boss approved a retro step at the end of `/audit` (DG-409). Found
in a project run under the guild: nine lessons in its own memory, none of which reached the guild.

### REQ-018 — Dependencies are audited on a schedule, in every language a project uses
**Class:** Should
**Acceptance:** Every project under the guild audits its dependencies on a schedule, independent
of PRs, for each language it uses (Python, PHP/composer, Node/npm at least). A finding fails the
run visibly and is turned into a ticket, raised by a person or agent. Nothing is auto-merged or
auto-upgraded.
**Decided:** 2026-10-01 — the Boss approved a scheduled, per-language audit after the pyjwt and
virtualenv advisories failed CI on every branch at once (DG-413); CI only audits on a PR or push,
so a quiet week hides a vulnerable tree.

### REQ-019 — The guild never mixes into a project's repository
**Class:** Must
**Acceptance:** In a project under the guild, the project's own git tracks none of its AI layer —
AGENTS.md, CLAUDE.md, `.claude/`, hook and Jira configuration, anything about how the AI works
rather than what is built — and drunken-doctor fails when it does.
**Decided:** 2026-10-02 — the Boss: applied to any project, the guild must never mix in; a project
may be handed to a customer as source code, or be a private product. This repository is exempt
(REQ-006).
**Clarified:** 2026-10-13 — this is a repository hygiene policy for projects that opt into the
guild's private AI layer. It means those files are not committed to the project repository; it
does not authorize deleting `AGENTS.md`, `CLAUDE.md` or other instruction files. Migration only
changes Git tracking/excludes after explicit owner approval, preserves the files on disk, and backs
them up. For a project that does not use the guild, its existing instruction files and tracking
policy belong to that project; an agent must leave them alone unless the owner asks for a change.
**Decided:** 2026-10-10 — a project has **no `.mcp.json` at all** (neither option in
`core/ai_layer.py`: not committed, not excluded). The file would hold one line naming a command,
and `drunken-jira-mcp` already serves every project, because each `jira_*` tool takes the
registry project id as its first argument. The server is declared once per machine, at the
user level of each agent (Claude Code: `claude mcp add --scope user`), by the install step
(GETTING_STARTED). Init stops writing the file and `drunken-doctor` flags a tracked one as
AI-layer content (DG-457). The Boss had said so more than once; this line is so it is not asked
again.

### REQ-020 — A project's AI layer comes from one private config repo
**Class:** Must
**Acceptance:** One private GitHub config repository holds the AI layer of every project. In a
project folder, one init step copies that project's layer in from it, lists the copied files in
`.git/info/exclude`, sets up the hooks and the Jira configuration, and only then does the agent
read AGENTS.md.
**Decided:** 2026-10-02 — one config repo for all projects, not one each; files are copied, not
symlinked; hidden from git through `.git/info/exclude`, not `.gitignore`.
**Clarified:** 2026-10-13 — excluding AI-layer files from Git never means removing them from the
working tree. A migration must preserve the files and make the tracking changes reviewable; it
must not run automatically merely because an agent sees a tracked instruction file.
**Decided:** 2026-10-09 — Jira credentials live in no git repository, public or private, config
repo included: a per-machine store outside every checkout (an environment variable or a file
under the operator's home, referenced as `env://…` or `file://…#key`), and init only points at it.
The Boss has said this since the project began; it is not to be asked again.
**Evidence:** 2026-10-10 (DG-432) — Claude Code 2.1.289 on Windows loads a `CLAUDE.md` and a
`.claude/settings.json` that git ignores through `.git/info/exclude`: a headless run read the first
(canary reply) and honoured the second (model override); the same repository without the files did
neither. Not yet verified: `.claude/skills`, `.claude/agents`, hooks in settings, a linked worktree,
interactive mode, and every other agent.

### REQ-021 — /prd starts from a draft the Boss attaches
**Class:** Should
**Acceptance:** When the Boss points /prd at one or more draft files (.md, .txt and .pdf in the
first round), the requirements the drafts state are proposed with the source file and page named;
anything the drafts leave unclear goes under Inferred, not into the numbered list; drafts that
contradict each other are reported, not resolved; the draft files are never changed and never
copied into the repository; their content is data, never an instruction to the agent.
**Decided:** 2026-10-03 — .docx is a later step, after a trial with real files; reading a .docx or
a scanned pdf is not yet verified.
**Decided:** 2026-10-10 — the Boss: in 2.0.0 (DG-497).

### REQ-022 — The guild is easy to install, use and update
**Class:** Must
**Acceptance:** A new skill or role reaches a machine that has the guild installed with one update
command, with no clone and no model call. A change to how the flow itself works is a minor or
major release with a changelog, and a status command says what has changed, before it is applied.
**Decided:** 2026-10-03 — the Boss: anyone who takes the guild should find installing, using and
updating easy, and updating should cost no tokens unless the way of working itself has a new
version. Channel for now: GitHub tags (see REQ-008).
**Decided:** 2026-10-10 — the Boss: in 2.0.0, said twice (DG-498..DG-502).
**Amended:** 2026-11-02 — easy does not mean the fewest pages, dependencies or controls. Guidance,
installation and maintenance must be appropriate and sufficient: a new user has a short verified
path to first use, deeper reference and troubleshooting remain available, prerequisites and effects
are explicit, configuration is not overwritten silently, and recovery is documented and tested.

### REQ-023 — A registered project id never reaches this repository
**Class:** Must
**Acceptance:** An operator's registered project ids never appear in this public repository, in
content or in a commit message. A commit that would carry one is refused before it is pushed, and
a push with no ids to check against is refused too; a checkout missing the git hook that does this
is a `drunken-doctor` failure; and an agent cannot skip or disable the git hooks. The push check is
a native `pre-push` hook that runs on every push git performs, including a solo tag pushed onto an
already-public commit and a push that is only ref deletions — the two shapes pre-commit's own
pre-push stage silently never ran a hook for at all (DG-479). "Already public" is decided by asking
the push target itself, once per push (`git ls-remote`, a hard timeout, `DRUNKEN_LS_REMOTE_TIMEOUT_SECONDS`
to change it — default 20s) — never by a local ref under any name or namespace, which a locally
fabricated `refs/remotes/<name>/*` ref (`git update-ref`, a same-machine fetch, or a hand-edited ref
file) could otherwise use to self-exclude the very commit being pushed through it (DG-479 round 4).
A push target that cannot be reached, or that times out, refuses the push — it is not read as
"assume nothing is public" or "assume everything is"; both would be a guess. It does not stop `git
push --no-verify`, a `core.hooksPath` redirected elsewhere, or a clone that never ran the installer
at all; those are accepted limits, caught afterwards by CI and the secret scan, which cannot
unpublish what already went out. `refs/notes/*` and any other ref outside `refs/heads`/`refs/tags`
are scanned exactly like any other ref the hook sees on its own stdin — the scan only cares about
the commit (or tag) object a pushed ref's own sha resolves to, never its ref name or namespace — so
a clean notes push passes quietly and a dirty one is refused, the same as any branch or tag.
**Decided:** 2026-10-06 — the Boss, after the 2026-09-23 leak (#89, #93) was found still
uncleaned. Both leaks were test fixtures.
**Decided:** 2026-10-09 — the Boss: DG-479_DECISION.md option A (narrow) plus D. pre-commit's own
pre-push stage never invokes any hook at all for a solo tag on an already-public commit or a
delete-only push (`hook_impl._pre_push_ns` returns "nothing to push" before `run()` is ever
reached, so no config knob can change it — tried and confirmed not possible). The fix is a native
`pre-push` hook, the sole owner of the stage so it never races pre-commit's own managed hooks for
it; DG-480 (a brand-new repository's first push being refused) is closed by the same hook for free,
since it reads the real ref lines off git's own stdin rather than taking pre-commit's separate
"all_files, no FROM/TO" path. `--no-verify`, a redirected `core.hooksPath`, and a human running an
unhooked clone remain open on purpose — no hook can close any of those — and are named above rather
than implied.
**Decided:** 2026-10-09 — the Boss: option A for "already public" too, after review found a local
ref under `refs/remotes/<the real configured remote>/*` — not merely an unrelated namespace, round
3's own fix — could still be forged to self-exclude a commit from the very push publishing it. No
local ref, under any name, is trusted for this any more: the push target is asked directly, live,
every push.
**Decided:** 2026-10-10 — the Boss: three gaps found while hardening this are **known limits of
2.0.0**, not blockers, because the floor guards against an agent's mistake, not against a person
or agent set on getting round it, and none of them can leak a project id today:
- DG-490 — the `ls-remote` timeout is not honoured on Windows when the transport leaves an
  orphaned child holding the pipes (a push waits ~21 s instead of 3 s; it still refuses, it is
  only slow).
- DG-491 — the git-dir substitution rule pairs a mention in quoted text or a heredoc with any
  unrelated mutating verb (it denies too much, never too little).
- DG-496 — a `cd` into the hooks directory in one Bash call followed by a bare relative write in
  a later call is not denied; it takes an agent deliberately making two calls.
They are ticketed and parked in the backlog for 2.0.x. Anything that makes one of them leak an
id is a Bug, not a limit.

### REQ-024 — Every step starts from what already exists
**Class:** Must
**Acceptance:** Each step of the flow runs in a project whatever state it finds — a new folder,
code with no PRD, a PRD in another shape, a Jira backlog cut by someone else, or a single task
or bug — without asking the Boss whether the step may be skipped. The step reads what is there
(code, README, an older requirements file, existing tickets labelled or not), names it as its
starting point, and finishes fast when it has nothing to change ("nothing to clarify",
"no name changes", "no new tickets"). No step refuses to run because a document another step
would have written is absent; it reports the absence and produces the smallest version it can.
`/breakdown` searches existing tickets before `jira_create_issue` and never creates a duplicate.
Found 2026-10-09: every flow skill except `/prd` stops at "no PRD.md"; `/ddd` forbids reading a
codebase; `/breakdown` never searches before creating. 1.3.0 in other projects on this machine
is unusable on an existing project for exactly this reason.
**Decided:** 2026-10-09 — the Boss: new or existing project, with or without requirements,
small or large — all of it must work; the steps do not change, the size of each step does.

### REQ-025 — Agent compatibility claims have agent-specific evidence
**Class:** Must
**Acceptance:** Documentation distinguishes instruction loading, skill access, discovery, routing,
tool availability, human gates and token data for each named agent. An agent is marked supported
only for versions and scenarios with recorded evidence; unavailable token data is reported as such.
**Decided:** 2026-10-12 — the Boss approved validating the shared workflow per agent and avoiding
general compatibility claims without evidence.

### REQ-026 — The workflow is proportionate to the work and its risk
**Class:** Must
**Acceptance:** The agent selects a Fast, Standard or Controlled path and states the reason. Fast
keeps the necessary context, change and verification for low-risk reversible work; Standard adds
planning and review where coordination is useful; Controlled adds explicit impact analysis,
approval and independent verification for security, data, architecture, deployment or hard-to-
reverse work. A shorter path never removes an applicable acceptance criterion or safety gate, and
the human may change the path.

### REQ-027 — Discussion is not authorization
**Class:** Must
**Acceptance:** A question receives an answer; a request to analyse or review produces findings; a
request for a plan produces a proposal. None changes files or external state. Implementation begins
only from an instruction to act and remains inside its stated scope. When authority is ambiguous
and the action would materially change state, the agent asks first. The completion report names the
authorising request, changed surfaces and observed verification.

### REQ-028 — The human remains in the loop
**Class:** Must
**Acceptance:** The human owns the goal, priority, accepted requirements and consequential choices.
The agent prepares evidence and recommendations without expanding scope. Destructive, irreversible,
merge-worthy, deployment and other designated approval actions wait for a current human decision.
The human can stop, redirect or reject work at every boundary without restarting valid completed
work.

### REQ-029 — Engineering claims distinguish evidence from inference
**Class:** Must
**Acceptance:** Investigation and reporting distinguish observed facts, expected and actual results,
hypotheses, unknowns, tests and conclusions inferred from evidence. "Passed", "fixed", "supported",
"deployed" and estimates are used only with the evidence appropriate to that claim. A change is not
called successful until its intended result and relevant regression boundary have been checked.

### REQ-030 — Problem solving is a verifiable loop
**Class:** Must
**Acceptance:** A problem workflow records the symptom and baseline; evaluates impact, risk and
urgency; tests hypotheses; compares viable remedies and side effects; applies only an authorised
remedy; verifies the result and relevant regressions; and records prevention when justified. An
unknown cause remains unknown rather than becoming a confident narrative.

### REQ-031 — Communication is clear, bounded and fit for its reader
**Class:** Must
**Acceptance:** Explanations lead with the conclusion and evidence; status reports say completed,
active, blocked and next; change reports say what changed, where, why and how it was verified;
decisions present options, trade-offs and a recommendation. Comments, tickets, pull requests,
release notes and review findings use their own reader-appropriate forms. Responses stop when the
decision-relevant information is complete and do not repeat a conclusion as filler.

### REQ-032 — A skill is one bounded method
**Class:** Must
**Acceptance:** Every skill states when to use it, when not to use it, required input, produced
output, completion evidence, authority boundary and hand-off. One policy has one owning source;
wrappers point to it rather than restating it. The index aids discovery but is not activation.
Positive, paraphrased, negative and composition scenarios prove that descriptions and routes select
the skill without relying on one keyword form.

### REQ-033 — Safety has three explicit control levels
**Class:** Must
**Acceptance:** The project maintains a tested matrix of hard-denied actions, actions requiring
human approval, and safe autonomous actions inside an authorised scope. Enforceable controls live
in tools or guards rather than model memory alone. No path may weaken secret protection, Git hooks,
protected delivery targets, the no-agent-merge rule or the no-autonomous-deploy rule.

### REQ-034 — Workflow value is measured before the system expands
**Class:** Must
**Acceptance:** Changes to workflow, skills, roles or runtime components are evaluated against time
to delivery, workflow overhead, rework, defects/regressions, routing accuracy and human correction;
token or monetary cost is included only when observable. A component that adds overhead without
evidence of reduced time, error or risk is simplified, retired or kept experimental rather than
expanded because it already exists.

### REQ-035 — Core operation requires no background product surface
**Class:** Must
**Acceptance:** Requirements, planning, building, review, audit and replan work without a daemon,
dashboard or database service. Jira, usage estimation and other integrations are optional. The core
may use installed files, project documents, Git and tools invoked for the current task; it does not
reintroduce Hub or claim machine-wide observation through another name.

### REQ-036 — Guidance is layered, sufficient and verified
**Class:** Must
**Acceptance:** Documentation provides a tested quick start, daily workflow, safety/approval guide,
provider-specific setup, troubleshooting/recovery and detailed reference. A reader can reach first
success without reading every page, while consequential prerequisites, effects and limits remain
available. Commands and internal links are checked against the release they document; brevity by
itself is not a pass criterion.

## 2026-11-02 reframe traceability

### Existing requirement disposition

| existing requirement | disposition | reason |
|---|---|---|
| REQ-001 | keep | The seven-step standard remains the shared flow; REQ-026 makes its use proportionate. |
| REQ-002 | amend | Intent and authority now precede skill, role and tool selection. |
| REQ-003 | amend | Compatibility becomes provider-, version- and capability-specific. |
| REQ-004 | amend | Replan preserves valid work and proposes only the affected change. |
| REQ-005 | remain dropped | The human still owns ordering; no refine ceremony returns. |
| REQ-006–008 | keep | Standard instructions, resolving pointers and one distributable source remain necessary. |
| REQ-009 | retain under REQ-003/025 | Gemini CLI is a possible provider, not a blanket compatibility promise. |
| REQ-010–013 | keep | Descriptions, routes, next-step ownership and route resolution remain the activation base. |
| REQ-014 | amend | Three core roles remain; technical personas become specializations by default. |
| REQ-015–021 | keep | Adapters, PRD brief, learning, audits, layering, config and draft intake are unaffected. |
| REQ-022 | amend | Easy means appropriate, sufficient, verified and recoverable, not merely shorter. |
| REQ-023–025 | keep | Privacy, existing-project operation and evidence-specific compatibility remain constraints. |
| REQ-037 | remain dropped | The Hub failed its value boundary; REQ-035 prevents a renamed replacement. |

### New decisions and delivery impact

| decision | requirement effect | delivery impact |
|---|---|---|
| Appropriate and sufficient, not minimal for its own sake | amend REQ-022; add REQ-026 and REQ-036 | installer, doctor, getting-started and reference evidence |
| A question is not an instruction | amend REQ-002; add REQ-027 | routing, response and authority scenarios |
| Human-governed work | add REQ-028 and REQ-033 | approval protocol, deny floor and action matrix |
| Engineer/scientist behaviour | add REQ-029 and REQ-030 | investigation and verification methods |
| Clear communication by artifact | add REQ-031 | clear-responses and artifact-specific references |
| Skills activate and compose without duplication | amend REQ-002 and REQ-014; add REQ-032 | skill audit, role adapters and routing evaluation |
| Requirement change continues from current state | amend REQ-004 | replan and duplicate-work checks |
| Portability is evidence-specific | amend REQ-003; retain REQ-025 | Claude/Codex evidence first; other providers classified honestly |
| Value before expansion | add REQ-034 and REQ-035; retain dropped REQ-037 | no Hub replacement; establish a measurement baseline |

### ~~REQ-037 — Discover all live local agent sessions~~
**Dropped** 2026-11-01 — the owner retired the Hub after review found that its
provider-limited observations did not deliver the machine-wide agent, session,
subagent, task, and ticket visibility needed to justify operating it. The shipped
implementation is retained in Git history; no replacement monitor is planned.

**Former class:** Must
**Acceptance:** On Windows and macOS, Hub displays every live coding-agent session discoverable on the machine regardless of vendor or project registration, identifies project registration separately, distinguishes idle and busy when the source reports them, labels unavailable values unknown, and retains no transcripts.
**Amended:** 2026-10-25 — the owner requests a local browser dashboard for easier
monitoring. Provide session/project filters, session details, source coverage and
observation times over the existing discovery contract. Keep stored metadata and
demonstration records distinct from live observations; unavailable task/status
values remain unknown. Initial delivery is read-only and retains the CLI.
**Amended:** 2026-10-26 — detect known agent CLI entry points on the Dashboard
server PATH (initially Claude, Codex, Aider and Antigravity), separately from session
adapter capability. A missing command means not found on that PATH, not proof
that the tool is absent from the machine. CLI presence does not imply login or
a running session. Keep checks lightweight and do not launch agents to inventory them.
The owner selects Antigravity, replacing Gemini CLI in this Dashboard inventory;
this does not remove historical integration requirements elsewhere.
**Amended:** 2026-10-27 — allow the owner to submit, follow up on and cancel
Guild-owned Claude Code and Codex tasks from the Dashboard. Create a separate
Git worktree per new task, retain a bounded task/result history and show the
project, current activity and reported subagents. Never claim control of an
unowned desktop or terminal session. Codex subagents require a separate
app-server metadata query because the CLI JSON stream can omit child creation;
report unknown coverage honestly. Remote access may use an existing Tailscale
Serve proxy with an exact HTTPS origin and an allowlisted Tailscale login. Keep
the backend on loopback and leave existing Serve routes intact.

## Inferred — not yet accepted
- (none — all accepted by the Boss, 2026-09-23)
- A user-level SessionStart hook that tells the agent to run init in a folder the guild does not
  yet know. (Proposed 2026-10-02; the Boss has not accepted it.)

## Open — for /clarify
- REQ-011 — result of the Antigravity run (Q4-A). Carry: changes one adapter.
- REQ-014 — whether Antigravity has subagents: not yet checked. Carry: one adapter.
- REQ-018 — which further languages (Go, Ruby) are in scope.
- REQ-019 — how a project that already commits its AI layer is migrated.
- REQ-008, REQ-022 — whether shipping skills inside the installed package changes how
  drunken-doctor and the tests read them (today they read `skills/` in the repository): not yet
  assessed.
- REQ-008, REQ-022 — agent-specific discovery and installation remain unverified until each
  agent's version/configuration is exercised using the evidence protocol in
  `docs/AGENT-COMPATIBILITY.md`.
