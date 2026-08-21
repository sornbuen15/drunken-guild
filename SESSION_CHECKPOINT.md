# Session Checkpoint — ai-team-toolkit

Read this first. It says what is decided, what is done, and what is next.
Finished work leaves this file and goes to the commit or the README.

Last updated: 2026-08-21

Related repos, both referenced throughout:

- `~/Projects/ai-team-toolkit` — this one. Sandbox where skills and agents are authored,
  then installed to `~/.claude/` by `scripts/install/sync_*.sh`.
- `~/Projects/drunken-team` — the MCP servers (`drunken-jira-mcp`, `drunken-discord-mcp`),
  and the rules in its `CLAUDE.md` that are now the authority this repo follows.

---

## 0. Where the work stands right now

**Branch: `feature/retire-local-board-for-jira`**, four commits in, working tree clean.
Stopped cleanly between Phase 2 and Phase 3 — nothing is half-edited.

| phase | what | state |
|---|---|---|
| 1 | `CLAUDE.md` declares Jira the only coordination surface | ✅ `91e1df1` |
| 2 | 8 skills moved from `board_*` to `jira_*` | ✅ `eaf5947`, `c18cef6`, `73a5c3b` |
| 3 | Retire the 4 orchestration skills to `_not_used/` | ⬜ **next** |
| 4 | `principal-engineer` merge | ⬜ |
| 5 | Pull 6 skills from drunken-team, model ids, agents `INDEX.md` | ⬜ (independent — can go first) |
| 6 | Retire the board code, then docs and examples | ⬜ |

### One thing needs a human before anything is pushed

`fix/sync-aborts-on-frontmatter-skills` is pushed and **has no PR**. Its 5 commits (the
`sync_skills.sh` fix and the original checkpoint) are not in `develop` yet. PR creation was
blocked by the permission classifier in a non-interactive session, so it must be opened by hand:

```bash
gh pr create --base develop --head fix/sync-aborts-on-frontmatter-skills --fill-verbose
```

`feature/retire-local-board-for-jira` was branched from that branch's tip, so once the PR merges
its base becomes an ancestor of `develop` and the two stop being stacked. **Open the feature PR
against `develop`, and only after the fix PR has merged.**

The remote also still points at the pre-rename URL. GitHub redirects, so pushes work, but:

```bash
git remote set-url origin https://github.com/sornbuen15/drunken-ai-team.git
```

---

## 1. The decision that was blocking everything — made

**There is no local board any more. Jira is the only coordination surface, and
`drunken-team` is the authority.** Skills and agents here follow its rules.

Two clarifications that came out of making the decision, both worth keeping:

**"Follow drunken-team" means follow its rules, not copy its files.** Its
`.agents/skills/principal-engineer/SKILL.md` still shells out to `jira_bridge.py`, which its own
`CLAUDE.md` says is not the supported path, and its flow runs In Progress → Done, skipping the
IN REVIEW its `CLAUDE.md` says in bold to never skip. Copying that file would import the
contradiction. The authority is `CLAUDE.md` plus `.agents/skills/jira-tickets/SKILL.md`.

**This repo itself has no Jira and needs none.** Work here is tracked in this file and in git.
`CLAUDE.md` now says so, so nobody creates a project to track it.

### Three limits of the real Jira that changed what the skills may write

Found in `jira-tickets/SKILL.md`, and each one broke a literal translation:

- **`priority` cannot be set on a team-managed project.** Every issue reads `Medium`. The
  CRITICAL/HIGH/MEDIUM/LOW field became **labels** everywhere.
- **No story points exist.** `task-estimation` may not write estimates anywhere on a ticket.
- **`jira_move_to_backlog` / `jira_move_to_board` change membership, not status.** On the board,
  moving a lane *was* the transition. In Jira it is a separate axis, so
  `backlog-refinement` is now forbidden to call `jira_transition_issue` at all.

---

## 2. Phase 3 — retire the four orchestration skills (next up)

Decided: **orchestration is cancelled, and no claim primitive is needed.** Jira's `jira_assign`
says whose work a ticket is; that is enough.

Move to `_not_used/`, with a note saying what replaced them. **Do not delete** — an agent does
not delete, and marking a thing unused beats removing it.

- `skills/kanban/agentic-kanban`
- `skills/kanban/kanban-io` — called itself "the required gatekeeper for all board operations"
- `skills/kanban/next-task`
- `skills/workflow/squad-workflow`

Check `sync_skills.sh` discovery before moving: if it globs `skills/*/*/SKILL.md`, moving them
out of `skills/` is enough. They are currently installed in `~/.claude/skills/`, so the next sync
will report four orphans. That is correct behaviour — reported, never deleted.

---

## 3. Phase 4 — `principal-engineer` is the only agent that needs merging

12 of the 13 agents here differ from their drunken-team twin **only** in `model:` and the
`Skill index:` path (`~/.claude/…` vs `~/.gemini/config/…`). That is a platform variant, not
drift. Nothing to do for those 12.

`principal-engineer` is the exception, and **our version is the better one** — 267 lines against
78. It is also the only agent contaminated with `board_*`.

