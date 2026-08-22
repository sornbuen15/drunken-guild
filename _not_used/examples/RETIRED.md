# Retired — `examples/04-next-task`, `examples/05-agentic-kanban`

**Retired:** 2026-08-22 · **Was:** `examples/04-next-task/`, `examples/05-agentic-kanban/`
**Replaced by:** nothing. They are the recorded output of skills that no longer exist.

Both examples exist to show what a skill produces. `next-task` and `agentic-kanban` were retired
on the same day (see `../skills/*/RETIRED.md`), so there is no run left to record.

They are also the last two `board/` fixtures in `examples/`: each ships a directory of
`board/<lane>/TASK-NN.md` files as its expected output, which is exactly the local board that
`CLAUDE.md` now forbids. `examples/01-spec-to-backlog` and `02-backlog-refinement` carry the same
fixture shape but cover skills that survive, so those get rewritten against Jira rather than
retired.

Kept because they are the clearest surviving record of how the board actually looked in use —
lanes, task frontmatter, claim timestamps — which is worth having when reading the retired
skills.
