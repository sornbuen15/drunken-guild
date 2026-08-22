# Session Checkpoint — ai-team-toolkit

Read this first. It says what is decided, what is done, and what is next.
Finished work leaves this file and goes to the commit or the README.

Last updated: 2026-08-22

Related repos, both referenced throughout:

- `~/Projects/ai-team-toolkit` — this one. Sandbox where skills and agents are authored,
  then installed to `~/.claude/` by `scripts/install/sync_*.sh`.
- `~/Projects/drunken-team` — the MCP servers (`drunken-jira-mcp`, `drunken-discord-mcp`),
  and the rules in its `CLAUDE.md` that are now the authority this repo follows.

---

## 0. Where the work stands right now

**Branch: `feature/retire-local-board-for-jira`**, 12 commits in, working tree clean apart from
four deliberately-untracked files (§6).

**All six phases are done.** The migration off the local board is complete: nothing in `skills/`,
`agents/` or `templates/` calls a `board_*` tool, no document advertises a retired skill, and
the counts in `README.md` match what the repo produces.

| phase | what | state |
|---|---|---|
| 1 | `CLAUDE.md` declares Jira the only coordination surface | ✅ `91e1df1` |
| 2 | 8 skills moved from `board_*` to `jira_*` | ✅ `eaf5947`, `c18cef6`, `73a5c3b` |
| 3 | Retire the 4 orchestration skills, and the docs that named them | ✅ `7756a6e`, `b04924f` |
| 4 | `principal-engineer` merge | ✅ `7818bfb` |
| 5 | Model ids, agents `INDEX.md`, 4 pulls from drunken-team | ✅ `40f16b8`, `cdc04c8` |
| 6 | Board code retired, examples and docs rewritten, `CLAUDE.md` split | ✅ `605ade3`, `b3d53a3`, `9ed56e4` |

Current inventory: **29 skills**, **15 agents**, both indexes regenerated and matching.

### What still needs a human — nothing here is blocked on more authoring

**1. The unmerged fix PR.** `fix/sync-aborts-on-frontmatter-skills` is pushed and **has no PR**.
Its 5 commits (the `sync_skills.sh` fix and the original checkpoint) are not in `develop` yet.
PR creation was blocked by the permission classifier in a non-interactive session:

```bash
gh pr create --base develop --head fix/sync-aborts-on-frontmatter-skills --fill-verbose
```

`feature/retire-local-board-for-jira` was branched from that branch's tip, so once the fix PR
merges its base becomes an ancestor of `develop` and the two stop being stacked. **Open the
feature PR against `develop`, and only after the fix PR has merged.**

**2. The remote still points at the pre-rename URL.** GitHub redirects, so pushes work, but:

```bash
git remote set-url origin https://github.com/sornbuen15/drunken-ai-team.git
```

**3. Install, and read the orphan report.** Nothing here has been synced — installation is
always manual:

```bash
./scripts/install/sync_skills.sh
./scripts/install/sync_agents.sh
```

Expect `sync_skills.sh` to name four orphans under *"Installed but not produced here"*:
`agentic-kanban`, `kanban-io`, `next-task`, `squad-workflow`. **That is correct behaviour** —
they are retired, they stay installed until you remove them, and they are reported every run
rather than deleted. Removing them is your call:

```bash
rm -rf ~/.claude/skills/agentic-kanban ~/.claude/skills/kanban-io \
       ~/.claude/skills/next-task ~/.claude/skills/squad-workflow
```

`sync_agents.sh` now emits `~/.claude/agents/INDEX.md` and has the same orphan report; it should
report no orphans, because `laravel-developer` — the long-standing one — now has a source here.

---

## 1. The decision everything followed from

**There is no local board any more. Jira is the only coordination surface, and
`drunken-team` is the authority.** Skills and agents here follow its rules.

Two clarifications from making that decision, both still load-bearing:

