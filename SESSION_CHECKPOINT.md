# Session Checkpoint — drunken-guild

**Read this first, then `CLAUDE.md`.** This file says where things stand and what to do next.
`CLAUDE.md` says how to work — and it is **stale**, see Phase 1.

Rule for this file: **finished work does not live here.** It goes to the commit, the ticket, or
`CLAUDE.md`, and this file links to it.

Last updated: 2026-08-22 · `develop` is where work lands · **no release yet, no tags on purpose**

---

## 0. What this repo is

`drunken-guild` is the merge of two repositories that had been drifting apart:

- `~/Projects/drunken-team` — Python MCP servers (`drunken-jira-mcp`, `drunken-discord-mcp`), the
  CLI (`drunken-doctor`, `drunken-away`, `drunken-usage`, …), 49 test files, CI, 9 pre-commit hooks.
- `~/Projects/ai-team-toolkit` — GitHub `drunken-ai-team`. The skills and agents installed into
  `~/.claude/`.

**Neither has been touched, and neither may be until this repo is released and verified.** They
are the fallback. `ai-team-toolkit` is scheduled for termination *after* that, not before.

**Brand.** *Drunken Programmer* is the pen name and the future org; `drunken-guild` is the
product. The name came from `.guild_templates/` in the old repo, which already meant "the standard
other projects copy" — a guild is a craftsmen's association holding a shared standard, which is
what this repo is for. `drunken-tavern` was rejected (collides with SillyTavern, 32k stars, same
AI space); plain `drunken` was rejected as unfindable. Both are still free on PyPI.

The joke has to survive contact with the work: **the name says drunk, the contents are FATAL
directives, blast-radius checks and post-mortems.** That tension is the brand. Do not soften
either half.

---

## 1. Live coordinates — all verified, not assumed

| | value |
|---|---|
| GitHub | `https://github.com/sornbuen15/drunken-guild` · public · default branch `develop` |
| Branches | `develop`, `main` (both at the same commit; nothing released yet) |
| Tags | **none, deliberately.** See §4. |
| Jira | key **`DG`**, name `Drunken-Guild`, **team-managed (`next-gen`)** |
| Discord | new room; channel id is in the registry, **not in any file here** |
| Registry | `~/.drunken/projects.json` — `drunken-guild` added alongside `drunken-team`, `beta`, `alpha`. Backup at `projects.json.bak-*` |
| `drunken-doctor --project drunken-guild` | 17 ok · 0 warning · 0 failed |

**Jira `DG` was verified against the API, not just the doctor.** DT-260 records that
`drunken-doctor` checks the credential with `/myself` and never that the project key exists — it
printed `OK … (project ALPHA)` while Jira answered *"No project could be found"*. A direct
`GET /rest/api/3/project/DG` returned `key=DG name=Drunken-Guild style=next-gen`.

`style=next-gen` confirms the three limits still apply: **`priority` cannot be set** (urgency is a
label), **no story points**, and **backlog membership is not a status**.

**Discord is verified.** A real message was posted to the new room on 2026-08-22 — message id
`123456789012345678`, author `drunken-guild-app` (bot). The bot is in the room, the credential
resolves, and the channel id is right. `drunken-doctor` could not have told you any of that; it
only checks that a channel id is set.

**Found while doing it — worth a ticket.** `require_discord()` returns the credential as the
**unresolved reference string** (`file://…#discord.default`), while `require_jira()` returns a
`ResolvedJira` carrying a ready `auth_header`. The two are not symmetric and nothing says so, so
the obvious call sends the literal reference as a bearer token and Discord answers `401
Unauthorized` — which reads exactly like a bad token or a bot that was never invited, when both
are fine. Callers must pass it through `core.secrets.resolve()` themselves.

That contradicts this repo's own rule that *"every error carries a remediation, because 'unknown
project' only tells an agent to give up"*. Either make `require_discord()` resolve like its Jira
twin, or have it return a type that cannot be mistaken for a token.

---

## 2. Why the merge — the evidence, so nobody re-litigates it

Skills and agents were authored in **four** places, 26 duplicated by name:

| where | count |
|---|---|
| `drunken-team/skills/` | 14, flat |
| `drunken-team/.agents/skills/` | 25, Antigravity variants |
| `drunken-ai-team/skills/` | 29, categorised |
| `drunken-ai-team/agents/` | 15 |

