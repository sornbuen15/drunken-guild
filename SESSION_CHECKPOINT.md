# Session Checkpoint — ai-team-toolkit

Read this first. It says what is broken, what must be decided, and in what order.
Finished work leaves this file and goes to the commit or the README.

Last updated: 2026-08-21

Related repos, both referenced throughout:

- `~/Projects/ai-team-toolkit` — this one. Sandbox where skills and agents are authored,
  then installed to `~/.claude/` by `scripts/install/sync_*.sh`.
- `~/Projects/drunken-team` — the MCP servers (`drunken-jira-mcp`, `drunken-discord-mcp`),
  and the rules in its `CLAUDE.md` that the skills here currently contradict.

---

## 1. The blocker: 12 skills drive a board that does not exist

`drunken-team/CLAUDE.md` says "Jira is the only coordination surface", and "do not create
`.claude/board/` or `.agents/board/` in any project" (DT-250).

These skills say the opposite. `kanban-io` calls itself "the required gatekeeper for all
board operations". No `.mcp.json` in any of the three projects declares a kanban server;
`scripts/mcp/kanban-server.js` is wired to nothing.

Every session in every project currently receives both instructions.

**Decide per group. This is the work; the rest is bookkeeping.**

| group | skills | board tools used | Jira equivalent |
|---|---|---|---|
| **create** | `issue-intake`, `spec-to-backlog`, `audit-to-backlog`, `project-audit-reviewer` | `board_create_task`, `board_get_task` | `jira_create_issue` — direct swap |
| **read** | `local-progress-reporter`, `test-report-generator` | `board_list_lane`, `board_summary` | `jira_search_issues` — direct swap |
| **read + move** | `backlog-refinement` | the above plus `board_move_task` | `jira_transition_issue`, `jira_move_to_backlog` |
| **claim / orchestrate** | `agentic-kanban`, `kanban-io`, `next-task`, `squad-workflow` | `board_claim_task`, `board_agent_context`, `board_orchestrate`, `board_release_claim` | **no equivalent** — see below |
| **wording only** | `git-workflow` | none; mentions the board in prose | edit the sentence |

The last group is the real decision. Jira has `jira_assign` for "this one is mine", but no
orchestration primitive and **no claim expiry** — DT-250 recorded that trade deliberately:
the board released a claim after 1800s, a Jira assignee never expires, and a ticket left
assigned to a dead agent stays that way until a human looks.

Three ways out. Pick one:

1. **Rewrite onto Jira.** Claim becomes `jira_assign`; orchestration becomes explicit
   steps. Loses claim expiry.
2. **Mark the four unused.** Move the other eight to Jira. Smallest change, loses the squad
   workflow.
3. **Keep kanban for projects without Jira.** Then it must be declared in an `.mcp.json`,
   and each skill must say which surface it needs. Two surfaces on purpose, documented.

Do not leave it as it is. Two surfaces by accident is the failure DT-248, DT-249 and DT-250
each cost a session.

---

## 2. Agents have no index

`~/.claude/agents/` holds 14 agents and no `INDEX.md`. `scripts/install/sync_agents.sh`
does not build one, unlike `sync_skills.sh`.

Not a functional gap — Claude Code discovers agents from their frontmatter. It is a gap for
§3: there is no catalog to paste into a project's `CLAUDE.md`.

**Do:** make `sync_agents.sh` emit `INDEX.md` the way `sync_skills.sh` does.

---

## 3. This repo's CLAUDE.md is stale, and should become the catalog

It should answer in one place: **what skills, agents, plugins and MCP servers exist, where
each comes from, and how a project declares them.**

Blocked on §1 — writing the catalog first would only record the contradiction.

**Do, after §1:**

- Rewrite `CLAUDE.md` around the four layers and their sources: skills and agents from here
  via `sync_*.sh`; MCP servers from `~/Projects/drunken-team` via each project's
  `.mcp.json`.
- Emit a block a project can paste into its own `CLAUDE.md`, generated rather than typed.
- State which surface each skill group needs, per §1's decision.

---

## 4. The docs teach the broken flow

Every worked example and the install walkthrough are built on the board from §1. They will
mislead anyone following them until §1 is decided, and they are wrong on plain facts today.

**Counts are wrong now.** The docs quote 12, 30 and 34 skills in different places; the repo
has 30. They say 14 agents; the repo has 13 — `laravel-developer` is installed in
`~/.claude/agents/` but has no source here. Either bring it in or drop the claim.

**The examples are the board walkthrough.** `01-spec-to-backlog`, `02-backlog-refinement`,
`04-next-task` and `05-agentic-kanban` each ship a `board/` fixture as their expected
output. Four of the five are in §1's board-dependent set. Rewrite them against whatever §1
decides, or mark them unused — do not leave a walkthrough that cannot be followed.

**The install instructions are incomplete and partly wrong.**

- `GETTING_STARTED.md` still documents a manual fallback that copies `skills/kanban/*` by
  hand. It predates the flattening `sync_*.sh` does and produces the nested layout that
  left eight stale directories behind.
- Nothing mentions `skills/.external`, so the next person will "fix" the four third-party
  skills by authoring copies here.
- Nothing says the MCP servers come from `~/Projects/drunken-team` and are declared per
  project in `.mcp.json`. A reader installing skills alone gets tools that call servers
  they were never told to set up.
- No step verifies the install. `sync_skills.sh` exited 1 for two months while looking
  successful; the walkthrough should end with a check that names the number installed.

**Do:** fix the counts now, since they are wrong regardless of §1. Everything else waits on
§1 and lands with §3, so the catalog and the walkthrough tell the same story.

---

## 5. Fixed on 2026-08-21, for context

`sync_skills.sh` had been exiting 1 on its second skill since skills gained frontmatter:
`set -euo pipefail` plus an unmatched `grep` for the removed `Trigger/Keywords:` line. It
printed a green "Updated" for the first skill on its way out, so 29 of 30 installed skills
sat at v1.1.0 without frontmatter for two months while this repo held v1.2.0 with it.

Now: `|| true` on every optional extraction, `INDEX.md` built from the frontmatter
`description:`, duplicate basenames refused, orphans and leftover group directories
reported but never deleted.

`skills/.external` records the skills that are third-party and have no source here —
`debug-mantra`, `management-talk`, `post-mortem`, `scrutinize`. Do not author or overwrite
these.

The eight leftover group directories under `~/.claude/skills/` — `architecture`, `backend`,
`frontend`, `infrastructure`, `leadership`, `product`, `security`, `workflow` — were removed
by the Boss the same day. `~/.claude/skills/` now holds 34 skills and no leftovers, and a
clean sync run reports none. `sync_skills.sh` will name them again if any reappear.
