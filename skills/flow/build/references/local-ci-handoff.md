# Local CI handoff before a pull request

When a project has selected Local CI for PR checks, use this sequence after finishing the change:

1. Merge the latest PR base branch (e.g. `develop`) into the feature branch.
2. Push the branch. Local CI fetches from GitHub, so unpushed commits cannot be checked.
3. Run `ci check --profile full` on the pushed head SHA and inspect `report.json`.
4. If `overall` is not `pass`, fix, commit, push, and run `ci check --profile full` again on the new pushed head SHA. Never open a PR on a failing or stale report.
5. Once `overall=pass`, run `ci verify <report.json> --json`. Confirm the report SHA equals the current branch head. If verification fails or the head changes, push and repeat the full check and verification.
6. Only after verification, open a PR. Include report SHA, `overall`, the verify outcome, and every `skipped` or `not_run` check, using `skills/documents/concise-docs/references/pull-request.md`.

If the project has not selected Local CI, follow its normal PR workflow; no local CI report is required. If selected Local CI is unavailable, do not open the PR as ready. State `not_run` and the observed reason, then hand off to the Boss. Do not treat local tests as a CI pass.
