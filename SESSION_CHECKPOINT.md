# Session Checkpoint — drunken-guild

**Read this first, then `CLAUDE.md`.** This file says where things stand and what to do next.
`CLAUDE.md` says how to work.

Rule for this file: **finished work does not live here.** It goes to the commit, the ticket, or
`CLAUDE.md`, and this file links to it. Everything Phases 1–3 covered has been cut for that reason
— the history is in DG-261 through DG-272 and in the git log.

Last updated: 2026-08-22 · `develop` at `c02fcbb`, CI green · **no release yet, no tags on purpose**

---

## 1. Live coordinates — verified, not assumed

| | value |
|---|---|
| GitHub | `https://github.com/sornbuen15/drunken-guild` · public · default branch `develop` |
| Tags | **none, deliberately.** First release is `v1.0.0`; `pyproject` already declares it |
| Jira | key **`DG`**, team-managed (`next-gen`) — no `priority`, no story points, backlog ≠ status |
| Registry | `~/.drunken/projects.json` |
| Repo contents | 38 skills · 15 agents · MCP servers and CLI in `src/` |
| Claude Code | `2.1.206` at `~/.local/bin/claude` |
| Antigravity | `agy 1.1.1` at `/opt/homebrew/bin/agy` |

**Both halves are installed and current.** `~/.claude/skills`, `~/.claude/agents` and
`~/.gemini/config/skills` (86 entries: ours plus ~30 Apache-2.0 skills shipped by Google, which are
not ours to touch) all match the source — `drunken-doctor` checks this now and reports `ai_layer.*`.

---

## 2. Three things are true right now and will bite you

- **The deployed CLI is current, and was not until 2026-08-22.** `uv tool list` now shows
  `drunken-guild v1.0.0` and `drunken-board-mcp` is gone from PATH. It took an uninstall first —
  `--force` repoints the symlinks and leaves the old environment shipping the retired server:

  ```bash
  uv tool uninstall drunken-team || true   # only if `uv tool list` still shows it
  uv tool install .
  ```

  `drunken-doctor` reports `deployment.tool_env` and names an install under the previous package
  name rather than skipping, so this state is visible rather than assumed.

- **Four skills are not ours and their licence is unknown.** `debug-mantra`, `post-mortem`,
  `scrutinize`, `management-talk` are byte-identical to the `9arm-skills` plugin, whose pack carries
  no licence file. This repo is public and MIT. The finding and three options are written into
  `skills/.external` (DG-263). **This is a decision for the Boss, not an agent.**

- **Two stale editable installs live in pyenv 3.14.3's site-packages** — `drunken_agy 1.1.0` and
  `drunken_team 1.6.0` — pointing at `~/Projects/drunken-team`. They made every local `pytest` run
  the fallback repo's code for two rounds of review. `tests/conftest.py` now refuses to start in
  that state (DG-268), so nothing depends on removing them, but they should go.

---

## 3. Next session — make Claude and Antigravity work together

**This is the goal: two agents running work in parallel off one board.** Both CLIs already take a
non-interactive prompt, both read the same skills and agents, and both can reach the same Jira.
What is missing is the wiring and the rules that stop them colliding.

### 3.1 Fix Antigravity's MCP config first — nothing works before this

`~/.gemini/antigravity-cli/mcp_config.json` is stale in four ways. Read it, then correct it:

| entry | state | action |
|---|---|---|
| `drunken-jira-mcp` | `--project drunken-guild` | point at `drunken-guild` |
| `drunken-discord-mcp` | `--project drunken-guild` | point at `drunken-guild` |
| `drunken-board-mcp` | retired (DG-250/265) | remove |
| `kanban-board` | `ai-team-toolkit/scripts/mcp/kanban-server.js`, retired | remove |
| `jira-board` | `npx @modelcontextprotocol/server-jira` — a **fourth** Jira surface | remove |

Generate rather than hand-write: `./scripts/install/install_mcp.sh drunken-guild --out <path>`
emits absolute paths and **merges**, so entries that are not ours survive.

Do this *after* `uv tool install .`, or the absolute paths point into the old environment.