| block | ours | drunken | action |
|---|---|---|---|
| `<role>`, `<thinking_model>`, `<product_management>`, `<technical_direction>`, `<leadership_communication>` | richer | thin or absent | keep ours |
| `<core_principles>` | **absent** | 8 lines — RICE, MoSCoW, Build-vs-Buy, RED metrics | **pull in** |
| `<squad_delegation>` | `board_agent_context` | thin | rewrite on Jira |
| `<orchestration_protocol>` | `board_*` | `jira_bridge.py`, skips IN REVIEW | **rewrite — both sides are wrong** |
| `<task_creation>` | `kanban-io` | thin | → `jira_create_issue` |

Phase 3 cancels orchestration, so `<squad_delegation>` and `<orchestration_protocol>` should
collapse to explicit sequential steps with `jira_assign` and `jira_start_task` — not a
re-implementation of `board_orchestrate` against Jira.

---

## 4. Phase 5 — what to pull from drunken-team (independent, can be done first)

Its `.agents/skills/` holds 25 directories; 13 are this repo's agents. The flow is
**drunken-team → here for six items only**, not a wholesale merge.

**Take, as pointers not copies:**
- `jira-tickets` (182 lines) — already linked from `CLAUDE.md`. Keep linking; do not vendor it.
- `ask-boss` (92) — the approval protocol.

**Take as real additions:**
- `zero-defect-mindset` (36) — shift-left
- `khit-wikhro-yaekyae` (40) — investigate before executing, in E2E
- `laravel-developer` (50) — **this closes the orphan**. It is installed in `~/.claude/agents/`
  with no source here; the source is drunken-team's. The old checkpoint asked the wrong question.
- `electron-ipc-protocol` (40)

**Decide, may be duplicates of what we already have** — six role stubs of 15–17 lines:
`mobile-developer` (vs `cross-platform-mobile` + `native-*`), `insurtech-specialist` (vs
`insurance-specialist`), `product-manager` (vs `principal-engineer`'s PM hat), plus
`aitech-specialist`, `desktop-frontend-dev`, `game-developer`.

**Also in this phase:**
- **`model:` ids are stale on every agent** — 4 at `claude-opus-4-8`, 9 at `claude-sonnet-4-6`.
  Current is the Claude 5 family (`claude-opus-5`, `claude-sonnet-5`).
- `sync_agents.sh` still emits no `INDEX.md`, unlike `sync_skills.sh`. `CLAUDE.md` now points at
  `agents/INDEX.md`, so this is a live dangling reference until it is built.

---

## 5. Phase 6 — code and docs, last

**Retire, do not delete.** To `_not_used/` with a note:
- `scripts/mcp/kanban-server.js` and `scripts/kanban/`
- `templates/mcp-settings.json` — it configures the board server
- `scripts/ask_boss.py` and `scripts/discord_listener.py` (untracked, 519 lines) — they duplicate
  `drunken-discord-mcp`, and **hardcode Discord channel id `1518206617336811573`**, which breaks
  both config precedence (DT-254) and secrets-by-reference. Do not commit them as they are.

**The 182-line Jira write-through is preserved on branch `wip/kanban-server-jira-sync`**, commit
`fc1a93c`, not merged. It made the board primary and Jira its mirror — the wrong direction. Its
message records the two defects it carries so nobody revives it unexamined.

**Docs:**
- `examples/01-spec-to-backlog`, `02-backlog-refinement`, `04-next-task`, `05-agentic-kanban`
  each ship a `board/` fixture as expected output. Rewrite the first two against Jira; `04` and
  `05` cover skills that Phase 3 retires, so they go with them.
- `GETTING_STARTED.md` still documents the manual fallback that copies `skills/kanban/*` by hand,
  predating the flattening `sync_*.sh` does. Nothing mentions `skills/.external`. Nothing says
  the MCP servers come from `~/Projects/drunken-team` and are declared per project in `.mcp.json`.
  No step verifies the install by naming the number installed.
- **Counts are already correct** — `README.md:7` reads 30 skills and 5+8=13 agents, and both
  match. The old checkpoint's claim that 12/34/14 were quoted around the docs no longer holds.
- Split `CLAUDE.md` per the original §3: it stays the live file for working *here*, and
  `templates/CLAUDE.md` becomes the thing other projects copy. A template embedded in a project
  that never exercises it cannot be verified by use.

---

## 6. Still true, for context

`skills/.external` records the skills that are third-party and have no source here —
`debug-mantra`, `management-talk`, `post-mortem`, `scrutinize`. Do not author or overwrite these.

`sync_skills.sh` was fixed on 2026-08-21: it had been exiting 1 on its second skill since skills
gained frontmatter (`set -euo pipefail` plus an unmatched `grep` for the removed
`Trigger/Keywords:` line), printing a green "Updated" for the first skill on its way out. 29 of 30
installed skills sat at v1.1.0 without frontmatter for two months. That fix is in the unmerged
PR above.

The eight leftover group directories under `~/.claude/skills/` were removed by the Boss the same
day. `~/.claude/skills/` holds 34 skills and no leftovers.
