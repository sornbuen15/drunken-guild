---
name: "jira-tickets"
description: "How to write and run a ticket in this project: the hierarchy a ticket sits in, the five shapes — Epic, Story, Task, Subtask, Bug — the labels that make work traceable, the fields this Jira can actually set, the status lifecycle, and what must be verified before anything is called Done."
---

# Skill: Tickets

**Version:** 2.0.0
**Applies to:** every agent working this project, whatever its name.

Jira is the only coordination surface. The **assignee** says whose the work is,
the **status** says where it is, the **labels** say what requirement it serves
and which agent is typing. Nothing else tracks any of it.

---

## 1. Should this be a ticket at all?

**Yes** — work someone else may pick up, a defect, a security finding, a
decision that must survive the session.

**No** — anything the repository already records. Code structure, what a commit
did, why a function looks like that. Git and the code say those better, and a
ticket restating them is a second surface that can disagree.

**Also no** — a step inside work you are doing right now. That is a commit.

---

## 2. The hierarchy

```
REQ-xxx       lives in PRD.md. Never a Jira issue.
  Epic          one bounded context from DOMAIN.md
    Story         one behaviour a customer would notice
      Task          one vertical slice, finishable in a day
        Subtask       one ordered step of that task

Bug           sits beside the hierarchy, parented where the defect lives
```

**A requirement is not an issue.** `REQ-xxx` stays in `PRD.md` and reaches Jira
as a label. Two places to edit one requirement is the drift this repo cures.

**Story or Task?** A Story is something the customer would notice and could
describe. A Task is how it gets built. If you cannot say who benefits, it is a
Task. If it names a file, a table or an endpoint, it is a Task.

**A Task is a vertical slice finishable in a day.** That is the sizing rule, not
advice — it is what makes a daily MVP possible. Something that fails it is
**split before it is created**, not after someone picks it up. Do not split by
layer: "the API" and "the UI" each ship nothing. Split by behaviour, so every
piece is demonstrable on its own.

**Subtasks only when the steps are genuinely ordered** — the backfill that runs
before the index, the rename that lands before its callers move. Steps that
could be done in any order are a checklist inside the Task. A subtask per bullet
is decoration and makes the board unreadable.

**Which step cuts which kind.** `/breakdown` creates Epics, Stories, Tasks,
Subtasks and any Bug found on the way; `/audit` creates gap tickets against an
Epic that already exists. Read those skills for when to cut a ticket — this file
says only what one looks like.

---

## 3. Labels

Four label families, and Jira has nowhere else to put any of them. **Labels do
not inherit** — a child issue gets its own, every time.

- **`req:REQ-xxx` — the requirement this work serves.** Every level carries it:
  Epic, Story, Task, Subtask, Bug. It is the only thing `/audit` can trace on,
  so a ticket without one is untraceable work — it may well be done, and
  nothing can say which requirement it satisfied, so the audit reports that
  requirement unmet. A ticket serving two requirements carries **both** labels.
  Ids come from `PRD.md`: one that is not in the file is a typo, not a new
  requirement.
- **urgency** — `critical`, `high`, `medium`, `low`, lower case. This is where
  the PRD's MoSCoW class lands, because `priority` cannot be set (§5).
- **`agent:<name>`** — the agent doing the typing: `agent:claude`, or another
  agent's own name. **Assignee is the accountable human.** Assignee can only
  hold a real email, so it cannot say which agent is on a ticket; do not
  repurpose it for one (DG-293).
- **`type:<kind>`** — `epic`, `story`, `task`, `subtask`, `bug`. It mirrors the
  issue type so a search can filter on it without depending on what this
  instance calls its types.

---

## 4. The shapes

Five shapes, one per kind. Headings and nothing else. **A ticket is read, not
experienced** — it is scanned by someone deciding what to pick up. Write
declaratively.

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
| every ticket — epic, story, task, subtask, bug, chore | **≤ 120 words.** If it needs more, it is two tickets or it needs a parent |
| post-mortem, security finding | as long as it takes — these are the record |

The project's own older tickets run about 49 words. Five written in one session
averaged 600. The rule exists because of the second number.

### Summary line

`[Area] imperative statement of the change`

`[CI] Fail the commit when .gitignore excludes a source file` — not
`[CI] Investigation into gitignore behaviour`.

### Epic — `GOAL` · `REQS` · `OUT OF SCOPE`

```
[Ordering] Customers order ahead and collect in store

GOAL
A customer picks a store, builds an order, pays, and collects without queueing.
Ordering owns the basket and the order lifecycle; Payment owns the charge.

REQS
REQ-004, REQ-005, REQ-009.

OUT OF SCOPE
Delivery. Table service. Loyalty points — REQ-011, its own Epic.
```

