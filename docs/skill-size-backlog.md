# Skill and agent size backlog

The repository records document size as a review signal, not a merge gate.
The current heuristics are 120 lines for `SKILL.md` and 100 lines for agent
files. A larger file is not automatically wrong; it is a candidate for
review when the owning workflow is next improved.

Known follow-up candidates are recorded in
`scripts/skill_size_baseline.json`. The current PR also reports
`skills/flow/build/SKILL.md` at 121 lines. The next improvement should decide
whether its local-CI evidence guidance belongs in a reference document, but
that refactor is intentionally separate from the feature change.
