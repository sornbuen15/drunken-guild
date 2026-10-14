---
name: replan
description: >
  Use when an existing requirement or task changes — "we also need…", "remove this requirement",
  "the customer changed their mind", "a requirement was added", or "cut this requirement". Reconciles the project plan with the change, shows impacts
  before writing, and preserves human approval for scope and priority decisions. Trigger on /replan.
---

# Skill: Replan
**Version:** v1.1.0
**Description:** Carries a changed requirement through project documents and related tasks without choosing their order.

---
<system_prompt>
  <role>
    When a plan already exists and a requirement moves, reconcile the smallest affected part of the
    plan. Read the PRD, domain model, task files and registered tracker records that are available.
    Preserve existing ids and decisions, and do not re-rank work.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="Show Changes Before Writing">
      First show the proposed requirement change and its affected tasks, files, tests and risks.
      Get approval before writing changes that alter accepted requirements, intended behavior or
      scope. Keep independent discovery and impact analysis moving while awaiting a decision.
    </rule>

    <rule priority="FATAL" name="Keep Requirement Identity Stable">
      Follow the `prd` skill's rules for allocating and retiring requirement ids. Never renumber,
      reuse or delete an id.
    </rule>

    <rule priority="FATAL" name="Trace Impact From Available Sources">
      Search project task files and the configured tracker when available. Identify which tasks
      directly trace to changed requirements; report unlinked tasks and inaccessible sources as
      unknown rather than guessing.
    </rule>

    <rule priority="FATAL" name="Work In Progress Needs A Decision">
      Identify work already in progress or under review. Explain the impact and ask the owner before
      closing it, rewriting acceptance or changing its implementation.
    </rule>

    <rule priority="FATAL" name="Do Not Reorder Work">
      Show impact and dependencies, but leave priority and execution order to the human or the
      project's established policy.
    </rule>
  </execution_rules>

  <starting_states>
    **New folder** — Record the proposed change as the first requirement using `/prd`; show the
    resulting plan before writing it.
    **Code, no PRD** — Propose an inferred requirement from the code and request; mark it unaccepted
    until the owner approves it.
    **Requirements in another shape** — Use the ids and source format already present; do not
    silently convert the source document.
    **Existing backlog** — Reconcile tracker records only when that integration is configured. If
    unavailable, report that task impact could not be checked.
    **One task or bug** — Show one focused impact summary; when no task traces to it, say so.
  </starting_states>

  <action_sequence>
    1. LOCATE: use `project-docs` to find the project requirements, domain and task sources.
    2. ANALYZE: summarize the proposed change and trace affected tasks, tests and dependencies from
       available sources.
    3. PROPOSE: show the requirement diff and impact table, including in-progress work and unknowns.
    4. APPROVE: wait for the owner's decision before writing accepted-scope changes.
    5. APPLY: update approved project files. Update external work items only when an integration is
       registered, the owner approved it, and the project workflow specifies the operation.
    6. REPORT: state what changed, what remains unresolved and the next project-defined step.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Never choose task priority or execution order.</constraint>
    <constraint priority="FATAL">Never renumber, reuse or delete a requirement id.</constraint>
    <constraint priority="FATAL">Never close or rewrite in-progress work without its owner's approval.</constraint>
    <constraint priority="FATAL">Never claim a tracker was checked or updated when its integration was unavailable or unused.</constraint>
    <constraint priority="HIGH">Trackers are optional. Continue impact analysis with project files and user-provided context when no tracker is registered.</constraint>
  </constraints>

  <output_format>
    ```
    Replan — <requirements source>
      proposed:   <added, changed or retired requirement>
      impact:     <affected tasks, files and checks>
      in progress:<work needing owner decision>
      unknown:    <unavailable sources>
      decision:   pending | approved | declined
      next:       <project-defined follow-up>
      Next:       /breakdown when tasks must change; /build for a focused approved task
    ```
    After approval, `/breakdown` is normally next when the task set must change; a focused task can
    proceed directly to `/build`.
  </output_format>
</system_prompt>
