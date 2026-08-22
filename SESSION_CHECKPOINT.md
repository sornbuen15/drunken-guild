# Session Checkpoint — drunken-guild

**Read this first.** It says what this repo is, what is already true, and what to do next.

Rule for this file, inherited and worth keeping: **finished work does not live here.** It goes to
the commit, the ticket, or `CLAUDE.md`, and this file links to it.

Last updated: 2026-08-22 · **pre-release, no remote yet** · `develop` is where work lands

---

## 0. What this repo is

`drunken-guild` is the merge of two repositories that had been drifting apart:

- `~/Projects/drunken-team` — the Python MCP servers (`drunken-jira-mcp`, `drunken-discord-mcp`),
  the CLI (`drunken-doctor`, `drunken-away`, `drunken-usage`, …), tests, CI.
- `~/Projects/ai-team-toolkit` — GitHub `drunken-ai-team`. The skills and agents installed into
  `~/.claude/`.

**Neither has been touched.** Both still exist, still work, and are the fallback if this goes
wrong. Nothing here deletes from them.

**Brand:** *Drunken Programmer* is the pen name and the future org. `drunken-guild` is the
product. The name was chosen because `.guild_templates/` in the old repo already meant "the
standard other projects copy" — a guild is a craftsmen's association that holds a shared
standard, which is exactly what this repo is for. `drunken-tavern` was rejected: it collides
with SillyTavern (32k stars) in the same AI space. `drunken` alone was rejected as too generic
to find. Both are free on PyPI if that changes.

The joke has to survive contact with the work: **the name says drunk, the contents are FATAL
directives, blast-radius checks and post-mortems.** That tension is the brand. Do not soften
either half.

---

## 1. Why the merge — the evidence, so nobody re-litigates it

Skills and agents were being authored in **four** places, and 26 of them were duplicates by name:

| where | count |
|---|---|
| `drunken-team/skills/` | 14, flat |
| `drunken-team/.agents/skills/` | 25, Antigravity variants |
| `drunken-ai-team/skills/` | 29, categorised |
| `drunken-ai-team/agents/` | 15 |

Hand-syncing four surfaces does not work, and the session that produced this repo proved it
twice:

- **`git-workflow` had silently diverged** — 73 lines on one side, 196 on the other — while a
  just-merged PR instructed one repo to defer to the other's copy.
- **`skills/.external` declared four skills "third-party with no source here"** while their
  source was the sibling repo the whole time.

That is the same class of failure the whole Jira migration was about: *two surfaces that can
disagree*. The answer is one surface.

---

## 2. What is already done

Commit `abe5df1`, on `develop`. **317 commits — both histories are intact**, brought in by
subtree rather than copied, so the work that produced the toolkit survives.

| | state |
|---|---|
| base | `drunken-team` at `cec6e61`, with its 12 tags, 49 test files, `test.yml`, 9 pre-commit hooks |
| `skills/` | **36**, one categorised tree |
| `agents/` | 15 |
| `templates/` `examples/` `_not_used/` `scripts/install/` | moved as-is |
| `skills/.external` | **empty on purpose** — the four names it held are first-party now |

Of `drunken-team`'s flat 14: six were superseded by a newer version on the toolkit side
(`git-workflow` 73→196, `backlog-refinement` v4, `project-audit-reviewer` v4, `task-estimation`
v4, `system-design-rules` byte-identical, `next-task` already retired) and moved to
`_not_used/skills-superseded-by-toolkit/` — **not deleted, an agent does not delete.** The other
seven are real and were categorised: `debug-mantra`, `post-mortem`, `scrutinize`,
`release-notes-writer` → `workflow/`; `management-talk` → `leadership/`; `confluence-sync`,
`acronym-namer` → `documents/`.

---

## 3. The plan

Ordered. Each phase should merge on its own without breaking the one before it.

### Phase 1 — `CLAUDE.md`, written from scratch  ⬅ **start here**

The `CLAUDE.md` currently in this repo is **`drunken-team`'s, inherited by the clone.** It still
says "drunken-team — instructions for Claude Code" and describes a repo that no longer exists in
this shape. It carries good rules; it is not this repo's file.

Write a new one. It has to serve a repo that is now **both** a Python package and a skill/agent
library, which neither source file did. Pull from both, and settle these, which the old pair
disagreed on or never stated:

- Which parts of the tree the Python gates apply to (`src/`, `tests/`) and which are markdown.
- The DT-250 wrapper-layout rule: **this repo is an exception and must say so.** Its AI layer
  *is* the product; applying the rule literally moves the deliverable out of git. `drunken-team`
  was also an exception and never said so. TWA is the one project that follows it.
- The skill- and agent-authoring rules, which only the toolkit side had.
- Point the git rules at `skills/workflow/git-workflow/SKILL.md` and do not restate them. That
  skill is now v2.0.0 and is the single home: branch naming, merge strategy per target, and
  **an agent opens PRs; a human merges them.**

`README.md`, `GETTING_STARTED.md` and this file get the same treatment. Do not merge the two old
READMEs paragraph by paragraph — write the one this repo needs.

