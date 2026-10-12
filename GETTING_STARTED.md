# Getting Started

From nothing installed to your first completed ticket.

## Install

Needs [`uv`](https://docs.astral.sh/uv/) and Git.

```bash
uv tool install git+https://github.com/sornbuen15/drunken-guild@v2.0.2   # pick the tag you want
drunken-install all                                                       # skills + agents -> ~/.claude
drunken-install extras --apply                                           # optional: the older skills and agents
drunken-install hook --apply                                             # every session gets the routing rule
drunken-doctor                                                           # proves it: routes.session_hook runs the recorded command
```

`drunken-install all --dry-run` shows what it would write first. The skills and agents travel
inside the package, so one install gives you both.

## Update

```bash
uv tool install --force git+https://github.com/sornbuen15/drunken-guild@v2.1.0
drunken-install status      # what would change, and the changelog entry; writes nothing
drunken-install all         # apply it
```

A tag is a pin — nothing here relies on `uv tool upgrade` moving it.

> **On Windows, close every Claude window first.** `uv tool install --force` fails with "Access
> is denied" while the running MCP server still holds the tool's files open. If that happened,
> delete `%APPDATA%\uv\tools\drunken-guild` and install again without `--force`.

## Add the runtime (optional)

Gives you the `jira_*` tools that `/breakdown`, `/build` and `/audit` need.

```bash
uv sync --extra dev
```

Register a project (credentials live in a file outside any repository) and declare
`drunken-jira-mcp` once per machine. Full steps: [`Drunken-Guild-Guide.md`](./Drunken-Guild-Guide.md).

## A new project

1. `drunken-init --project <id> --path <repo>` writes `AGENTS.md` and a one-line `CLAUDE.md`
   adapter at the project's root (REQ-015) — do not overwrite either by hand.
2. Open Claude Code inside the project and run `/prd`, then `/clarify`, then `/ddd`. Each prints
   which project documents it found and where — the map is the project's root `AGENTS.md`. When there is no map, the defaults are
   `.ai/PRD.md`, `.ai/DOMAIN.md`, `.ai/audit/`, `docs/`, `docs/decisions/`.
3. `/breakdown` cuts the backlog — `REQ-xxx → Epic → Story | Task → Subtask`, Story and Task
   both siblings under the Epic — and halts until you approve the plan; nothing is created first.
4. `/build` takes one task at a time: the test is written and seen failing before the fix, one
   branch, one PR. The agent opens it; a human merges it.
5. `/audit` traces every requirement to a merged, tested, deployed task and writes the day's
   report — gaps become tickets only on your approval.

## An existing project

A project that keeps its documents somewhere else works too — record the paths in `AGENTS.md` and the skills follow; only two copies of the same document is a stop. An older project's
`PROJECT_BRIEF.md` or `REQUIREMENTS.md` stays where it is — `/prd` offers to consolidate it into
one `PRD.md`, naming what the sources disagreed about, never silently. A Jira backlog someone
else already cut is read first, not duplicated: `/breakdown` binds an existing ticket instead of
creating a second one for the same work.

## Windows notes

- PowerShell 5.1+ or [PowerShell 7+](https://github.com/PowerShell/PowerShell/releases).
- `.\scripts\install\install_skills.ps1` and `.\scripts\install\install_agents.ps1` are the
  contributor path's equivalent of the two `.sh` scripts; both take `-IndexOnly`.
- Close every Claude window before `uv tool install --force` (see Update, above).

## Doctor

```bash
drunken-doctor
```

Checks the credential authenticates (not that the Jira project itself exists — a bad credential
can come back `200` with an empty list; confirm the key yourself the first time), that this
machine's skills and agents match the source, and that the routing hook — recorded in its own `AGENTS.md`'s settings entry — actually runs rather than merely being present.

## Where to go next

| | |
|---|---|
| [`README.md`](./README.md) | the two-sentence version and the flow diagram |
| [`AGENTS.md`](./AGENTS.md) | the rules, if you are contributing here |
| [`skills/INDEX.md`](./skills/INDEX.md) | every skill, its trigger and its path |
| [`Drunken-Guild-Guide.md`](./Drunken-Guild-Guide.md) | architecture, Jira workflow, approvals |
| [`Integration-Guide.md`](./Integration-Guide.md) | bringing another project under this workflow |
