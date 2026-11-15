# Pull request description

Use this shape for one focused task. Keep each section short and make the task identifiable at a glance.

## What

Task: DG-XXX — <short task title>

<What changed, in one paragraph.>

## Why

<The user or project problem this change addresses, in one paragraph.>

## Checklist

- [ ] <Check run> — <actual result>
- [ ] <Relevant check not run> — <reason>
- [ ] No unrelated changes; no install, deploy or merge performed unless explicitly authorized.

## Evidence

For a local CI report, record:

- Profile and run ID.
- Report SHA and `overall` result.
- The actual `ci verify PATH/report.json --json` outcome.

When Local CI is available, run the `full` profile before PR handoff. Treat a report as current only when verification confirms its SHA matches the branch head and `overall=pass`. If Local CI is unavailable, state `not run` and why; never imply a pass.

| Check | Status | Summary |
|---|---|---|
| <check id> | <pass/fail/timeout/skipped/not_run> | <actual report summary or reason> |

List every `skipped` and `not_run` check and any failed optional check. If verification was not run or did not confirm the current SHA, say so plainly; do not present the report as a passing PR gate.
