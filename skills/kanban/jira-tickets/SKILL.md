---
name: "jira-tickets"
description: "How to write and run a ticket in this project: the three-part shape, the fields this Jira can actually set, the status lifecycle, and what must be verified before anything is called Done."
---

# Skill: Tickets

**Version:** 1.0.0
**Applies to:** every agent working this project — Claude, Antigravity, anything else.

Jira is the only coordination surface. The **assignee** says whose the work is,
the **status** says where it is. Nothing else tracks either.

---

## 1. Should this be a ticket at all?

**Yes** — work someone else may pick up, a defect, a security finding, a
decision that must survive the session.

**No** — anything the repository already records. Code structure, what a commit
did, why a function looks like that. Git and the code say those better, and a
ticket restating them is a second surface that can disagree.

**Also no** — a step inside work you are doing right now. That is a commit.

---

## 2. The shape

Three headings. Nothing else.

```
FINDING     what is true that should not be, or what is missing
SCOPE       what will change. Bullets.
ACCEPTANCE  how anyone can tell it worked
```

**A ticket is read, not experienced.** It is scanned by someone deciding what
to pick up. Write declaratively.

Do not write:

- `Found 2026-08-19 while verifying DG-252 by running drunken-doctor…`
- `WHY IT MATTERS BEYOND THIS ONE FILE`
- `Every surface agreed. The only wrong thing was…`

That is a story, and stories belong in the **commit message and the PR**, where
someone reading the diff needs them. Put the same facts in the ticket as
statements.

### Length

| kind | budget |
|---|---|
| task, bug, chore | **≤ 120 words.** If it needs more, it is two tickets or it needs a parent |
| post-mortem, security finding | as long as it takes — these are the record |

The project's own older tickets run about 49 words. Five written in one session
averaged 600. The rule exists because of the second number.

### Summary line

`[Area] imperative statement of the change`

`[CI] Fail the commit when .gitignore excludes a source file` — not
`[CI] Investigation into gitignore behaviour`.

---

## 3. Fields: what this Jira can and cannot do

Read `jira_board_info` rather than assuming. It reports the issue types this
project accepts and the settable field ids, **which differ per instance** —
never hardcode one you found in a payload.

- **`parent`** — an Epic or Story key. Without it the issue has no place in the
  hierarchy and Timeline stays empty. Shared context goes **on the Epic and is
  linked**, never copied into each child.
- **`labels`** — comma-separated, and this is how urgency is expressed.
  **`priority` cannot be set on a team-managed project at all**; every issue
  reads `Medium` because that is the only value it can have. Jira's own
  `createmeta` confirms it is not accepted on create.
- **`duedate`, `start_date`** — ISO `YYYY-MM-DD`.
- **No story points exist**, so capacity planning cannot work here. Not a gap
  to fill.

---

## 4. Lifecycle

```
TODO  →  IN PROGRESS  →  IN REVIEW  →  DONE
```

**Never skip IN REVIEW**, including for your own work.

```
jira_assign(key, "me")            # this one is mine
jira_assign(key, "Jakkawan")      # hand it over — name, email, or "none"
jira_start_task(key)              # → In Progress, and gives you the branch command
jira_submit_for_review(key, pr, files)
```

One ticket per phase, and **each phase must merge on its own** without breaking
the one before it. If three parts of a ticket all edit the same function, they
are one PR, not three — branches taken from `develop` in parallel would
conflict with each other.

### The backlog is not a status

`jira_move_to_backlog` / `jira_move_to_board` change **membership of the
current working set, and nothing else**. A ticket parked in the backlog is
still `IN PROGRESS` if that is what it was. Read backlog as a status and you
have recreated the two-surfaces problem.

---

## 5. Before anything is called Done

**A ticket marked IN REVIEW is not merged code.** DG-225 sat in review for
weeks while its branch was never merged and the trunk stayed vulnerable; every
surface said it was done.

Verify in this order, and verify by looking rather than by remembering:

1. The PR is **merged** — check `origin/develop`, not the PR page and not the
   merge commit message.
2. The suite is green **on the merged tree**, not on your branch.
3. The thing the ticket claims to fix is **absent from the merged code** — grep
   for it. A finding closed in one module is not closed in the codebase.

Then comment what was verified and how, and transition.

### Merge is not deploy

The installed tool env is a separate deployment. Merging does not update it,
and `drunken-doctor` reports the gap. Say so in the closing comment when it
applies — "fixed" and "deployed" are different facts.

And **deploy is not running**: a server process started before a reinstall
still holds the old code until it restarts.

### If it closed narrower than written

Say so in the comment, with the reason and what it depends on. A ticket quietly
closed at half its scope is worse than one left open.

---

## 6. When things change

- **Grew?** Split it. A second ticket with a parent beats one ticket nobody
  finishes.
- **Wrong after it closed?** New ticket referencing the old. Do not reopen —
  the closed one is the record of what was believed at the time.
- **Dropped by decision?** Comment who decided and when, then close. A ticket
  that just goes quiet looks like one that was forgotten.

---

## 7. What good looks like

```
[CI] Fail the commit when .gitignore excludes a source file

FINDING
.gitignore's `*token*` matched tests/test_jira_token_economy.py. `git add -A`
skipped it silently; the commit, pre-commit and the local suite all passed
because the file was still on disk. A PR shipped claiming 21 tests and
contained none.

SCOPE
Pre-commit hook: fail when any file under src/, tests/ or scripts/ is excluded
by .gitignore. Catches the class, not the two patterns known today.

ACCEPTANCE
Seen failing first: a decoy source file matching an ignore rule must trip the
hook before the fix exists.
```

88 words. Every line is a fact someone can act on or check.
