# Session Checkpoint

**Read this, then `CLAUDE.md`.** This says where things stand and what is next.
`CLAUDE.md` says how to work. `DESIGN.md` says why the repo is shaped this way.

**Finished work does not live here.** It is in the ticket, the commit, or `RETIRED.md`.

Last updated 2026-08-23 · `develop` at `c0943a8` · CI green · **no tags yet, deliberately**

---

## 1. Do these first

Numbered because the order matters. Everything else waits on 1 and 2.

### 1. Boss — reinstall the runtime

**Why:** the trunk is 4 files ahead of what is installed. Until this runs, `drunken-jira-mcp`
still flattens every ticket body to paragraphs (DG-279 is merged but not live), and
`sync_customizations.py` still climbs.

```bash
cd ~/Projects/drunken-guild && uv tool install . --reinstall
```

**Done when:** `uv run drunken-doctor --project drunken-guild` shows `deployment.tool_env` green.
One warning survives on purpose — `deployment.mcp_pin`, because `uv tool install` ignores
`uv.lock`.

### 2. Boss — fix Antigravity's MCP config · **DG-277**

**Why:** it declares five servers. Three cannot start — `drunken-board-mcp`'s executable is gone
(DG-265), `kanban-server.js` is not on disk, and `npx @modelcontextprotocol/server-jira` is a 404
on npm. The two that work point at project `drunken-team`, the fallback repo.

**Where:** `~/.gemini/antigravity-cli/mcp_config.json`. Editing under `~/.gemini` is an install,
so an agent may not do it.

```bash
cp ~/.gemini/antigravity-cli/mcp_config.json ~/.gemini/antigravity-cli/mcp_config.json.pre-DG-277.bak && cat > ~/.gemini/antigravity-cli/mcp_config.json <<'JSON'
{
  "mcpServers": {
    "drunken-jira-mcp": {
      "command": "/Users/r.jakkawan/.local/bin/drunken-jira-mcp",
      "args": ["--project", "drunken-guild"]
    },
    "drunken-discord-mcp": {
      "command": "/Users/r.jakkawan/.local/bin/drunken-discord-mcp",
      "args": ["--project", "drunken-guild"]
    }
  }
}
JSON
```

**Do not** run `install_mcp.sh` instead. It merges by design, so it fixes the two live entries and
leaves all three dead ones in place.

**Done when:** `agy` starts with two MCP servers and no startup error.

### 3. Antigravity — start the epic · **DG-283**

Blocked until 2 is done. Five stories under it, each saying what must be true and where Claude's
method is documented — **not** the steps. Antigravity plans its own approach and breaks its own
tasks.

| ticket | what |
|---|---|
| DG-284 | consume the shared skills without holding a second copy |
| DG-285 | consume the shared agents; say which per-agent differences are legitimate |
| DG-286 | keep MCP config generated from the registry, not hand-written |
| DG-287 | prove both directions with a read-only call before either agent writes |
| DG-288 | agree who owns the working tree, and write that rule in one place |

**Suggested order:** 284 → 285 → 286 → 287 → 288. The first three make the layers shared; 287
proves the channel; 288 is the rule that makes concurrent work safe.

**The constraint on all five, from the epic:** skills, agents and MCP servers are never rewritten
for Antigravity. One source, `drunken-guild`. A change is made once and reaches both agents. Copy
and rewrite only where Antigravity genuinely cannot consume the shared form — say so on the ticket,
and keep the copy generated.

### 4. Boss — decide the release

Nothing blocks `v1.0.0` but the decision. The flow is in
`skills/workflow/git-workflow/SKILL.md`; the three things that go wrong are:

1. PR `develop` → `main`, titled `chore(release): v1.0.0`
2. Merged **with a merge commit**, no squash — strategy is chosen by target
3. Tag **only after the merge lands**. Tagging first tags a commit not on `main`, which looks
   right and is not

`drunken-doctor`'s `version.declared` check goes from skipping to asserting the moment the first
tag exists.

---

## 2. Live coordinates — verified 2026-08-23

| | |
|---|---|
| GitHub | `sornbuen15/drunken-guild` · public · default branch `develop` · 0 forks |
| Jira | key `DG`, team-managed — no `priority`, no story points, backlog ≠ status |
| Registry | `~/.drunken/projects.json` — `drunken-guild`, `drunken-team`, `beta`, `alpha` |
| Repo | 38 skills · 15 agents · 389 commits · suite 724 passed |
| Dependabot | **0 open alerts** (was 4) |
| Tooling | Claude Code 2.1.206 · `agy` 1.1.1 · `drunken-guild` 1.0.0 installed |

---

## 3. Two things that will bite you

**The AI layer is installed and current; the runtime is not.** `drunken-doctor` reports both
separately. `ai_layer.*` is green, `deployment.tool_env` is not — see item 1.

**`_not_used/` is no longer committed** (DG-291). It still exists on disk and an agent still moves
retired things there, but the tracked record is `RETIRED.md` at the root. **Add the row there in
the same change** — that row is the only part a fresh clone gets.

---

## 4. Decisions taken, so they are not reopened

| decision | why | ticket |
|---|---|---|
| Git history is **not** being purged of `_not_used/` | it would kill the recovery commits `RETIRED.md` points at, for 323 KB of a 4.3 MB repo. The accidental-copy risk was removed by untracking | DG-291 |
| `requirements.txt` retired, not regenerated | nothing read it; reproducible installs come from `uv.lock`, exported on demand | DG-281 |
| Drift in the deployment **warns**, does not fail | matches `ai_layer.source` and the missing-module branch beside it; the failure being fixed was a green line, not an ignored yellow one | DG-278 |
| No `.github/dependabot.yml` | `exclude-paths` suppresses pull requests, not alerts. Adding a file that cannot solve the problem is worse than adding none | DG-290 |

---

## 5. Still open, and owned by nobody yet

- **DG-263** — four skills (`debug-mantra`, `post-mortem`, `scrutinize`, `management-talk`) are
  byte-identical to the `9arm-skills` plugin, whose pack carries no licence file. This repo is
  public and MIT. The finding and three options are written into `skills/.external`.
  **This is the Boss's call, not an agent's.**
- **Two stale editable installs** in pyenv 3.14.3's site-packages — `drunken_agy 1.1.0` and
  `drunken_team 1.6.0`, pointing at `~/Projects/drunken-team`. `tests/conftest.py` refuses to run
  in that state since DG-268, so nothing depends on removing them. They should still go.
- **Follow-up on DG-262** — `deployment.tool_env` should warn when a legacy tool root exists
  *alongside* a current one, not only when the current one is absent.

---

## 6. Standing constraints

- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`.** They are the fallback
  until this repo is released and verified.
- **Do not touch `~/.gemini/antigravity-cli/brain/*/worktrees/`.** That belongs to Antigravity.
- **An agent does not install and does not delete.** Hand the command to the Boss.
- **Directory renames come last**, by the Boss's instruction.
- **A ticket marked IN REVIEW is not merged code.** Verify against `origin/develop`.
