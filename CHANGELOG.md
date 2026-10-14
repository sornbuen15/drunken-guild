# Changelog

A change to **how the flow itself works** is a minor or major release and has an entry here
(REQ-022). `drunken-install status` quotes the newest entry before an update is applied.

The top heading is the version this tree declares in `pyproject.toml`; `Unreleased` stands in
while a release is being prepared, and is renamed to the version when it is tagged
(`tests/test_install_agents.py::TestTheChangelog`).

## Unreleased

Optional practices help teams reason about SDLC work without imposing company policy.

### Added
- `deployment-preparation` prepares a target-specific preflight, verification and recovery plan.
  It does not deploy, and is available with the other optional extras.
- `/session-checkpoint` carries optional handoff context in an ignored, machine-local file; only its
  blank template is tracked.
- `docs/OPTIONAL-SDLC-PRACTICES.md` maps optional security, release and deployment practices to
  the skills and checks already available in the repository.

### Changed
- `secure-by-design` now offers optional risk assessment, threat modeling, development checks,
  focused review and configuration assessment. The reviewer role offers a focused security review
  when requested or required by project guidance; it does not impose a default gate.
- `release-notes-writer` prepares release notes and a project-specific readiness summary. It does
  not impose a version scheme or tag policy, and release preparation stays separate from deployment.
- Skill routing distinguishes release preparation, deployment preparation and deployment requests
  instead of treating the word "release" as a deployment action.
- Jira-backed planning can move selected backlog work to the active board when the owner delegates
  a same-day assessment and immediate start; other backlog moves still need the owner's decision.

## 2.0.3 — 2026-10-12

The per-prompt routing hook stops over-triggering and sends build work to the worker agent.

### Fixed
- `drunken-install route` no longer over-triggers on a pasted log, a quoted block or fenced
  code: it now considers only the first 400 characters of a prompt, strips log-looking lines,
  quoted lines and `<pasted_content>`-style blocks before matching, and caps a nudge at the two
  highest-scoring categories and five names in total — a pasted `drunken-doctor` log used to
  nominate as many as 10 skills in one run. It also tells a role (`worker`, `reviewer`,
  `manager` — installed as both a skill and an agent) apart from a plain skill: a role is named
  through the Agent tool with its `subagent_type`, everything else through the Skill tool
  (DG-521).
- A Thai or English ticket hand-off ("ทำ ticket ALPHA-12 ให้หน่อย", "implement ticket ALPHA-12")
  routes to `build` and the `worker` agent; a ticket key needs a Jira-looking shape (`utf-8` is not
  one), and bare "plan" or "architecture" without a work word no longer nominates anything. A real
  request after a pasted log is still found (noise is stripped before the 400-character window).

### Changed
- The documents tell one story: README (what and install), GETTING_STARTED (first project), a 150-line
  operator guide that opens with the same product description, and CONTRIBUTING for the clone path.
  The guide no longer tells a tag-install user to `git clone`, no longer asks for a `.mcp.json` in
  every checkout (declare the MCP server once per machine), shows PowerShell beside bash, and points
  at `drunken-doctor` instead of listing its checks. Stale cross-references and references to the
  retired board and approval servers are gone. `docs/REFERENCE.md` keeps the long detail word for
  word (DG-517, DG-522).
- `scripts/check_doc_drift.py` now fails on a broken relative link or anchor, a `§` reference to a
  section that does not exist, a gap in numbered headings, and a claim that the registry can be
  committed (DG-522).

### Measured
Scratch runs of `claude -p` on a Thai build ticket with edits allowed, four runs per side and the
same 53 skills and 24 agents available: without the hook the `worker` agent ran in 1 of 4 and the
test skills in 0 of 4; with it, 4 of 4 and 4 of 4. The `reviewer` agent ran in 0 of 4 both ways.
Cost per run rose from about $0.21 to $0.43 on average (range $0.13 to $0.68), because the work now
runs in an agent. Small samples on one small task: a direction, not a price.

## 2.0.2 — 2026-10-12

Makes the guild's skills and agents reach a session, brings the older ones back, and fixes what
the installed 2.0.1 showed on real projects. Delivery is proven; whether the model then follows
the routing is measured below (scratch runs, three per cell, so a direction, not a proof).

