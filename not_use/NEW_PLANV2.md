The workflow must be able to be executed as commands:
1. init-project: Read PROJECT_SPEC.md and DESIGN.md (for existing projects, also read the source code), then design at high level, in architecture, using DDD-Document, and other methods as appropriate.
2. refinement: Plan the project and create a backlog on the Jira board.
3. sprint-planning: Move the planned tasks from the backlog to the sprint active board. **Each time you do planning, review all tasks in both the active board and the backlog, and adjust or modify their priority to determine what should be done first and last.**
The board will contain the following statuses:
TODO, IN PROGRESS, IN REVIEW, DONE
**Once sprint-planning is complete, start working immediately.** You can ask whether to choose to work in sequence or parallel.

- TODO: Status awaiting execution within the sprint.
- IN PROGRESS: Status currently being worked on.
- IN REVIEW: Status awaiting review by AI, humans, or both.
- DONE: Status having undergone unit testing, integration testing, smoke testing, or e2e testing (if necessary).

**Tasks on the board can be instructed to be executed in sequence or parallel.**
**If all tasks are in "in review" (not in todo and in progress), the system must perform integration testing and generate a test report before they can be moved to "done."**
**Parallel work should not involve the same role performing two tasks; instead, each role should handle its own task, depending on task suitability.**

4. Review-retro is used to check if the work already completed is sufficient.
Identify areas for improvement.
**Add the areas needing improvement to the backlog.** After review-retro is complete,
the user must decide whether to proceed with sprint planning. Simply answer yes or no.
**At this point, advise users whether to create a session checkpoint and close a new session or continue working, as sprints shouldn't be too long.**
**Every task will have a task ID, which must always be associated with a git branch.**
**Do not merge immediately with git; we only perform a PR merge into `develop`.**
**Merges into `main` or `master` must be initiated or commanded by the user.
**Release and tagging must also be initiated or commanded by the user.**
