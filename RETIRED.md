# Retired — the index

What this project has withdrawn, why, and what took its place. **This file is the record;
the content itself is not tracked.**

`_not_used/` still exists on disk, and an agent still moves retired things into it rather than
deleting them. It is no longer committed (DG-291). Nothing was lost in making that change — every
path below is reachable from the commit named beside it.

## Why the content is not published

The rule "an agent does not delete" exists so work is not lost. It is not a rule to publish, and
the two had been conflated: `_not_used/` was tracked because `.gitignore` never mentioned it, not
because anyone decided it should be. Sixty-seven files of withdrawn code sat on a public MIT
repository, and it cost more than disk:

- **A drifted duplicate was being published beside the real file.**
  `skills-superseded-by-toolkit/git-workflow/SKILL.md` is 73 lines against the live file's 196.
  Those are the exact numbers `CLAUDE.md` cites as this project's founding disaster. The repository
  that exists to eliminate that duplicate was shipping it where anyone could copy the wrong one.
- **It generated real work.** Dependabot raised three alerts against a retired lockfile for a
  package version nothing installs, crowding a genuine `cryptography` alert; then opened
  [#23](https://github.com/sornbuen15/drunken-guild/pull/23) to bump it, which was merged, and which
  conflicted with the pull request retiring that very file.
- **It was a second archive.** Git history is the first. Keeping a parallel copy of withdrawn code
  in the tree is the two-surfaces failure this repository was built to cure, turned on itself.

## What is here

| what | why it went | replaced by | recover from |
|---|---|---|---|
| `board-mcp/` — `src/board_mcp/` and three test modules | a board beside Jira is a second surface that can disagree with the first (DG-250). The project's own board held three cards last touched 2026-07-22, using a prefix retired in DG-244, while every real ticket went through Jira | Jira, via `drunken-jira-mcp` | `ed42b6c` |
| `skills/` — `agentic-kanban`, `kanban-io`, `next-task`, `squad-workflow` | all four read or wrote the local board | nothing; the board is gone | `abe5df1` |
| `scripts/` — `scripts/kanban/`, `scripts/mcp/` | the local board's implementation, including `kanban-server.js` | `drunken-jira-mcp` | `abe5df1` |
| `examples/` — `04-next-task`, `05-agentic-kanban`, `pre-jira-fixtures/` | recorded output of skills that no longer exist, and the last `board/<lane>/` fixtures | nothing | `abe5df1` |
| `skills-superseded-by-toolkit/` — the losing half of five name collisions | authored in four places; in every collision the kept copy was newer, longer, or identical — never worse | the same-named skills under `skills/<category>/` | `abe5df1` |
| `agent-layer-stubs/` — eight stubs from `.agents/skills/` | each was a thinner copy of something richer, or a persona written before the roster settled. Assessed one at a time, because "it looks like a duplicate" is how real content gets lost | `agents/`, now the single source Antigravity reads | `b72b433` |
| `requirements/` — `requirements.txt` | 113 lines adrift from `pyproject.toml`, and nothing read it | `uv.lock`, exported on demand | `4c4c97c` |
| `templates/mcp-settings.json` | superseded by generated MCP configuration | `drunken-config` | `abe5df1` |
| `vendored-skills-unlicensed/` — `debug-mantra`, `post-mortem`, `scrutinize`, `management-talk` | never authored here. All four are byte-identical to the `9arm-skills` pack, which carries no licence file and no reachable upstream, so this repository could not redistribute them under its own MIT licence (DG-263). What a session actually loaded was never this copy — the installed files are symlinks into that pack | nothing. `think-analyze-isolate` covers the running-things half of `debug-mantra`; the rest have no replacement here | `d41d99d`, at their original `skills/` paths |
| `guild-templates/` — the whole `.guild_templates/` set: `CLAUDE.md`, `.cursorrules`, `CONVENTIONS.md`, `.aider.conf.yml`, `SESSION_CHECKPOINT.md` | a second template set beside `templates/`, and the stale one — it told agents to shell out to the Jira bridge script, parked work with a retired `board_*` tool, gave three commit formats none of which is `git-workflow`'s, and its Aider config loaded a path that exists in no project it was copied into. It was still the set `Integration-Guide.md` sent new projects to (DG-337) | `templates/`, where the Cursor, Aider and checkpoint files were rewritten to defer to the project's `CLAUDE.md` rather than restate it. `check_doc_drift.py` fails any document that names the old set | `ba6077c`, at `.guild_templates/` |
| `scripts/` — `clean_host_config.py`, `migrate_env_to_registry.py`, and `tests/test_clean_host_config.py` | first step of the 2.0.0 re-scope (DG-348, group 8). No file referenced `clean_host_config.py`: `drunken-config --kind host` already prunes this project's retired servers on every regeneration (DG-286). `migrate_env_to_registry.py` was a one-off `.env` migration that had done its job, and its only live mention was a remediation message pointing new users at it (DG-351) | `drunken-config --kind host` for host config; `scripts/set_secret.py` for putting a credential into `secrets.json`, which the onboarding error now names | `195c9ea`, at their original `scripts/` and `tests/` paths |
| `antigravity-plumbing/` — `.agents/AGENTS.md`, `.agents/hooks.json`, `templates/AGENTS.md`, `scripts/install/install_host_docs.sh`, `scripts/check_worktree_isolation.py`, `scripts/sync_customizations.py`, their tests; and, edited out in place, the `toolCall` branch of `approval_hook.py` (payload mapping, its own `render`, the payload debug log and `paths.antigravity_payload_debug_path`), `doctor`'s `~/.gemini` roots, and the Antigravity trees of both install scripts | Antigravity had been "supported, not recommended" since DG-301, and this was plumbing only it used — including a copy of `CLAUDE.md` that put the deny list in a file the hook never reads (DG-340). Inventory group 6 of the 2.0.0 re-scope, approved by the Boss 2026-09-11 (DG-349). Another agent is not banned: it follows the same rules as Claude, with its own name in the author and the `agent:` label | the rules in `CLAUDE.md` (a vendor-neutral `AGENTS.md` is the re-scope's target); `git-workflow`'s One Working Tree rule, now vendor-neutral, for what `check_worktree_isolation` enforced | `195c9ea`, at their original paths |
| `skills-no-flow/` — skills `python-quality-gates`, `project-hygiene`, `confluence-sync`, `zero-defect-mindset`, `ai-output`; `scripts/confluence_bridge.py` and `tests/test_confluence_bridge.py` | none serves a step of the 2.0.0 flow (/prd → /clarify → /ddd → /breakdown → /build → /audit). `python-quality-gates` hard-coded this repo's layout into a skill installed everywhere (DG-347); `project-hygiene` already deferred every rule to `git-workflow`; `confluence-sync` could not run outside this repo and hard-coded one project's ADRs (DG-346); the two mindset skills restated what the build step does. Groups 2 and 3 of the re-scope, approved by the Boss 2026-09-11 (DG-352). The fifteen general skills that moved in the same change are *not* retired — they live unchanged in `plugins/drunken-extras/skills/` | a project's own build/test/lint commands in its `AGENTS.md`; `git-workflow`; the `/build` step | `fcc52de`, at their original `skills/` and `scripts/` paths |

## Recovering one

```bash
git show <commit>:_not_used/<path>
git checkout <commit> -- _not_used/<path>
```

Rows whose last column names an original path are the exception: those things were never inside
`_not_used/` in git. They were removed straight from where they lived, so recover them from there
instead — `git show d41d99d:skills/workflow/debug-mantra/SKILL.md`,
`git show ba6077c:.guild_templates/CLAUDE.md`, `git show 195c9ea:scripts/migrate_env_to_registry.py`,
`git show 195c9ea:.agents/AGENTS.md`.

Each retired directory kept its own `RETIRED.md` with the long reasoning; those are in the same
commits.

## Adding to this list

Move the thing into `_not_used/` as before, then add a row here. The row is the part that is
committed, so it has to carry the reason on its own — "see the directory" points at something a
fresh clone does not have.