### Added
- `drunken-install context` prints the routing rule and the skills and agents actually installed
  (names only, at most 2,500 characters, never raises), and `drunken-install hook` (plan by
  default, `--apply`, `--remove`) puts it into the user Claude settings as a SessionStart hook, so
  every session gets it with or without a project `AGENTS.md`. The hook records the absolute path
  of the executable, backs up `settings.json` first, refuses invalid JSON, never touches other
  keys, and `drunken-doctor` (`routes.session_hook`) runs the recorded command to prove it works
  (DG-513). `scripts/measure_routing.py` measures which Skill and Agent tools a session really calls.
- `drunken-install extras` installs the 16 older skills (including `universal-ui`,
  `universal-ux`) and 15 specialist agents (including `laravel-developer`, `qa-engineer`,
  `security-engineer`) that lived in `plugins/drunken-extras` and were installed nowhere. Plan by
  default, `--apply` writes, `--only` picks names, nothing is removed or overwritten. Retired items
  (local-board kanban skills, unlicensed packs) are not restored (DG-512).

- `drunken-install route` is a `UserPromptSubmit` hook: it matches the prompt against a Thai and
  English keyword table (one data file, `src/core/data/route_keywords.json`) and names the installed
  skills or agents to call, at most 600 characters, nothing for a prompt that matches nothing, never
  echoing the prompt. `hook --apply` and `--remove` now manage both hooks; `drunken-doctor` checks
  `routes.prompt_hook` (DG-515).
- `scripts/release_smoke.py` builds the wheel, installs it into a throwaway venv under a temp home and
  checks install, extras, prune, both hooks, the doctor and that the real settings are untouched; it
  is step 0 of the release checklist in CONTRIBUTING.md (DG-514).
- `scripts/check_skill_size.py` keeps skills (120 lines) and agents (100 lines) light: a new file over
  the limit fails and a file already over may only shrink (DG-516).
- `drunken-doctor`'s `processes.orphans` check lists leftover session processes with a dead
  parent and a known-leftover command line (a shell snapshot, a stdin interpreter, `uv run`,
  `drunken-jira-mcp`), and **lock holders** — a process whose executable sits inside the installed
  guild tool, whatever its parent, labeled `orphan` or `held by session <ppid>`. `drunken-install
  reap` plans the same list; `--apply` re-verifies every id (same pid, same start time, parent
  state unchanged) immediately before terminating it, terminates orphans unconditionally, and
  terminates a held lock holder only with `--include-held` — stopping one can make Jira tools
  unavailable until the session restarts it. Nothing is ever killed by inference, and an unreadable
  process table refuses rather than reporting a clean, unchecked list. `drunken-install
  skills`/`agents`/`all` print a one-line warning, before writing anything, naming how many lock
  holders exist and the exact command to clear them (DG-518).
- README.md is now 54 lines with the seven-command flow diagram and a five-command install, GETTING_STARTED.md is 100 lines, and everything they used to carry moved word for word into `docs/REFERENCE.md` and `REPOSITORY_MAP.md`; the new `concise-docs` skill covers guides, test cases, status reports, release notes, tickets and chat summaries (DG-517).

### Fixed
- After `extras --apply`, `status` called all 16 extras "retired" and `skills --prune --prune-apply`
  would have deleted them; the retired list no longer names them. The hook recorded the first
  `drunken-install` on PATH instead of the one running; it now records the running executable, as an
  absolute path (DG-514).
- `drunken-doctor` no longer warns forever about `~/.drunken` permissions on Windows: it reads the
  ACL from `icacls` instead of a synthesized mode, and an ACL that still grants another account
  warns (DG-509).
- An empty, BOM-prefixed or truncated `projects.json` gives a typed error naming the file instead of a
  traceback, and a registry with a `version` but no `projects` object is refused (DG-507).
- `content_scan` reads `.claude`/`.gemini` at any depth, a differently cased `.Claude`, and a
  nested `.mcp.json`; a real `.venv`, `node_modules` or `vendor` install is still stepped over
  (DG-508).