Hand-syncing four surfaces does not work, and the session that produced this repo proved it twice:

- **`git-workflow` had silently diverged** — 73 lines against 196 — while a just-merged PR told
  one repo to defer to the other's copy.
- **`skills/.external` declared four skills "third-party with no source here"** while their source
  was the sibling repo the whole time.

Same class of failure as the local kanban board: *two surfaces that can disagree*. One surface is
the answer.

---

## 3. What is already done

`develop` at `b4b1844`. **319 commits — both histories intact**, brought in by subtree rather than
copied.

- `skills/` — **36**, one categorised tree
- `agents/` — 15
- `templates/` `examples/` `_not_used/` `scripts/install/` — moved as-is
- `skills/.external` — **empty on purpose**, and says why in the file
- `.mcp.json` — points at `--project drunken-guild` (it arrived pointing at `drunken-team`)

Of `drunken-team`'s flat 14: six were superseded and moved to
`_not_used/skills-superseded-by-toolkit/` with a note; the other seven were real and got
categorised (`debug-mantra`, `post-mortem`, `scrutinize`, `release-notes-writer` → `workflow/`;
`management-talk` → `leadership/`; `confluence-sync`, `acronym-namer` → `documents/`).

---

## 4. Versioning starts from zero

Every tag was deleted deliberately. This repo inherited two incompatible series — `drunken-team`'s
`v1.3.0`→`v2.3.0` and the toolkit's `v1.0.0`→`v1.1.0` — which read as one line but were two
products. Both remain in their source repos; nothing was lost.

**The first release of `drunken-guild` is `v1.0.0`.** `pyproject.toml` still declares
`name = "drunken-team"`, `version = "2.3.0"`; both are wrong now and are Phase 1 work.

---

## 5. The plan

Ordered. Each phase should merge on its own without breaking the one before it.
**An agent opens PRs; a human merges them.** Branch from `develop`, PR into `develop`.

### Phase 1 — the identity files, written from scratch  ⬅ **start here**

Everything at the repo root still belongs to `drunken-team`:

| file | state |
|---|---|
| `CLAUDE.md` | drunken-team's, with a stale banner on top. Good rules, wrong repo. |
| `README.md` | opens `# Drunken Team` |
| `pyproject.toml` | `name = "drunken-team"`, `version = "2.3.0"` |
| `GETTING_STARTED.md` | the toolkit's — skills only, no MCP |
| `.incoming/` | 4 files parked from the merge: the toolkit's `CLAUDE.md`, `README.md`, `SESSION_CHECKPOINT.md`, `.gitignore`. Read, then delete the directory. |

Write new ones. They must serve a repo that is **both** a Python package and a skill/agent
library, which neither source file did. Settle these, which the old pair disagreed on or never
stated:

- Which parts of the tree the Python gates cover (`src/`, `tests/`) and which are markdown. The
  pre-commit hooks already skip markdown — `ruff`/`ruff-format`/`mypy` reported *"no files to
  check"* on every markdown commit — but **CI has no `paths` filter**, so a docs-only push runs
  the full Python matrix. Three lines fixes it.
- **The DT-250 wrapper-layout exception.** `drunken-team`'s rule says the wrapper is not a git
  repo and the AI layer stays out of git, and that it applies to *"every project including this
  one"*. It never held for `drunken-team`, and it deliberately does not hold here: the AI layer
  **is** the product, and applying it literally moves the deliverable out of version control. ALPHA
  is the one project that follows it. Say so, or an agent will "fix" this repo by moving `skills/`
  out of git.
- The skill- and agent-authoring rules, which only the toolkit side had.
- Point the git rules at `skills/workflow/git-workflow/SKILL.md` and **do not restate them.**

### Phase 2 — one source for Antigravity, not two

**Boss's requirement: never maintain two copies.** Antigravity reads the *same* skills, agents and
MCP servers as Claude. Only if something genuinely cannot be shared does Antigravity get its own,
created on the Antigravity side.

`.agents/skills/` here still holds **25 directories**: the 15 agent twins, `jira-tickets`,
`ask-boss`, and 8 stubs already assessed and rejected as duplicates of richer agents
(`aitech-specialist`, `game-developer`, `insurtech-specialist`, `mobile-developer`,
`product-manager`, and three others).