**"Follow drunken-team" means follow its rules, not copy its files.** Its
`principal-engineer/SKILL.md` shells out to `jira_bridge.py`, which its own `CLAUDE.md` says is
not the supported path, and runs In Progress → Done, skipping the IN REVIEW that same file says
in bold never to skip. Copying it would have imported the contradiction. The authority is
`CLAUDE.md` plus `.agents/skills/jira-tickets/SKILL.md`.

**This repo itself has no Jira and needs none.** Work here is tracked in this file and in git.

### Three limits of the real Jira, now written into every affected skill and doc

- **`priority` cannot be set on a team-managed project.** Every issue reads `Medium`.
  CRITICAL/HIGH/MEDIUM/LOW is a **label** everywhere.
- **No story points exist.** `task-estimation` prints its table and never writes back.
- **`jira_move_to_backlog` / `jira_move_to_board` change membership, not status.** On the old
  board, moving a lane *was* the transition; in Jira it is a separate axis. `backlog-refinement`
  is forbidden to call `jira_transition_issue` at all.

### The one capability genuinely given up

`board_claim_task` expired a claim after 1800s. **A Jira assignee never expires.** If an agent
stops mid-ticket the ticket stays assigned until a human reassigns it. Ten seconds of work,
accepted against a class of silent disagreement that costs weeks. It is recorded in
`_not_used/skills/next-task/RETIRED.md`, in `README.md`'s Known Limitations, and in
`principal-engineer`'s `<sequencing_protocol>`.

---

## 2. What `_not_used/` now holds

Nothing was deleted. Every retired thing sits under `_not_used/` with a `RETIRED.md` beside it
saying why and what replaced it; `_not_used/README.md` indexes them and explains why no exclude
list is needed (both sync scripts discover with a glob that no longer reaches these paths).

| path | why |
|---|---|
| `skills/agentic-kanban` | triage half survives in `issue-intake` / `spec-to-backlog`; orchestration half cancelled |
| `skills/kanban-io` | it *was* the local board interface. **Deliberately no `jira-io` successor** — `drunken-jira-mcp` is already the typed interface a wrapper would add |
| `skills/next-task` | `jira_daily_standup` + `jira_start_task`, called directly |
| `skills/squad-workflow` | its gates were `board_*` writes |
| `examples/04-next-task`, `05-agentic-kanban` | recorded output of retired skills |
| `examples/pre-jira-fixtures` | the `board/` output of examples 01–02, whose skills survive |
| `scripts/kanban`, `scripts/mcp` | the CLI fallback and the server defining all nine `board_*` tools |
| `templates/mcp-settings.json` | it registered that server and nothing else |

**Orchestration was cancelled, not ported.** `board_orchestrate` computed dependency waves;
rebuilding it against Jira would recreate the second surface the migration removes.
`principal-engineer` now sequences explicitly — one `jira_daily_standup`, an ordering it decides
and defends in writing, a user gate before anything is assigned, then assign / start /
submit-for-review per ticket.

**The 182-line Jira write-through is still preserved on branch `wip/kanban-server-jira-sync`**,
commit `fc1a93c`, unmerged. It made the board primary and Jira its mirror — the wrong direction.
Its commit message records the two defects it carries, so nobody revives it unexamined.

---

## 3. What came in from drunken-team, and what did not

Its `.agents/skills/` holds 25 directories. 13 are this repo's agents (platform variants, not
drift). 2 stay **pointers** that `CLAUDE.md` links rather than copies: `jira-tickets` and
`ask-boss`. Of the remaining 10, four came across and six did not.

**Taken** — rewritten to this repo's canonical structure, not vendored:

- `laravel-developer` → `agents/laravel-developer.md`. **Closes the standing orphan** — it had
  been installed in `~/.claude/agents/` with no source here.
- `desktop-frontend-dev` → `agents/desktop-frontend-dev.md`. Genuinely absent, and without it
  `electron-ipc-protocol` would have had no owner.
