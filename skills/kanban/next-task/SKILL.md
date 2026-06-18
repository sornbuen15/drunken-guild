---
name: next-task
description: >
  Picks the highest-priority task from todo/, claims it atomically, and enters Plan Mode before
  writing any code. Apply whenever the user wants to start working, asks what to do next, says
  "continue", or "what should I work on" — even without saying "next task". Trigger on /next.
---

# Skill: Next Task Picker & Initiator
**Version:** v3.1.0
**Description:** Picks the highest-priority task from todo/, claims it atomically, and enters Plan Mode for approval before writing any code. Enforces WIP=1 per agent.

---
<system_prompt>
  <role>
    When this skill applies, follow strict single-piece flow discipline: pull the highest-priority
    task from `todo/` into `in-progress/` and formulate an Execution Plan for approval before
    making any code changes.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="Strict Single-Piece Flow (WIP Limit = 1)">
      Before looking at todo/, call board_list_lane({ lane: "in-progress" }).
      If any task is returned, you MUST REFUSE to pick a new task. Inform the user that the
      current task must be completed and moved to done/ before proceeding.
      The WIP limit is enforced by the server — this check is a pre-flight confirmation.
    </rule>

    <rule priority="FATAL" name="Priority-Based Selection">
      Call board_list_lane({ lane: "todo" }) to get all available tasks.
      Select based on this strict hierarchy: CRITICAL > HIGH > MEDIUM > LOW.
      Among equal priorities, pick the lowest Task ID (oldest task first).
    </rule>

    <rule priority="FATAL" name="Claim Before Moving">
      Before moving a task to in-progress, you MUST call board_claim_task first.
      The server will reject board_move_task to in-progress if no valid claim exists.
    </rule>

    <rule priority="FATAL" name="Plan Mode First (No Code Generation)">
      Once a task is claimed and moved to in-progress/, enter PLAN MODE.
      You MUST NOT modify, create, or delete any application code.
      Use ONLY read-only commands (`Read`, `Grep`, `find`) to inspect the workspace.
    </rule>
  </execution_rules>

  <action_sequence>
    1. VERIFY STATE: board_list_lane({ lane: "in-progress" }).
       If any task is returned: STOP and report the active task to the user.
    2. SCAN TODO: board_list_lane({ lane: "todo" }) → get all tasks with priorities.
    3. SELECT: Pick exactly ONE task with the highest available priority
       (CRITICAL > HIGH > MEDIUM > LOW). Tie-break: lowest task ID.
    4. CLAIM: board_claim_task({ task_id, agent_slug }) → { ok, claimed_at }
       If ok: false, report the rejection reason and stop.
    5. MOVE: board_move_task({ task_id, target_lane: "in-progress", agent_slug })
       If ok: false (e.g. wip_limit_exceeded), release claim and stop.
    6. READ TASK: board_get_task({ task_id }) or board_agent_context({ task_id }) →
       read the full task to understand objective, acceptance criteria, and relevant files.
    7. INITIATE & PROPOSE: Read the necessary project files and formulate a step-by-step
       Execution Plan (target files, core logic, potential risks) before responding.
    8. APPROVAL GATE: Halt execution completely and ask the user:
       "Tech Lead, do you approve this plan, or would you like to make adjustments before I write the code?"
  </action_sequence>
</system_prompt>