58 words. The goal in the domain's own words, the ids it serves, and the line
people skip — OUT OF SCOPE is what stops two Epics building the same thing.

### Story — `AS A` / `I WANT` / `SO THAT` · `ACCEPTANCE` · `REQ`

```
[Ordering] Customer re-orders their last order in one tap

AS A returning customer
I WANT to repeat my last order from the home screen
SO THAT I do not rebuild a five-item basket every morning

ACCEPTANCE
Given a customer with at least one completed order,
when they open the home screen,
then the last order appears as a single "Order again" card.

Given that card is tapped,
when an item on it is no longer sold at that store,
then the basket is built from the rest and the dropped items are named.

REQ
REQ-005.
```

94 words. One Given/When/Then per behaviour, and the second one is what stops
the Task being built for the happy path only.

### Task — `SCOPE` · `ACCEPTANCE` · `Parent`

```
[Ordering] Serve the "Order again" card from the orders API

SCOPE
Add `GET /v1/customers/{id}/last-order`, returning the most recent completed
order with per-item availability at the requested store. Reuse the existing
order repository; no new table.

ACCEPTANCE
Unit: an order whose items are all stocked returns every item available.
Unit: an item withdrawn at that store returns `available: false`, the rest
unchanged.
Contract: a customer with no completed order returns 204, not an empty 200.

Parent: DG-501.
```

82 words. SCOPE is a short plan, not a diff; ACCEPTANCE is the tests. If the
plan cannot be written before the code exists, the Task is not ready to start.

### Subtask — one step · `DONE WHEN`

```
[Ordering] Backfill completed_at on historical orders

Backfill `orders.completed_at` from the last status-transition row, in batches
of 1000, before the index is added.

DONE WHEN
No row in `orders` with status `completed` has a null `completed_at`, checked
on a restored copy of production.
```

45 words. One step, one observable check that ends it. If it needs a SCOPE it
is a Task.

### Bug — `FINDING` · `SCOPE` · `ACCEPTANCE`

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

88 words, and the ACCEPTANCE line is the one that cannot be paraphrased away:
**the test is seen failing first, and the ticket says so.** A test written after
the fix proves only that it compiles. Every other line is a fact someone can act
on or check.

---

## 5. Fields: what this Jira can and cannot do

Read `jira_board_info` rather than assuming. It reports the issue types this
project accepts and the settable field ids, **which differ per instance** —
never hardcode one you found in a payload. It also says whether the board has a
backlog, probed rather than inferred: type does not predict it, a kanban board
may have none while a team-managed 'simple' board has one, and `backlog: null`
means the question could not be answered — which is not the same as no.

- **`parent`** — Story parents to Epic, Task to Story, Subtask to Task. Without
  it the issue has no place in the hierarchy and Timeline stays empty. Shared
  context goes **on the Epic and is linked**, never copied into each child.
- **`labels`** — comma-separated, and this is how urgency is expressed, along
  with everything in §3. **`priority` cannot be set on a team-managed project
  at all**; every issue reads `Medium` because that is the only value it can
  have. Jira's own `createmeta` confirms it is not accepted on create.
- **`duedate`, `start_date`** — ISO `YYYY-MM-DD`.
- **No story points exist**, so capacity planning cannot work here. Not a gap
  to fill. A Task sized to a day is the estimate.

---

## 6. Lifecycle

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

## 7. Before anything is called Done

**A ticket marked IN REVIEW is not merged code.** DG-225 sat in review for
weeks while its branch was never merged and the trunk stayed vulnerable; every
surface said it was done.

Verify in this order, and verify by looking rather than by remembering:

1. The PR is **merged** — check `origin/develop`, not the PR page and not the
   merge commit message.
2. The suite is green **on the merged tree**, not on your branch.
3. The thing the ticket claims to fix is **absent from the merged code** — grep
   for it. A finding closed in one module is not closed in the codebase.
4. The ticket carries its `req:REQ-xxx` label. Closed without one, the work is
   done and `/audit` still reports the requirement as unmet.

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

## 8. When things change

- **Grew?** Split it. A second ticket with a parent beats one ticket nobody
  finishes. A Task that no longer fits in a day is a Story with Tasks under it.
- **Wrong after it closed?** New ticket referencing the old. Do not reopen —
  the closed one is the record of what was believed at the time.
- **Dropped by decision?** Comment who decided and when, then close. A ticket
  that just goes quiet looks like one that was forgotten.
- **Requirement dropped?** The tickets keep their `req:` label. `PRD.md` strikes
  the requirement through rather than deleting it, so the label still resolves
  to something a reader can find.
