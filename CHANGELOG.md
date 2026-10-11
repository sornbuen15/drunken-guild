# Changelog

A change to **how the flow itself works** is a minor or major release and has an entry here
(REQ-022). `drunken-install status` quotes the newest entry before an update is applied.

The top heading is the version this tree declares in `pyproject.toml`; `Unreleased` stands in
while a release is being prepared, and is renamed to the version when it is tagged
(`tests/test_install_agents.py::TestTheChangelog`).

## Unreleased

### Fixed
- `drunken-doctor`'s `paths.home.permissions` warning (and `paths.auth_db.permissions`) could
  never clear on Windows: the check read `path.stat().st_mode`, which `pathlib` synthesizes there
  from a single read-only attribute bit rather than the real ACL, so a directory always reported
  as world-accessible — the warning stayed even right after running the `icacls` command the
  report itself printed. On Windows the check now runs `icacls` and reads the ACL it reports,
  treating `Everyone`, `BUILTIN\Users`, `NT AUTHORITY\Authenticated Users` and similar as other
  principals; the current user, `SYSTEM`, `Administrators` and the owner are not. If `icacls`
  cannot be run or its output cannot be parsed, the check still warns rather than silently passing.
  POSIX is unchanged (DG-509).

## 2.0.2 — 2026-10-12

Makes the guild's skills and agents reach a session, brings the older ones back, and fixes what
the installed 2.0.1 showed on real projects. Delivery is proven; whether the model then follows
the routing is **not measured yet**.

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

### Fixed
- `drunken-doctor` no longer warns forever about `~/.drunken` permissions on Windows: it reads the
  ACL from `icacls` instead of a synthesized mode, and an ACL that still grants another account
  warns (DG-509).
- An empty, BOM-prefixed or truncated `projects.json` gives a typed error naming the file instead of a
  traceback, and a registry with a `version` but no `projects` object is refused (DG-507).
- `content_scan` reads `.claude`/`.gemini` at any depth, a differently cased `.Claude`, and a
  nested `.mcp.json`; a real `.venv`, `node_modules` or `vendor` install is still stepped over
  (DG-508).
- The installer no longer explodes on two Windows junctions that point at each other: it walks
  without entering a link and still refuses it (DG-510).

### Known and open
- Whether a session that receives the routing then calls the skills and agents is not measured; the
  one scratch run without the hook and the one with it both called none.
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
