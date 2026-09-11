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

## Recovering one

```bash
git show <commit>:_not_used/<path>
git checkout <commit> -- _not_used/<path>
```

The last two rows are the exception: they were never inside `_not_used/` in git. They were removed
straight from where they lived, so recover them from their original paths instead —
`git show d41d99d:skills/workflow/debug-mantra/SKILL.md`, `git show ba6077c:.guild_templates/CLAUDE.md`.

Each retired directory kept its own `RETIRED.md` with the long reasoning; those are in the same
commits.

## Adding to this list

Move the thing into `_not_used/` as before, then add a row here. The row is the part that is
committed, so it has to carry the reason on its own — "see the directory" points at something a
fresh clone does not have.
