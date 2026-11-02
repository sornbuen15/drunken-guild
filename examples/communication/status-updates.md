# Work status update scenarios

Use these as manual review cases for `clear-responses`. The answer should stay
brief and name the task, evidence-backed state, and next action where relevant.

| Evidence available | Suitable update |
|---|---|
| Task alpha's guidance and examples are edited; focused checks passed; no command is running. | `alpha: Updated status guidance and examples; focused checks passed. No command is running now. Next: review the diff.` |
| A named test command is still running in a visible session. | `alpha: The status scenarios are written. The focused test command is still running in session <id>; next I’ll report its exit result.` |
| The required test environment cannot be accessed and no code changed. | `alpha is blocked: the test environment is unavailable, so I have not run the checks. Next: use an approved environment or report the limitation.` |
| A branch has uncommitted changes, but no command, tool operation, or assistant turn is active. | `alpha has uncommitted changes, but no work process is running. Next: resume the review when you ask.` |

Reject updates that say work is continuing in the background based only on a
branch, open PR, or uncommitted files. Do not require a fixed format for
ordinary answers.