**Editing a file under `~/.gemini/` is an install. Hand the Boss the command; do not run it.**

### 3.2 Prove each direction with one read-only call

```bash
# Claude → Antigravity
agy -p "List the DG tickets in To Do and say which you would pick first, and why." \
    --project drunken-guild --mode plan

# Antigravity → Claude
claude -p "Read CLAUDE.md and summarise the git rules in five lines."
```

`--mode plan` and a read-only prompt are the point: prove the channel before either can write.

For the second direction, Antigravity's `settings.json` `allowed_commands` currently permits only
four `ask_boss.py` spellings, so `command(claude)` has to be added there. That is the Boss's file.

### 3.3 Decide the coordination rule *before* running anything in parallel

Two agents in one checkout will collide in git, not in Jira. Settle these:

1. **Who owns a ticket** — `jira_assign` already answers this and nothing else tracks it. One
   agent, one ticket, assignee set before work starts.
2. **Who owns the working tree** — the real risk. Options, cheapest first:
   - separate `git worktree` per agent, one branch each
   - Antigravity read-only: it reviews, runs acceptance tests, files tickets; Claude writes
   - alternate turns, never concurrent
   The middle option matches what `CLAUDE.md` already says Antigravity does, and needs no new
   machinery. Start there and widen only if it proves limiting.
3. **Who merges** — unchanged. An agent opens PRs; a human merges them.

### 3.4 What "done" looks like for this

- Antigravity answers a read-only prompt from Claude, against `drunken-guild`, with correct Jira.
- Claude answers a read-only prompt from Antigravity.
- One ticket is carried end to end by each, on its own branch, without touching the other's.
- The rule from 3.3 is written into `CLAUDE.md` and `.agents/AGENTS.md` — **the same rule in both**,
  because a per-agent copy is the failure this repo was built to cure.

### 3.5 Known unknowns — check, do not assume

- Antigravity has not run since **2026-07-10**. Assume nothing about its session state.
- `agy --print-timeout` defaults to 5 minutes. A real task will exceed it.
- Whether `agy` inherits this repo's `.mcp.json` or only its own global config is **unverified**.
- Nothing has tested two agents writing to the same Jira ticket at once.

---

## 4. Open tickets

| key | what |
|---|---|
| **DG-260** | `drunken-doctor` reports a project OK when its Jira project key does not exist |
| **DG-271** | `requirements-dev.txt` pins a different ruff than `pyproject` and still names `drunken-guild`. Regenerating moves ~35 packages and `pip-audit --strict` reads it — read that result before merging |
| — | Follow-up noted on DG-262: `deployment.tool_env` should warn when a legacy tool root exists *alongside* a current one, not only when the current one is absent |
| — | DG-263's licence decision, once the Boss makes it → new ticket referencing it |

---

## 5. Phase 4 — release `v1.0.0`

Not started, and nothing blocks it but the decision to do it.

1. PR `develop` → `main`, titled `chore(release): v1.0.0`
2. Merged **with a merge commit** — no squash. Merge strategy is chosen by target
   (`skills/workflow/git-workflow/SKILL.md`)
3. Tag **only after the merge lands**. Tagging first tags a commit that is not on `main`, which is
   worse than not tagging because it looks right
4. `drunken-doctor`'s `version.declared` check compares `pyproject` against the newest tag, so it
   goes from skipping to asserting the moment the first tag exists

Optional and last: publish as `pip install drunken-guild`, collapsing the `drunken-*` console
scripts into `drunken <subcommand>` with the old names kept as aliases.

---

## 6. Standing constraints

- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`.** They are the fallback
  until this repo is released and verified. `ai-team-toolkit` is terminated *after* that.
- **Do not touch `~/.gemini/antigravity-cli/brain/*/worktrees/`.** That belongs to Antigravity.
- **An agent does not install and does not delete.** Retired things move to `_not_used/` with a
  note; anything needing a recursive force-delete becomes a list handed to the Boss.
- **Directory renames come last**, by the Boss's instruction.
- **A ticket marked IN REVIEW is not merged code.** Verify against `origin/develop`.
