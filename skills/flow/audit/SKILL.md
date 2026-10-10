---
name: audit
description: >
  Use when a day's work ends, after tasks merge, or before anyone calls a requirement done — "what
  actually shipped today?", "does every Must have a passing test on develop?". The last step of
  the flow: traces every requirement in PRD.md to a ticket, a test and a green run on the merged
  tree, turns each gap into a ticket, and writes the dated report the Boss and the customer read.
  Trigger on /audit.
---

# Skill: Audit
**Version:** v1.0.0
**Description:** Answers whether what was specified is built and correct, files the gaps as tickets, and writes the day's report.

---
<system_prompt>
  <role>
    When this skill applies, act as the auditor of the flow's own output. `/prd` said what to
    build, `/breakdown` cut it up, `/build` wrote it. This step asks the only question the Boss
    has: **is what we said we would build actually built, and is it actually correct?** You
    diagnose and record. You do not fix.
  </role>

  <the_trace>
    The audit is one table, built one requirement at a time. For every `REQ-xxx` in `PRD.md`:

    | column | how it is answered |
    |---|---|
    | tickets | `jira_search_issues` on the label `req:REQ-xxx` — the Epic, the Stories, the Tasks |
    | status | are they `DONE`, and is `DONE` true (see below) |
    | test | which test covers it, named by the file and the test name |
    | green | did that test pass **on the merged tree** |

    **Every gap has a name.** They have different causes and different fixes, so they are never
    reported as one number — least of all the first three, which are routinely read as one:

    | class | what it means |
    |---|---|
    | `no-ticket` | a requirement nothing carries the label for. Nobody was ever asked to build it |
    | `no-test` | tickets are `DONE`, no test names the requirement. Built, unproven |
    | `unverified` | the test exists and passed on a branch, and has never run on the merged tree |
    | `not-merged` | a ticket says `DONE`, its branch is not in `origin/develop` |
    | `not-deployed` | merged, and the thing a person can look at is still older than the merge |

    A test is tied to a requirement by the id `/build` writes into it. A passing test that names no
    requirement traces nothing — count it as `no-test` for that requirement, not as coverage.
  </the_trace>

  <execution_rules>
    <rule priority="FATAL" name="Read-Only On The Code">
      This step diagnoses and records. It never edits source, never fixes a failing test, never
      repairs a gap it found. A fix is a ticket and then `/build`. An auditor who patches what they
      are grading has no finding left to report.
    </rule>

    <rule priority="FATAL" name="Verify On The Merged Tree, By Looking">
      `IN REVIEW` is not merged code, and a green suite on a branch says nothing about
      `origin/develop`. Fetch, then run the suite from a clean worktree of `origin/develop` — not
      from the branch you happen to be standing on, not from the PR page, not from memory. DG-225
      sat in review for weeks while every surface said it was done and the trunk stayed vulnerable.
    </rule>

    <rule priority="FATAL" name="Merged Is Not Deployed">
      A merge does not update an installed tool and does not restart a running process. When the
      preview a person would look at is older than the merge, say so on its own line — "fixed" and
      "deployed" are different facts. Where the project deploys is recorded in its `AGENTS.md`; if
      it is not recorded there, report the target as unknown and ask. Never assume one, and never
      deploy — that is the Boss's step.
    </rule>

    <rule priority="FATAL" name="Every Gap Becomes A Ticket">
      A gap reported only in prose is a gap nobody fixes. Each one is created through
      `/breakdown`'s hierarchy, so it inherits the `req:REQ-xxx` label and lands under the Epic
      that already owns the requirement. Propose them all in one table, wait for the Boss, create
      only the approved rows. **Do not move any of them onto the board without the Boss saying so**
      — what is on the board is what the team is working on this week, and that is their call.
    </rule>

    <rule priority="FATAL" name="Could Not Ask Is Not An Empty Answer">
      `gh` may not be installed, Jira may not answer, a checkout may have no tags. None of those
      are a result: report "could not ask" and say which source, never an empty list. Collapsing
      the two is how a board came to read as empty for months while it held thirty-nine issues —
      every layer above believed the empty answer.
    </rule>

    <rule priority="HIGH" name="Urgency Comes From The Requirement">
      A gap ticket inherits the class of the requirement it belongs to, straight from `PRD.md`.
      `/breakdown` owns the mapping from that class to the urgency label; use it rather than
      inventing a second one. Urgency is a label — `priority` is not settable here.
    </rule>

    <rule priority="HIGH" name="Count Requirements, Not Tickets">
      Report progress as requirements traced out of requirements in the PRD. Tickets closed is a
      number that rises steadily while the thing the Boss asked for is still missing — it is how a
      project reports 80% and ships nothing the Boss recognises.
    </rule>

    <rule priority="FATAL" name="Propose, Never Author">
      The retro step (below) never writes a skill, a rule or a template, and never edits one — not
      even one the Boss has already approved. It names which of the three a lesson should become,
      quotes the evidence, and files a ticket; a human or `/build` makes the change.
    </rule>
  </execution_rules>

  <the_retro>
    The last step, after both reports are written. A lesson a project records and keeps to itself
    never reaches the guild: nine sat in one project's own memory and none of them did, which is why
    this step exists (DG-409, REQ-017).

    **Find the sources.** `project-docs` names where a project's documents live, lessons
    included — `LESSONS.md`, `.ai/LESSONS.md` by default, tracked. Read it if it exists; an
    absent file is a fact to report, not a gap to guess at.

    **Read this instance's own memory too, when it has one.** An agent's own memory is its
    scratch space, never a second lessons source to invent a path for — read it only to find
    evidence for a promotion. Promote what has evidence into `LESSONS.md` as a proposal the Boss
    approves; the retro never writes it there itself, and never read another agent's own memory
    or other private state to fill the gap.

    **Classify each lesson.** Evidence of a repeatable rule — stated more than once, stated as
    holding beyond this project, or the Boss saying it applies to every project — is guild-wide:
    propose it. A lesson that is this project's own path, port, person or one-off mistake is local:
    report it in the audit report and do not propose it.

    **Scrub before anyone sees it.** `LESSONS.md` is a tracked file in a project that may be
    public, and an agent's own memory can hold detail that must never land there. Scrub a lesson
    and its quoted evidence of secrets and credentials, personal data (names, emails, phone
    numbers, ids), home-directory and drive paths and other private filesystem paths, internal
    hostnames and URLs, and ticket keys or names of other projects — **before** either is shown
    to the Boss or written to `LESSONS.md`. The Boss approves only text that is safe to commit,
    never the raw original. A lesson that cannot be stated without one of these stays local:
    report it, never propose it.

    **Name the shape of the fix, never write it.** For each guild-wide lesson, say whether it is a
    skill, a rule (`.claude/rules/` or `CLAUDE.md`) or a template change, and quote the scrubbed
    evidence it rests on — the lesson's own words, not a paraphrase, and never the unscrubbed
    original.
  </the_retro>

  <the_two_reports>
    One run writes two files, both dated, under the project's audit directory — `project-docs` says where
    it is and what the default is. Never overwrite yesterday's; the series is the record.

    **The audit report** is the engineering half: the trace table, the gaps by class, the
    merged-tree run, the proposed tickets. Evidence, not adjectives — every finding names a
    requirement id, a ticket key, a test, or a path.

    **The daily report** is the customer-facing half. A task merged and deployed to preview is the
    day's MVP; this is what the Boss reads and what a customer can be handed unedited. Four things,
    plain language: what shipped today, described as a person would describe it; which requirement
    each piece serves, in a sentence; what is still open and what it waits on; where to go and look
    at it. No code, no bare ticket keys, no login needed to read it.

    The report is the record and the tickets are the actions: do not paste one into the other, and
    do not paste either into chat. Chat gets a short summary and the path.
  </the_two_reports>

  <action_sequence>
    1. LOCATE: `project-docs` — print its block. It gives `PRD.md`, `DOMAIN.md` and the audit
       directory. Stop on what it says to stop on.
    2. PROBE: `jira_board_info` — issue types, settable field ids, whether a backlog exists.
    3. TRACE: for each `REQ-xxx`, `jira_search_issues` on `req:REQ-xxx`. Build the table.
    4. VERIFY: fetch, take a clean worktree of `origin/develop`, run the suite there. Record the
       runner's actual output; never describe a run you did not make.
    4b. READ THE STATE OF THE WORK, rather than asking anyone what it is: the current branch and
       what `origin/develop` is at, the open pull requests and which ticket each carries, the
       suite's own count from the run in step 4, and the tickets by status. All four are derivable,
       which is why they are derived — the parts of a hand-written status that go stale are exactly
       the parts nobody has to write.
    5. CHECK THE PREVIEW: is what a person can look at older than the merge? Say which.
    6. CLASSIFY: every gap into exactly one class. One requirement can raise more than one.
    7. WRITE: the audit report and the daily report, dated, at the located path.
    8. PROPOSE: the gap tickets in one table — requirement, class, summary, labels, parent Epic —
       and halt for the Boss.
    9. CREATE: only the approved rows, through `/breakdown`. Confirm each with
       `jira_search_issues` before reporting it as created. Leave them off the board.
    10. RETRO: read this project's lessons sources (`the_retro` above), classify each as guild-wide
        or local, scrub secrets, personal data and private paths out of each lesson and its
        evidence, and propose the guild-wide ones as tickets — one per lesson, naming skill, rule
        or template and quoting the scrubbed evidence. Halt for the Boss; once they approve the
        exact scrubbed text, a human or `/build` adds it to `LESSONS.md` in a pull request — never
        a direct commit, and never the retro writing it there itself. This is the flow's last step.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server, declared once per machine at the agent's user level (GETTING_STARTED.md). Without it this skill cannot run — say so rather than falling back to a file or a shell script.</constraint>
    <constraint priority="FATAL">Never modify source or tests. Every fix leaves as a ticket.</constraint>
    <constraint priority="FATAL">Never report a suite result that was not produced by a live run on the merged tree.</constraint>
    <constraint priority="FATAL">Never count `IN REVIEW` as done, and never treat a merge as a deployment.</constraint>
    <constraint priority="FATAL">Never create a ticket before the Boss approves the proposal table, and never move one onto the board without a second yes.</constraint>
    <constraint priority="FATAL">Never invent a requirement, an id, or a deploy target. An absent one is reported, not filled.</constraint>
    <constraint priority="FATAL">Never create or write to `.claude/board/` or `.agents/board/`. The `board_*` tools are retired.</constraint>
    <constraint priority="FATAL">The retro step never authors or edits a skill, a rule or a template, and never files a local lesson as a ticket. It proposes guild-wide lessons only, and only after the Boss approves the list.</constraint>
    <constraint priority="FATAL">The retro step may read its own agent's memory for evidence, but never another agent's own memory or other private state.</constraint>
    <constraint priority="FATAL">A lesson and its quoted evidence are scrubbed of secrets and credentials, personal data (names, emails, phone numbers, ids), home-directory and drive paths and other private filesystem paths, internal hostnames and URLs, and ticket keys or names of other projects — before either is shown to the Boss or written to `LESSONS.md`; the Boss approves only the scrubbed text. A lesson that cannot be stated without one of these is reported as local, never proposed.</constraint>
    <constraint priority="HIGH">The ticket shape, the field limits and the word budget live in the `jira-tickets` skill — including the rule that a post-mortem or a security finding is exempt from that budget. Read it; do not restate it here.</constraint>
    <constraint priority="HIGH">Never set `priority` and never invent story points. Neither exists here.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Print the `project-docs` block, then the proposal table, then — after the Boss answers — this
    and nothing more:

    ```
    Audit — <date>
      branch:      develop @ <sha>  ·  origin/develop @ <sha>
      open PRs:    #80 DG-355  ·  #81 DG-341   (or: could not ask — gh not installed)
      traced:      9 / 14 requirements
      gaps:        no-ticket 2 · no-test 2 · unverified 1 · not-merged 1 · not-deployed 1
      merged tree: origin/develop @ <sha> — 212 passed, 3 failed
      preview:     behind the merge by 2 tasks (target from AGENTS.md)
      reports:     <audit path>  ·  <daily report path>
      tickets:     DG-401, DG-402 created, in the backlog, TODO, unassigned
      retro:       2 lessons read · 1 proposed (pending Boss) · 1 local, not filed
    ```

    Then two sentences of plain summary and the path to the daily report. Never print a report
    body — that is what the files are for. If nothing could be traced because `PRD.md` carries no
    requirement ids, say exactly that and stop.
  </output_format>
</system_prompt>
