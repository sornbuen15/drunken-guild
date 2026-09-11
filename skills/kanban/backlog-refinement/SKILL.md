---
name: backlog-refinement
description: >
  Moves backlog tickets onto the board by urgency tier, always selecting critical tickets first.
  Apply whenever the user wants to plan a sprint, choose what to work on next, prioritize the
  backlog, or populate the work queue — even if they just say "what should we tackle next?"
  or "let's plan". Trigger on /refine.
---

# Skill: Backlog Refinement & Sprint Planning
**Version:** v4.1.0
**Description:** Moves backlog tickets onto the board by urgency tier, always selecting critical tickets first.

---
<system_prompt>
  <role>
    When this skill applies, apply Agile prioritization discipline: bring tickets from the backlog
    into the current working set based strictly on urgency tier, never by individual ticket
    selection.
  </role>

  <what_refinement_actually_changes>
    Read this before the action sequence. It is the one thing this skill is easy to get wrong.

    **`jira_move_to_board` changes membership of the current working set, and nothing else.**
    It does not transition anything. A ticket that was `TODO` in the backlog is `TODO` on the
    board. A ticket that was `IN PROGRESS` and got parked is still `IN PROGRESS` when it comes
    back.

    So refinement never touches status. It answers one question — *is this in the working set* —
    and that is the whole job. The moment this skill starts transitioning tickets because they
    "moved to todo", backlog has become a second status and the board and the status field can
    disagree. That is the failure this entire migration exists to close.

    Probe with `jira_board_info` first: **not every board has a backlog.** It reports whether
    this one does, and that is probed rather than inferred from the board's type, because the two
    do not track each other. On a board with no backlog, say so and stop — there is nothing to
    refine.
  </what_refinement_actually_changes>

  <execution_rules>
    <rule priority="FATAL" name="Critical Auto-Promotion">
      When scanning the backlog, if ANY ticket carries the `critical` label, you MUST flag it and
      propose moving all critical tickets onto the board immediately.
    </rule>

    <rule priority="FATAL" name="No Individual Ticket Selection">
      You are STRICTLY FORBIDDEN from asking the user to pick individual tickets or keys.
      You must only offer choices by urgency tier (`critical`, `high`, `medium`, `low`).
    </rule>

    <rule priority="FATAL" name="Tier Comes From Labels">
      Urgency is read from **labels**. Do NOT read or write the `priority` field — it cannot be
      set on a team-managed project and reads `Medium` on every ticket, so sorting by it produces
      one undifferentiated bucket that looks like a priority order.
    </rule>

    <rule priority="FATAL" name="Jira I/O via MCP Tools Only">
      NEVER use ls, mv, cp, mkdir, cat, echo, or any shell file command to move work, and never
      read or write a local board. ALL operations use `drunken-jira-mcp`.
    </rule>

    <rule priority="HIGH" name="Sequence What Shares Files">
      Before reporting, check which tickets brought onto the board name the same files or module
      in their SCOPE. Those run in **sequence**: branches taken from the integration branch in
      parallel would conflict with each other. Tickets that share nothing may run in parallel.
      Say which is which in the report, and ask the Boss which way to execute — do not decide it.
      (This rule used to live only in the Jira server's `sprint_planning` prompt, DG-339.)
    </rule>
  </execution_rules>

  <action_sequence>
    1. PROBE: `jira_board_info` → does this board have a backlog? If not, stop and say so.
    2. GLOBAL CONTEXT: `jira_search_issues` for `IN PROGRESS` and `IN REVIEW` → understand what
       is already in flight. Work in review still occupies a person.
    3. QUEUE ANALYSIS: `jira_search_issues` for the backlog and for `TODO` on the board.
    4. RE-PRIORITIZATION: Evaluate whether any backlog ticket has become more urgent than what is
       already sitting on the board unstarted.
    5. ALIGNMENT: For each ticket to bring in:
         `jira_move_to_board({ issue_key })`
       Keep the board's `TODO` column to the most immediate next steps
       (`critical` > `high` > `medium` > `low`), respecting anything a ticket's SCOPE names as a
       prerequisite. **Do not transition anything.** Status is not this skill's business.
    6. REPORT: Output the sorted queue — what is in flight, what is on the board unstarted, what
       remains in the backlog.
    7. PROMOTION — only in a project that has `scripts/promote_permissions.py` (drunken-guild
       does; most projects do not, and a missing one is not an error): run it to surface locally
       learned permissions as a reviewable diff. If any are promoted, explicitly ask the Boss to
       review the `settings.json` diff before committing.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server, declared in the project's `.mcp.json`. Without it this skill cannot run — say so rather than falling back to a file or a shell script.</constraint>
    <constraint priority="FATAL">Never create or write to `.claude/board/` or `.agents/board/`. The `board_*` tools are retired.</constraint>
    <constraint priority="FATAL">Never call `jira_transition_issue` from this skill. Refinement changes working-set membership, never status.</constraint>
    <constraint priority="FATAL">Never offer individual ticket selection — only urgency tiers.</constraint>
    <constraint priority="FATAL">Never read or write the `priority` field. Urgency is a label.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Output the re-prioritized queue as three grouped sections:
    - **In flight:** `IN PROGRESS` and `IN REVIEW` tickets, with key, summary, and assignee.
    - **Brought onto the board this pass:** tickets moved in, grouped by urgency label
      (`critical` > `high` > `medium` > `low`), each with key, summary, and any prerequisite note.
      State their status unchanged, so nobody reads the move as a transition.
    - **Sequence or parallel:** which of those share files and must run one after another, and
      which share nothing. End with the question: "Execute in sequence or in parallel?"
    - **Backlog (remaining):** counts per urgency tier.
    Close with a one-line rationale for the decision. All output in English.
  </output_format>
</system_prompt>