- The install documents pinned `v2.0.0`, left out `extras` and `hook`, did not say to close every Claude window before `uv tool install --force` on Windows, and taught moving a project's AI layer out of git without saying that a new git worktree then has no `AGENTS.md` (DG-511); README and GETTING_STARTED now say all four.
- The installer no longer explodes on two Windows junctions that point at each other: it walks
  without entering a link and still refuses it (DG-510).

### Known and open
- Routing, measured with `claude -p` in scratch projects: on an existing project the session-start
  text alone made 0 of 24 UI and test runs call a skill; with the prompt hook, UI, test and security
  prompts called the matching skill in 12 of 12 runs, and a bug-fix prompt in 1 of 3. A new-project
  prompt called `/prd` in about 10 of 12 runs with or without a hook. Agents (`worker`, `reviewer`)
  were not measured. The keyword table is the weak spot: a prompt it does not match gets no help.
- A project's AI layer is absent in a new git worktree when it is untracked (DG-511).
- The hang first reported for one installer test on Windows did not reproduce and is not explained
  (DG-510); locale-dependent `icacls` parsing and a real domain-joined machine are unverified (DG-509).
- The server-side registry reader still silently drops a version-2-looking file without `projects`.

## 2.0.1 — 2026-10-11

Found by the first `drunken-doctor` run of the installed 2.0.0 on real projects.

### Fixed
- `drunken-doctor` no longer fails this repository's own checkout when it runs from the installed
  package, and the exemption needs the registry id `drunken-guild` as well as the checkout's own
  pyproject (a pyproject alone is a string any project controls) (DG-503).
- `content_scan` no longer reads a third-party package's `CLAUDE.md` inside a project's `.venv`,
  `node_modules` or Composer `vendor` as the project's own AI layer. A directory is stepped over only
  by a marker the installer writes, never by name, and never when it is `.claude`/`.gemini` at the
  root, directly holds an instruction file, or has a git-tracked one below it (DG-505).

### Added
- `drunken-init --remove-project <id>` removes a registry entry after copying the whole registry to
  `projects.json.bak-<UTC time>`; it refuses an unknown or empty id, writes through a symlinked
  registry, swaps the file atomically, and cannot be combined with another action (DG-506).

### Known and open
- An unreadable or empty registry still raises a traceback (DG-507); `.claude`, `.mcp.json` nested or
  in another case are not read by `content_scan` (DG-508); a pyproject line scan can be fooled by a
  multiline string (DG-504); DG-490, DG-491, DG-496 as in 2.0.0.

## 2.0.0 — 2026-10-11

The flow is one standard that an agent can run on any project.

### The flow (REQ-001, REQ-004, REQ-012, REQ-021, REQ-024)
- Seven steps: `/prd` → `/clarify` → `/ddd` → `/breakdown` → `/build` → `/audit`, and `/replan`.
- Every step starts from what a project already has — a new folder, code with no PRD, requirements
  in another shape, a Jira backlog someone else cut, or a single task or bug — and finishes fast when
  it has nothing to change. No step stops at "no PRD.md".
- `/breakdown` searches Jira first and binds an existing ticket instead of creating a duplicate.
- `/prd` reads `.md`, `.txt` and `.pdf` drafts as data: it cites the page, sends the unclear to
  Inferred, and never copies a draft.
- Every step ends by naming the next one.

### A project stays clean (REQ-019, REQ-020)
- A project's AI layer comes from one private config repo (`drunken-init --config-repo`).
- `drunken-init --migrate-ai-layer` moves a layer a project already committed out of its git: back up,
  exclude, untrack (staged; you commit it).
- A project carries no `.mcp.json`; `drunken-jira-mcp` is declared once per machine at user scope.
- Jira credentials live in no git repository.

### Safety (REQ-023)
- A native `pre-push` hook scans every push, including a solo tag and a push of deletions only; "already
  public" is asked of the push target itself.
- The hook floor covers linked worktrees and `core.hooksPath`.
- Known limits: DG-490, DG-491, DG-496.

### Install and update (REQ-022, REQ-008)
- The skills, roles and agent adapters ship inside the package. `drunken-install` installs and updates
  them with one command on Windows and POSIX, and `drunken-install status` says what an update would
  change before it is applied.

### Not in 2.0.0
- Antigravity, Aider and Gemini CLI (2.1).