1. **`jira-tickets` and `ask-boss` become first-class skills** under `skills/`. They are the only
   unique content in `.agents/skills/`, and **eight files here still reference `jira-tickets` at
   the absolute path `~/Projects/drunken-team/.agents/skills/…`** — five skills, `principal-engineer`,
   `CLAUDE.md` and `templates/CLAUDE.md`. Moving it in makes those relative and kills the last
   cross-repo dependency.
2. **The 15 twins stop existing as files.** `install_agents.sh` generates both variants from the
   single `agents/` source; the only real differences were `model:` (claude vs gemini) and the
   skill-index path.
3. **The 8 stubs → `_not_used/`** with a note per rejection.
4. **Antigravity points at the shared install.** A symlink `~/.gemini/config/skills` →
   `~/.claude/skills` is the obvious mechanism, **but `~/.gemini/config/skills` is a real
   directory holding ~66 entries, roughly 30 of which are not ours** (`accidental-data-loss-prevention`,
   `agile-workflow`, `acronym-namer`, …). **Survey it and find its owner before linking anything**
   — a careless symlink loses all of them. If a link is not safe, the install script writes both;
   that is the fallback, not the goal.

Write the Antigravity note in this phase, so it and Claude read the same rules.

### Phase 3 — install scripts, one per layer

Scripts, no wizard.

```
scripts/install/install_skills.sh    → ~/.claude/skills/
scripts/install/install_agents.sh    → ~/.claude/agents/  (+ the Antigravity variant)
scripts/install/install_mcp.sh       → writes/prints the .mcp.json snippet
```

`install_skills.sh` and `install_agents.sh` are already here and battle-tested — **rename and extend,
do not rewrite.** `install_skills.sh` carries `|| true` on every optional grep for a reason recorded
in its own comments: under `set -euo pipefail` an unmatched grep once killed the run after
printing a green success line, and 29 of 30 skills sat stale for two months.

**Both `INDEX.md` files are stale right now** — `skills/INDEX.md` lists 29 against 36 real skills.
They are generated by these scripts, so regenerate as part of this phase rather than by hand.
(Hand-generation was tried and drifted two bytes per description from the script's output.)

The `.mcp.json` snippet the script emits must use an **absolute** path:
`uv --directory /abs/path/to/drunken-guild run python -m jira_mcp.server --project DG`.
The form in this repo's own `.mcp.json` is cwd-relative (`uv run` + `PYTHONPATH: src`) and works
only from inside the checkout — copied into a consuming project it silently fails.

### Phase 4 — release `v1.0.0`, then the package (optional)

`develop` → `main` by PR titled `chore(release): v1.0.0`, merged **with a merge commit** (no
squash), tagged only after the merge lands. Tagging first tags a commit that is not on `main`,
which is worse than not tagging because it looks right.

The package (`pip install drunken-guild`, CLI `drunken`) is last and optional. If it happens, the
six `drunken-*` console scripts collapse into `drunken <subcommand>`, old names kept as aliases.

---

## 6. What needs the Boss

- **Merge every PR.** An agent opens them; a human merges them. No exception.
- **Terminate `ai-team-toolkit` only after** this repo is released and verified.

---

## 7. Things that will bite you

- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`.** They are the fallback.
- **`~/.claude/` follows this repo now.** If an install here disagrees with what is in `~/.claude/`,
  this repo wins.
- **Directory renames come last**, by the Boss's instruction.
- **An agent does not delete.** Retired things move to `_not_used/` with a note saying why and what
  replaced it. Anything needing a recursive force-delete becomes a list handed to the Boss.
- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal.
  Config precedence is fixed: environment variable, then registry, then `.agents/*.json`; nothing
  discovers a file by climbing.
  `ai-team-toolkit`'s untracked `scripts/ask_boss.py` and `scripts/discord_listener.py` **hardcode
  a Discord channel id**. They were never committed. Do not bring them across in that state.
- **`drunken-board-mcp` is still packaged.** `pyproject.toml` exposes `board_mcp.server:main` as a
  console entry point and `board_mcp` is in `packages`, so `pip install` puts a runnable
  `drunken-board-mcp` on PATH. It is correctly absent from `.mcp.json` and nothing runs it, but
  every `board_*` tool is retired. Decide whether *marked unused* should also mean *not shipped*.
- **A ticket marked IN REVIEW is not merged code.** Verify against `origin/develop` before
  believing any claim that something is fixed.
