# Changelog

A change to **how the flow itself works** is a minor or major release and has an entry here
(REQ-022). `drunken-install status` quotes the newest entry before an update is applied.

The top heading is the version this tree declares in `pyproject.toml`; `Unreleased` stands in
while a release is being prepared, and is renamed to the version when it is tagged
(`tests/test_changelog.py`).

## Unreleased

Heading towards **2.0.0**. The flow is one standard that an agent can run on any project.

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
