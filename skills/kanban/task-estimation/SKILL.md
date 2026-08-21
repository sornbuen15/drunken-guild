---
name: task-estimation
description: >
  Estimates complexity, AI execution cycles, and human review effort for the TODO tickets on the
  Jira board. Apply whenever the user asks how long something will take, wants to know the effort
  of upcoming work, or needs to decide what's safe to start — even if they just say "is this a
  big task?" or "how much work is left?". Trigger on /estimate.
---

# Skill: AI Task Estimation & Complexity Analysis
**Version:** v4.0.0
**Description:** Scans TODO tickets on the board to assess complexity, predict AI execution cycles, and estimate human review time.

---
<system_prompt>
  <role>
    When this skill applies, apply Technical Project Manager discipline: analyze the tickets in
    `TODO` on the current board and estimate the effort required for an AI agent to execute them.
  </role>

  <estimation_metrics>
    - **T-Shirt Size:** S (Simple config/typo), M (Standard feature/1-2 files), L (Complex logic/Multiple files/DB changes), XL (Architectural change/High risk of hallucination).
    - **Est. AI Turns:** How many prompt-response cycles the AI will likely need.
    - **Human Review Effort:** High/Medium/Low (How strictly the Tech Lead needs to review the output).
  </estimation_metrics>

  <where_estimates_live>
    **This Jira has no story points, and that is not a gap to fill.** Estimates produced here are
    a reading aid for the person deciding what to start next. They are reported in chat and
    nowhere else.

    Do NOT write an estimate into a ticket field, do NOT invent a custom field to hold one, and
    do NOT encode a size into a label. An estimate that lives on the ticket becomes a number
    people plan against, and nothing updates it when the work turns out different.

    If the user wants the reasoning preserved against a specific ticket, `jira_add_comment` is
    the honest place for it — a comment is dated and reads as an opinion, which is what it is.
  </where_estimates_live>

  <action_sequence>
    1. SCAN: `jira_search_issues({ jql: "status = 'To Do' AND ..." })` → keys, summaries, labels,
       assignees. Restrict to the current working set; backlog tickets are not being started.
    2. READ: For each ticket, read the ACCEPTANCE section and anything its SCOPE names as a
       prerequisite. `jira_search_issues` on a referenced key resolves what blocks what.
    3. ANALYZE: For each ticket, evaluate the required file modifications, system impact,
       and potential roadblocks (e.g., missing context, XL scope).
    4. REPORT: Output a clean Markdown table:
       | Key | Summary | Urgency label | T-Shirt | Est. AI Turns | Human Review | Risk/Blocker Note |
    5. RECOMMENDATION: If any ticket is rated XL, strongly recommend splitting it before
       execution — a second ticket with a parent beats one ticket nobody finishes.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server, declared in the project's `.mcp.json`. Without it this skill cannot run — say so rather than falling back to a file or a shell script.</constraint>
    <constraint priority="FATAL">Never read work state from the file system. `.claude/board/` and the `board_*` tools are retired.</constraint>
    <constraint priority="FATAL">Never write an estimate into a ticket field, a custom field, or a label. No story points exist here.</constraint>
    <constraint priority="FATAL">Read-only on Jira. This skill estimates; it never transitions, assigns, or creates.</constraint>
    <constraint priority="HIGH">Report the urgency **label**, not the `priority` field — the field is unsettable and reads `Medium` on every ticket.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Output a single Markdown table, one row per TODO ticket:
    | Key | Summary | Urgency label | T-Shirt | Est. AI Turns | Human Review | Risk/Blocker Note |
    Below the table, list any XL-rated ticket with an explicit recommendation to split it before execution.
    State plainly that these estimates are not stored on the tickets.
    All output in English.
  </output_format>
</system_prompt>
