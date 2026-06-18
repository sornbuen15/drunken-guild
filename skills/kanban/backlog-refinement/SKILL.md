---
name: backlog-refinement
description: >
  Promotes backlog tasks to todo/ by priority tier, always selecting CRITICAL tasks first.
  Apply whenever the user wants to plan a sprint, choose what to work on next, prioritize the
  backlog, or populate the work queue — even if they just say "what should we tackle next?"
  or "let's plan". Trigger on /refine.
---

# Skill: Backlog Refinement & Sprint Planning
**Version:** v3.1.0
**Description:** Promotes backlog tasks to todo/ by priority tier, always selecting CRITICAL tasks first.

---
<system_prompt>
  <role>
    When this skill applies, apply Agile prioritization discipline: promote tasks from backlog/
    to todo/ based strictly on Priority Levels, never by individual task selection.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="Critical Auto-Promotion">
      When scanning the backlog, if ANY task has priority CRITICAL, you MUST automatically
      flag it and propose moving all CRITICAL tasks to todo/ immediately.
    </rule>

    <rule priority="FATAL" name="No Individual Task Selection">
      You are STRICTLY FORBIDDEN from asking the user to pick individual task files or IDs.
      You must only offer choices by Priority Levels (CRITICAL, HIGH, MEDIUM, LOW).
    </rule>

    <rule priority="FATAL" name="Board I/O via MCP Tools Only">
      NEVER use ls, mv, cp, mkdir, cat, echo, or any shell file command on .claude/board/.
      ALL board operations MUST use the MCP board_* tools.
    </rule>
  </execution_rules>

  <action_sequence>
    1. GLOBAL CONTEXT: board_list_lane({ lane: "in-progress" }) → understand what is currently active.
    2. QUEUE ANALYSIS: board_summary() → get full board state (backlog, todo, in-progress counts).
    3. RE-PRIORITIZATION: Evaluate if any backlog task has become more critical than tasks in todo/.
    4. ALIGNMENT: For each task to promote, call:
         board_move_task({ task_id, target_lane: "todo", agent_slug: "principal-engineer" })
       Ensure todo/ contains ONLY the most immediate next steps (CRITICAL > HIGH > MEDIUM > LOW),
       respecting depends_on relationships with in-progress tasks.
    5. REPORT: Output the newly sorted queue: what is running, what is queued in todo/, what is in backlog/.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Never write to the board directly — always use the MCP board_* tools.</constraint>
    <constraint priority="FATAL">Never offer individual task selection — only priority tiers.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>
</system_prompt>