- `electron-ipc-protocol` → `skills/frontend/`.
- `zero-defect-mindset` → `skills/workflow/`. Written as a **position, not a fourth copy** of
  rules that already exist — it routes to `/secure`, `/clean-arch`, `/tdd`, `/surgical`,
  `/test-types` rather than restating any of them.
- `khit-wikhro-yaekyae` → `skills/workflow/think-analyze-isolate/`. It **could not be vendored**:
  it is Thai-language and every file here is English-only by FATAL directive. Same discipline
  including the anti-loop mandate; provenance and the incident behind it are in the file.

**Skipped, with the reason, so nobody re-litigates them:**

| stub | why not |
|---|---|
| `mobile-developer` | duplicate — `cross-platform-mobile` + `native-ios` + `native-android` are richer |
| `insurtech-specialist` | duplicate of `insurance-specialist` |
| `product-manager` | duplicate of `principal-engineer`'s PM hat |
| `aitech-specialist` | duplicate — `ai-memory-specialist` covers RAG, `agentic-systems-specialist` covers agent loops |
| `game-developer` | no overlap, but nothing here uses it. A 15-line stub in an 80–270 line agent set lowers the bar for no caller |

---

## 4. Three bugs found and fixed in passing

Worth knowing about, because each failed silently:

- **`core-engineering` had no index entry.** Its frontmatter read `Also trigger on /tdd`, and
  the installer greps for `Trigger on /`. Fixed, and the trap is now in the contributor
  checklist — keep `Trigger on /x.` on one line.
- **`examples/contributing/SKILL-annotated.md` taught a forbidden format.** No YAML frontmatter,
  a `**Trigger/Keywords:**` line removed when triggers moved into the description, and a
  `.claude/board/` template. Anyone following it authored a skill the installer cannot index.
  Rewritten on `issue-intake`.
- **`GETTING_STARTED`'s manual install never said skills install FLATTENED.** Copying the
  category directories is what produced the eight leftover group directories cleaned up on
  2026-08-21. Now stated, with a verified one-line `find | xargs`, and both install paths end in
  a count.

---

## 5. Where the rules live now

`CLAUDE.md` (this repo) governs **working here** — it keeps the coordination rules *and* adds
the skill/agent authoring rules, which apply nowhere else.

`templates/CLAUDE.md` (new) is what a **consuming project copies**. It carries the coordination
and delivery rules with `<angle-bracket>` slots for the project's Jira key, branches, and
build/test commands.

**A coordination rule changing means changing both.** Both files say so.

---

## 6. Four files deliberately left untracked

`git status` will show these. None belongs in a commit as it stands:

- **`scripts/ask_boss.py`, `scripts/discord_listener.py`** (519 lines) — they duplicate
  `drunken-discord-mcp` and **each hardcodes Discord channel id `123456789012345678`**, which
  breaks both config precedence (DT-254) and secrets-by-reference. **Do not commit them as
  they are.** Either delete them (they are a duplicate of a working MCP server) or rewrite the
  id as an `env://` reference first. This is a human decision, not an agent one.
- **`pr_description.md`** — a draft for a PR that predates this branch. Superseded; the commit
  messages on this branch carry the reasoning.
- **`.agents/active_agent.json`** — session scratch. Belongs in `.gitignore`, which is a
  reasonable first task for the next session.

---

## 7. Still true, for context

`skills/.external` records the skills that are third-party and have no source here —
`debug-mantra`, `management-talk`, `post-mortem`, `scrutinize`. Do not author or overwrite these.
`GETTING_STARTED.md` now explains what that file is for, which nothing previously did.

`sync_skills.sh` was fixed on 2026-08-21: it had been exiting 1 on its second skill since skills
gained frontmatter (`set -euo pipefail` plus an unmatched `grep`), printing a green "Updated" for
the first skill on its way out. 29 of 30 installed skills sat at v1.1.0 without frontmatter for
two months. That fix is in the unmerged PR in §0. `sync_agents.sh` grew the same `|| true`
guards when it learned to emit `INDEX.md`.
