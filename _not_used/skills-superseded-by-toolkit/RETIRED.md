# Retired — drunken-team's flat `skills/`, superseded by the toolkit's versions

**Retired:** 2026-08-22 · **Was:** `skills/<name>/SKILL.md` in `drunken-team` (flat, uncategorised)
**Replaced by:** the same-named skills under `skills/<category>/`, which are newer.

## Why

The merge that created `drunken-guild` found skills being authored in four places, and these were
the losing half of five name collisions. In every case the toolkit's version was newer, longer,
or byte-identical — never worse:

| skill | this copy | kept copy |
|---|---|---|
| `git-workflow` | 73 lines | **196 lines, v2.0.0** — merge strategy per target, and "an agent opens PRs; a human merges them" |
| `backlog-refinement` | 33 lines | **98 lines, v4.0.0** — moved onto Jira |
| `project-audit-reviewer` | 40 lines | **120 lines, v4.0.0** |
| `task-estimation` | 33 lines, v3.0.0 | **69 lines, v4.0.0** — prints, never writes back |
| `system-design-rules` | 64 lines, v1.2.0 | **byte-identical** — this copy was installed from the other one |

`git-workflow` is the one worth remembering: the two had drifted 73 against 196 lines while a
just-merged PR instructed one repo to defer to the other's copy. Nobody noticed. That divergence
is the single clearest argument for the merge.

Also here:

- **`next-task`** — already retired on the toolkit side when the local kanban board went. Its
  claim-and-pick has no Jira equivalent and needs none; see `../skills/next-task/RETIRED.md`.
- **`example`** — a template showing how to write an Antigravity skill, not a skill. The
  equivalent for this repo is `examples/contributing/SKILL-annotated.md`, which was rewritten
  and is current.

Kept, not deleted, because they are the record of what the MCP side believed before the merge.
