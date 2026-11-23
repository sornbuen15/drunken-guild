# Local CI handoff before a pull request

When a project has selected Local CI for PR checks and the check runs on another machine, use
this sequence after finishing the change. macOS owns the feature branch and PR; Windows runs the
Local CI check:

1. On macOS, merge the latest PR base branch (e.g. `develop`) into the feature branch, then push
   it. Local CI fetches from GitHub, so unpushed commits cannot be checked.
2. Hand the branch name and pushed head SHA to the Windows operator. On Windows, fetch that branch
   and confirm the checkout is at the handed-off SHA before running `ci check --profile full`.
   Inspect `report.json` and return the report path, SHA, overall result, and each check status.
3. If `overall` is not `pass`, fix the issue on macOS, push the updated branch, and repeat the
   Windows check on the new pushed head SHA. Never open a PR on a failing or stale report.
4. Once `overall=pass`, run `ci verify <report.json> --json` on Windows. Return the verification
   result to macOS. Confirm the report SHA equals the current pushed branch head; if verification
   fails or the head changes, push the new head and repeat the full check and verification.
5. Only after Windows verification confirms the current pushed SHA, open the PR on macOS. Include
   the report SHA, `overall`, the verify outcome, and every `skipped` or `not_run` check, using
   `skills/documents/concise-docs/references/pull-request.md`.

If Windows-side CI is unavailable, do not open the PR as ready. State `not_run` and the observed
reason, then hand off to the Boss. Do not treat local tests as a CI pass. If the project has not
selected Local CI, follow its normal PR workflow; no local CI report is required.