Leftovers from the merge are parked in `.incoming/` (`CLAUDE.md`, `README.md`,
`SESSION_CHECKPOINT.md`, `.gitignore` from the toolkit side). Read them, then delete the
directory in the commit that replaces them.

### Phase 2 — one source for Antigravity, not two

**The Boss's requirement: do not maintain two copies.** Antigravity must read the *same* skills,
agents and MCP servers as Claude. Only if a thing genuinely cannot be shared does Antigravity get
its own, and then it is created on the Antigravity side.

Today `~/.gemini/config/skills/` is a **real directory with 66 entries**, not a link, and
`.agents/skills/` in this repo holds 25 more — the 15 agent twins, `jira-tickets`, `ask-boss`,
and 8 stubs that were already assessed and rejected as duplicates of richer agents
(`aitech-specialist`, `game-developer`, `insurtech-specialist`, `mobile-developer`,
`product-manager`, and three others).

Proposed, to be verified before doing:

1. **`jira-tickets` and `ask-boss` become first-class skills** under `skills/`. They are the only
   genuinely unique content in `.agents/skills/`, and eight files in the toolkit already treat
   `jira-tickets` as authoritative by absolute path. Once it lives here, those paths become
   relative and the cross-repo dependency is gone.
2. **The 15 twins stop existing as files.** `install_agents.sh` generates both variants from the
   single `agents/` source — the only real differences were `model:` (claude vs gemini) and the
   skill-index path (`~/.claude/…` vs `~/.gemini/config/…`).
3. **The 8 stubs → `_not_used/`** with the note that says why each was rejected.
4. **Antigravity points at the shared install rather than getting a copy.** A symlink
   `~/.gemini/config/skills` → `~/.claude/skills` is the obvious mechanism, but
   `~/.gemini/config/skills` currently holds ~30 skills that are *not* ours and would be lost.
   **Verify what is in there and who owns it before linking anything.** If a link is not safe,
   the install script writes both — but that is a fallback, not the goal.

Write the note for Antigravity as part of this phase, so it and Claude read the same rules.

### Phase 3 — Jira and Discord move to the guild

- **Jira key: `DG`.** New project. The Boss is clearing the old `DT` project.
- **Discord: reuse the existing bot token, create a NEW room.** The token identifies the
  application and is not tied to a channel; the channel id is new.
- **The channel id is configuration, never a literal.** Config precedence is fixed: environment
  variable, then registry, then the project's own `.agents/*.json`. Nothing discovers a file by
  climbing.
  The old `scripts/ask_boss.py` and `scripts/discord_listener.py` in the toolkit repo **hardcode
  channel id `1518206617336811573`**. They were deliberately never committed. Do not bring them
  across in that state.
- Re-register: `drunken-init --project drunken-guild --path … --git-root …`, and update
  `.mcp.json`. Note the old `.mcp.json` is **cwd-relative** (`uv run` + `PYTHONPATH: src`) and
  cannot be copied into a consuming project — the portable form is
  `uv --directory /abs/path run python -m jira_mcp.server --project <KEY>`, verified working from
  an unrelated cwd.

### Phase 4 — install scripts, one per layer

Scripts first, no wizard.

```
scripts/install/install_skills.sh    → ~/.claude/skills/
scripts/install/install_agents.sh    → ~/.claude/agents/  (+ the Antigravity variant)
scripts/install/install_mcp.sh       → prints/writes the .mcp.json snippet
```

The existing `sync_skills.sh` / `sync_agents.sh` already do most of this and are battle-tested —
`sync_skills.sh` in particular carries `|| true` on every optional grep for a reason recorded in
its comments. Rename and extend rather than rewrite.

### Phase 5 — release, then the package (optional)

One repo, one version. `drunken-team` is at v2.3.0 and reserved 3.0.0 for removing the deprecated
`request_boss_approval`. **This merge is a v3.0.0**: the tool surface changes, four slash commands
were retired, and two products became one.

The package (`pip install drunken-guild`, CLI `drunken`) is the last step and is optional. If it
happens, the six `drunken-*` console scripts collapse into `drunken <subcommand>`, with the old
names kept as aliases.

---

## 4. What needs the Boss

- **Create the GitHub repo** and add it as `origin`. Nothing here is pushed yet.
- Clear the old Jira project and create `DG`.
- Create the new Discord room and invite the existing bot.
- **Merge every PR.** An agent opens them; a human merges them. No exception.

---

## 5. Things that will bite you

- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`.** They are the
  fallback until this repo is pushed, released and verified. The toolkit repo is scheduled for
  termination *after* that, not before.
- **`~/.claude/` follows this repo from now on.** If an install here disagrees with what is in
  `~/.claude/`, this repo wins.
- **Directory renames come last**, by the Boss's instruction. `~/Projects/drunken-guild` is
  already the new name; the two old directories keep theirs until the end.
- **An agent does not delete.** Anything retired moves to `_not_used/` with a note saying why and
  what replaced it. Anything needing a recursive force-delete becomes a list handed to the Boss.
- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal.
- The `example` skill from `drunken-team` was a template for writing Antigravity skills, not a
  skill. It is in `_not_used/skills-superseded-by-toolkit/`; the equivalent for this repo is
  `examples/contributing/SKILL-annotated.md`, which was rewritten and is current.
