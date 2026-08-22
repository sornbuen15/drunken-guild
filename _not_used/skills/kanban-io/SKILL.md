---
name: kanban-io
description: >
  The single authoritative interface for all Kanban board reads and writes via MCP tools.
  Apply whenever any skill or agent needs to read, create, move, or claim board tasks — this
  is the required gatekeeper for all board operations. Direct file access to .claude/board/
  is never permitted; route everything through this skill. Trigger on /kanban-io.
---

# Skill: Kanban Board I/O
**Version:** v3.2.0
**Description:** The single authoritative interface for all Kanban board reads and writes via MCP tools. All other skills delegate board access here — never touch `.claude/board/` directly.

---
<system_prompt>
  <role>
    When this skill applies, follow the Kanban Board Controller protocol — the only interface
    permitted to read from or write to `.claude/board/`. Every other skill that needs board
    state routes through here. Never use shell file commands on the board; always invoke MCP
    tools so that I/O is typed, atomic, and safe across concurrent agent sessions.
  </role>

  <implementation_note>
    Board accessed via the kanban-board MCP server (JSON-RPC 2.0 over stdio).
    Server: `scripts/mcp/kanban-server.js` (Node.js 18+)
    Registration: `templates/mcp-settings.json` | Setup: `scripts/mcp/README.md`
    Fallback (non-MCP): `scripts/kanban/kanban_read.sh` / `kanban_write.sh`
  </implementation_note>

  <mcp_tools>
    All board operations MUST use these MCP tools. Do NOT use shell commands on `.claude/board/`.

    READ:
      board_next_id → { id: "TASK-NNN", nnn: N }
      board_get_task { task_id } → { ok, id, lane, file, frontmatter, content }
      board_list_lane { lane } → [{ id, title, priority, assigned_to, depends_on, blocks, claimed_at, lane }]
      board_summary → { counts: { backlog, todo, in-progress, done }, lanes: { … } }  (also auto-releases stale claims)

    WRITE:
      board_create_task { lane, slug, content } → { ok, id, path }
      board_claim_task { task_id, agent_slug } → { ok, id, claimed_at } or { ok: false, reason }
        MUST succeed before board_move_task to in-progress.
      board_release_claim { task_id, agent_slug } → { ok }
      board_move_task { task_id, target_lane, agent_slug } → { ok, id, from, to } or { ok: false, reason }
        Moving to in-progress requires a prior claim and enforces WIP=1 per agent.
      board_done_task { task_id, agent_slug } → { ok, id }

    ORCHESTRATION:
      board_orchestrate { task_ids: string[] }
        → { total_tasks, waves: [{ wave, mode, tasks, depends_on_wave, rationale }] }
        Topologically sorted wave plan. Same-wave tasks run in parallel; different waves sequential.
      board_agent_context { task_id }
        → { task_id, title, assigned_to, priority, objective, acceptance_criteria, technical_notes, relevant_files, depends_on, blocks }
        Compact ~100-150 token handoff envelope — pass directly to sub-agents.

    CONTEXT RETRIEVAL:
      query_project_context { files: string[], keywords: string[] }
        → { results: [{ file, section_title, content, line_start, truncated }], total_matches }
        Use INSTEAD of reading whole files. Extracts only matching sections. Short filenames resolved to .claude/ automatically.
  </mcp_tools>

  <board_structure>
    .claude/board/backlog/      — planned, not started
    .claude/board/todo/         — approved, ready to start (CRITICAL bugs go here directly)
    .claude/board/in-progress/  — active (WIP=1 per agent, server-enforced)
    .claude/board/done/         — completed and verified
    Naming: TASK-<NNN>_<kebab-case-slug>.md  (NNN zero-padded: TASK-001 … TASK-042)
    IDs always assigned by the server — never hardcoded.
  </board_structure>

  <task_template>
    Every task file MUST use this canonical format exactly:

    ---
    id: TASK-<NNN>
    type: feature | bug | security | tech-debt | infrastructure
    phase: <phase-number or "?">
    priority: CRITICAL | HIGH | MEDIUM | LOW
    title: <concise verb-noun title>
    assigned_to: "@<single-agent-slug>"
    depends_on: []
    blocks: []
    source: "<path or reference to the artifact that originated this task>"
    ---

    ## Objective
    One sentence: what problem is being solved or what capability is being added.

    ## Context
    - Reference to the spec, audit finding, post-mortem, or decision that motivated this task.
    - Key constraints or trade-offs that shaped the scope.

    ## Root Cause  ← BUGS AND SECURITY FINDINGS ONLY — omit for features and tech-debt
    `path/to/file.ext:line` — specific diagnosis.

    ## Acceptance Criteria
    - [ ] **`path/to/affected/file.ext`** — what must be true after the fix or feature
    - [ ] Tests added or updated
    - [ ] Full test suite green

    ## Technical Notes  ← OPTIONAL
    Architectural constraints, gotchas, or implementation guidance.

    Note: `claimed_at` and `claimed_by` are written by the server — do not include on creation.
  </task_template>

  <claim_lifecycle>
    UNCLAIMED (todo/) → board_claim_task → CLAIMED (todo/, claimed_at written)
                     → board_move_task("in-progress") → ACTIVE
                     → board_done_task → DONE
    Stale claims auto-released by board_summary. PE may release any claim via board_release_claim.
  </claim_lifecycle>

  <execution_rules>
    <rule priority="FATAL" name="MCP Tools Only">
      NEVER use ls, mv, cp, mkdir, cat, echo>, or any shell file command on .claude/board/.
    </rule>
    <rule priority="FATAL" name="Claim Before In-Progress">
      board_claim_task MUST succeed before calling board_move_task to in-progress.
    </rule>
    <rule priority="HIGH" name="Verify Lane Before Moving">
      If unsure of a task's lane, call board_get_task first.
    </rule>
    <rule priority="HIGH" name="Use board_orchestrate for Multi-Task Scheduling">
      Call board_orchestrate([task_ids]) before claiming or moving any group of tasks.
      Do not reason about depends_on by hand.
    </rule>
  </execution_rules>

  <constraints>
    <constraint priority="FATAL">All board I/O goes through MCP tools — never direct shell commands.</constraint>
    <constraint priority="FATAL">assigned_to must be exactly one agent slug. Never a list, never blank.</constraint>
    <constraint priority="FATAL">board_claim_task must succeed before board_move_task to in-progress.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Task creation: Created: TASK-<NNN> in `.claude/board/<lane>/` | Title: … | Assigned to: @…
    Task claim:    Claimed: TASK-<NNN> by @<agent-slug> at <ISO timestamp>
    Task movement: Moved: TASK-<NNN> → `<target-lane>/`
    Listing:       Output the structured summary from board_list_lane or board_summary.
  </output_format>
</system_prompt>
