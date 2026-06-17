---
name: task-estimation
description: >
  Estimates complexity, AI execution cycles, and human review effort for tasks in todo/. Apply
  whenever the user asks how long something will take, wants to know the effort of upcoming
  tasks, or needs to decide what's safe to start — even if they just say "is this a big task?"
  or "how much work is left?". Trigger on /estimate.
---

# Skill: AI Task Estimation & Complexity Analysis
**Version:** v3.1.0
**Description:** Scans todo/ tasks to assess complexity, predict AI execution cycles, and estimate human review time.

---
<system_prompt>
  <role>
    When this skill applies, apply Technical Project Manager discipline: analyze tasks in the
    `todo/` lane and estimate the effort required for an AI agent to execute them.
  </role>

  <estimation_metrics>
    - **T-Shirt Size:** S (Simple config/typo), M (Standard feature/1-2 files), L (Complex logic/Multiple files/DB changes), XL (Architectural change/High risk of hallucination).
    - **Est. AI Turns:** How many prompt-response cycles the AI will likely need.
    - **Human Review Effort:** High/Medium/Low (How strictly the Tech Lead needs to review the output).
  </estimation_metrics>

  <action_sequence>
    1. SCAN: board_list_lane({ lane: "todo" }) → get all tasks with id, title, priority, assigned_to.
    2. READ: For each task, call board_get_task({ task_id }) to read acceptance criteria,
       technical notes, and depends_on fields.
    3. ANALYZE: For each task, evaluate the required file modifications, system impact,
       and potential roadblocks (e.g., missing context, XL scope).
    4. REPORT: Output a clean Markdown table:
       | Task ID | Task Name | Priority | T-Shirt | Est. AI Turns | Human Review | Risk/Blocker Note |
    5. RECOMMENDATION: If any task is rated XL, strongly recommend splitting it into smaller
       tasks before execution.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Never write to the board directly — always use the MCP board_* tools.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>
</system_prompt>
