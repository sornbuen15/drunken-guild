# `_not_used/` — retired, kept

Nothing in this repo is deleted. Anything retired is moved here with a note saying **why it
was retired and what replaced it**, so a later reader can tell "deliberately withdrawn" from
"lost".

Two things follow from that:

- **Nothing here is discovered by tooling.** `sync_skills.sh` and `sync_agents.sh` find their
  input with `find skills/ -name SKILL.md` and `agents/*.md`. A file that has moved here is
  outside both, so it stops being installed the moment it moves — no exclude list is needed.
- **What is already installed stays installed.** The next `sync_skills.sh` run will list the
  retired skills under *"Installed but not produced here"*. That is the intended behaviour:
  reported, never deleted. Removing them from `~/.claude/skills/` is the operator's call.

Each retired directory carries a `RETIRED.md` next to the original file. The original file is
left byte-for-byte as it was.

## Contents

| path | retired | why |
|---|---|---|
| `skills/agentic-kanban` | 2026-08-22 | local board retired for Jira; orchestration cancelled |
| `skills/kanban-io` | 2026-08-22 | it *was* the local board interface |
| `skills/next-task` | 2026-08-22 | claim-and-pick has no Jira equivalent and needs none |
| `skills/squad-workflow` | 2026-08-22 | coordination protocol built on `board_*` orchestration |
| `examples/04-next-task` | 2026-08-22 | example output of a retired skill |
| `examples/05-agentic-kanban` | 2026-08-22 | example output of a retired skill |
| `scripts/kanban` | 2026-08-22 | CLI fallback for a board that no longer exists |
| `scripts/mcp` | 2026-08-22 | the MCP server that defined every `board_*` tool |
| `templates/mcp-settings.json` | 2026-08-22 | it registers the server above, and nothing else |
| `examples/pre-jira-fixtures` | 2026-08-22 | the `board/` output of examples 01-02, whose skills survive |
