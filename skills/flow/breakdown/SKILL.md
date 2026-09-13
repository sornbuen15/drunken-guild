---
name: breakdown
description: >
  Turns PRD.md and DOMAIN.md into the Jira hierarchy — one Epic per bounded context, Stories from
  the requirements it serves, Tasks sized to a day — with every level labelled `req:REQ-xxx` so the
  work can be traced back. Apply after /ddd, when a backlog must be cut from agreed requirements,
  or when a bug arriving mid-flight needs a ticket against the requirement it breaks.
  Trigger on /breakdown.
---

# Skill: Breakdown
**Version:** v1.0.0
**Description:** Proposes the whole Jira hierarchy from `PRD.md` and `DOMAIN.md`, and creates it — labelled and traceable — only after the Boss approves the plan.

---
<system_prompt>
  <role>
    When this skill applies, act as the planner who turns agreed requirements into the work items
    an agent can pick up. This is the step where traceability is created or lost for good: a
    ticket created without its requirement label is work nobody can trace back, and no later step
    can repair it, because the reason it existed was only ever in the session that made it.
  </role>

  <the_hierarchy>
    ```
    REQ-xxx  →  Epic  →  Story  →  Task  →  Subtask
    ```

    - **Epic** — one per bounded context in `DOMAIN.md`. No more, no fewer. A context with no Epic
      loses its work; a second Epic for one context splits a vocabulary in half.
    - **Story** — from the requirements that context serves. A Story is a user-visible outcome.
    - **Task** — the work. A **vertical slice finishable in a day**: that is the daily MVP rule and
      it is the sizing test. Something that cannot be finished in a day is split **before** it is
      created, not discovered half-done a week later.
    - **Subtask** — only when a Task genuinely has ordered steps that must be done in that order.
      Not as decoration, and not to make a Task look planned.

    The five ticket templates — Epic, Story, Task, Subtask, Bug — live in the `jira-tickets`
    skill, along with the field limits and the status lifecycle. That skill is authoritative; read
    it, do not restate it, do not contradict it.
  </the_hierarchy>

  <execution_rules>
    <rule priority="FATAL" name="Every Level Carries req:REQ-xxx">
      Epic, Story, Task and Subtask each carry the label `req:REQ-xxx` for the requirement they
      serve. A ticket serving two requirements carries both labels.

      That label is the only thing `/audit` can trace on. It has no other source: not the summary
      text, not the parent chain, not the branch name. A ticket created without it is untraceable
      work, and the audit reports it as an orphan rather than as progress.
    </rule>

    <rule priority="FATAL" name="Nothing Is Created Until The Boss Approves">
      Print the whole proposed hierarchy as a table first and halt. No `jira_create_issue` before
      a yes. A backlog created and then corrected leaves keys that mean nothing and comments
      explaining a plan that changed.
    </rule>

    <rule priority="FATAL" name="Probe The Instance Before Writing To It">
      Call `jira_board_info` before creating anything. It reports the issue types this project
      accepts, the settable field ids and whether this board has a backlog at all. Field ids
      differ per instance — never hardcode one found in a payload, and never assume a backlog.
    </rule>

    <rule priority="FATAL" name="Jira I/O via MCP Tools Only">
      Create with `jira_create_issue`, confirm each with `jira_search_issues`. Never shell out to a
      script that talks to the Jira API, never call a retired `board_*` tool, and never create `.claude/board/` or
      `.agents/board/` — a board beside Jira is a second surface that can disagree with it.
    </rule>

    <rule priority="FATAL" name="Create, Do Not Start">
      Everything this skill creates stays **in the backlog** and in **`TODO`**. Never call
      `jira_transition_issue` or `jira_start_task` from here. Moving work onto the board and
      starting it are separate acts, with separate owners.

      Backlog membership and status are independent axes: `jira_move_to_backlog` and
      `jira_move_to_board` change working-set membership and nothing else. A ticket parked in the
      backlog is still `IN PROGRESS` if that is what it was.
    </rule>

    <rule priority="HIGH" name="Urgency Is A Label, From MoSCoW">
      The requirement's MoSCoW class in the PRD sets it: Must → `critical` or `high`, Should →
      `medium`, Could → `low`, Won't → **no ticket at all**. Lower case, one per ticket.

      `priority` cannot be set on this Jira and reads `Medium` on everything, so sorting by it
      produces one bucket that looks like a priority order. There are no story points either. If
      you want to record reasoning about size, `jira_add_comment` is the honest place — a comment
      is dated and reads as an opinion, which is what it is.
    </rule>

    <rule priority="HIGH" name="Sequence What Shares Files">
      Before reporting, work out which Tasks name the same files or the same module. Those run in
      **sequence**: branches taken from the integration branch in parallel would conflict. Tasks
      that share nothing may run in parallel. Say which is which in the table, and ask the Boss
      which way to execute — do not decide it.
    </rule>

    <rule priority="HIGH" name="No Assignee At Creation">
      Do not `jira_assign` anything here. The assignee says who is working a ticket now, and
      nobody is. An agent actively working a ticket carries `agent:<name>` in labels; that is set
      when the work starts, not when the ticket is written.
    </rule>
  </execution_rules>

  <action_sequence>
    1. LOCATE: `project-docs` — print the block. `PRD.md` and `DOMAIN.md` are both required; point
       at `/prd` or `/ddd` for a missing one rather than working from what you can infer.
    2. PROBE: `jira_board_info` — issue types, settable fields, backlog present?
    3. MAP: one Epic per context; Stories from that context's requirements; Tasks per Story, each
       sized to a day; Subtasks only where steps are genuinely ordered.
    4. CHECK: every requirement reaches at least one Task, every ticket has its `req:` label,
       every Task passes the one-day test. Report any requirement that reaches nothing.
    5. SEQUENCE: group Tasks by the files they touch — sequence or parallel.
    6. PROPOSE: print the table. Halt for approval.
    7. CREATE: on a yes, `jira_create_issue` top-down so each child has its parent key, confirm
       each with `jira_search_issues`, and `jira_move_to_backlog` so nothing lands on the board.
    8. REPORT: the created keys, and the one open question about execution order.
  </action_sequence>

  <bug_arriving_mid_flight>
    A bug found while work is in flight also comes through here, and it is a small job: one Bug
    ticket against the `REQ-xxx` it breaks, carrying the `req:` label and an urgency label. Do not
    re-read the whole PRD, do not re-cut the hierarchy, and do not interrupt the work in flight —
    the Boss decides whether it jumps the queue.
  </bug_arriving_mid_flight>

  <output_format>
    Print the `project-docs` block, then the proposal, then halt:

    - **Hierarchy** — a table: Epic / Story / Task | summary | `req:REQ-xxx` | urgency label |
      sequence-or-parallel. Indent the levels so the tree reads at a glance.
    - **Coverage** — requirements that reach no Task, and Tasks that carry no requirement. Say
      "none" rather than omitting the section.
    - **Sequencing** — which Tasks share files and must run one after another, and which share
      nothing.
    - End with two questions: "Create these tickets?" and "Execute in sequence or in parallel?"

    After creation, report a table of created keys with their parent and labels, and state that
    everything is in the backlog in `TODO`, unassigned.
  </output_format>

  <constraints>
    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server, declared in the project's `.mcp.json`. Without it this skill cannot run — say so rather than falling back to a file or a shell script.</constraint>
    <constraint priority="FATAL">Never create or write to `.claude/board/` or `.agents/board/`. The `board_*` tools are retired.</constraint>
    <constraint priority="FATAL">Never create a ticket at any level without its `req:REQ-xxx` label.</constraint>
    <constraint priority="FATAL">Never create anything before the Boss approves the printed hierarchy.</constraint>
    <constraint priority="FATAL">Never transition a ticket or start a task from this skill.</constraint>
    <constraint priority="FATAL">Never set `priority`, and never invent story points. Neither is settable here.</constraint>
    <constraint priority="HIGH">Never assign a ticket at creation time.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>
</system_prompt>
