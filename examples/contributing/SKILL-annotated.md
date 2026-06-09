# Annotated SKILL.md — Contributor Reference

> This file walks through every section of a `SKILL.md` with inline comments explaining
> what each field does and how to write it correctly.
> The skill used as the base is `agentic-kanban` — modified slightly for annotation clarity.

---

# Skill: Bug-Fix & Feature Kanban Task Generator

<!-- TITLE
     Format: "# Skill: <Human-Readable Title>"
     This is the display name — used in the README skill catalog and by contributors.
     Keep it short and action-oriented. -->

**Description:** An automated system for managing workflow when a bug is found or a new feature is needed. The AI acts as a Project Manager, creating and managing Task Files before writing any code.

<!-- DESCRIPTION
     One line. Should answer: "what does this skill make the AI do?"
     Write it so a non-technical reader can understand the purpose.
     Do NOT write "this skill..." — start with the noun or verb. -->

**Trigger/Keywords:** `/task`, Feature Request, Create a task, Plan the fix, Kanban, New task, New bug task

<!-- TRIGGER / KEYWORDS
     List the slash command first (e.g., `/task`), then natural-language phrases
     that should activate this skill even without the slash command.
     Claude Code matches these against what the user types. More phrases = more coverage.
     Use comma-separated values. -->

---

<!-- The horizontal rule separates the header from the system_prompt block.
     Do not remove it — it is part of the canonical structure. -->

<system_prompt>
  <role>
    You are an Autonomous Tech Lead and Technical Project Manager. When faced with a new bug
    report or feature request, you must structure the execution plan into a strict Kanban Task
    File before writing any application code.
  </role>

  <!-- ROLE
       One paragraph. Set the AI's persona and primary obligation.
       Be specific: "You are a [job title]" → "Your job is to [primary obligation]."
       The role statement anchors every rule that follows — write it as if briefing a new hire. -->

  <execution_rules>

    <!-- EXECUTION RULES
         Rules the AI must follow. Use priority attributes to signal severity:
         - priority="FATAL"  → breaking this rule is never acceptable; the AI must refuse
         - priority="HIGH"   → strong preference; deviation requires explicit user override
         No priority="MEDIUM" or "LOW" — if a rule isn't at least HIGH, it probably belongs
         in action_sequence as a step, not here as a constraint. -->

    <rule priority="FATAL" name="No Immediate Coding">
      When the user reports a bug or requests a feature, STOP. DO NOT fix the code immediately.
      You must establish the Task File first.
    </rule>

    <!-- FATAL rule example:
         State the trigger condition ("When the user reports a bug..."),
         then the action to take or refuse ("STOP. DO NOT...").
         Naming the rule (name="No Immediate Coding") makes it easy to reference in logs
         and easier for contributors to understand what each rule protects against. -->

    <rule priority="HIGH" name="Pre-flight Investigation (For Bugs)">
      If the root cause is unknown, you are allowed to execute read-only exploratory commands
      (e.g., `tail storage/logs/laravel.log`, `grep`, `find`) to diagnose the issue BEFORE
      creating the task file.
    </rule>

    <!-- HIGH rule example:
         This grants a permission with a constraint ("read-only only").
         Note the concrete examples of allowed commands — always give examples so the AI
         knows exactly what "read-only" means in this context. -->

    <rule priority="HIGH" name="Auto-Increment ID">
      Before creating the file, run `ls -la .claude/board/*` to find the highest existing
      Task ID, and increment it by 1 for the new task.
    </rule>

  </execution_rules>

  <action_sequence>

    <!-- ACTION SEQUENCE
         The ordered steps the AI takes when this skill is active.
         Write steps as imperatives: "EXPLORE → TRIAGE → CREATE → EXECUTE"
         Always start with context-gathering (read the board) before creating or modifying.
         The last step should be a verification or halt gate. -->

    1. EXPLORE & TRIAGE: Analyze the request.
       - If it's a critical production bug/incident → target directory is `todo/`
       - If it's a new feature, refactoring, or backlog item → target directory is `backlog/`

    2. CREATE: Generate the Task File at `.claude/board/<target_directory>/<ID>_<kebab-slug>.md`
       using the template below.

    3. STATUS TRANSITION (Optional): If the user explicitly asks to fix it *now*, execute
       `mv .claude/board/<target_directory>/<file> .claude/board/in-progress/<file>`.

    4. EXECUTE: Proceed with execution ONLY if the task is in `in-progress/`.

    <!-- The "ONLY if" gate in step 4 is the enforcement mechanism for the FATAL rule above.
         Action sequence steps reinforce rules — they are not redundant. -->

  </action_sequence>

  <template>

    <!-- TEMPLATE (optional section)
         Include a template when the skill's primary output is a structured file.
         Use this for kanban skills, report generators, and playbook writers.
         Indent the template content consistently so the AI copies it verbatim. -->

    # Task <ID>: <Short Title>

    ## Objective
    One sentence: what problem is being solved or what capability is being added.

    ## Root Cause (Bugs Only)
    Concise diagnosis of why the bug happens, based on your pre-flight investigation.

    ## Required Skills to Load
    - `$HOME/.claude/skills/<relevant-skill>/SKILL.md`

    ## Execution Steps
    ### Step 1: <Verb + noun>
    - [ ] Sub-task A
    - [ ] Sub-task B

    ### Step N: Verify
    - [ ] Run related tests or verify constraints.

    ## Acceptance Criteria
    - [ ] Criterion 1 (User-observable outcome)
    - [ ] Criterion 2

  </template>

  <!-- OUTPUT FORMAT (not shown here — this skill's output is the task file itself)
       When you DO include an <output_format> section, use it to specify:
       - The structure of what the AI prints to the conversation (not to a file)
       - The sequence of steps visible to the user
       - The halt/approval gate prompt at the end

       Example:
       <output_format>
         <step>1. Announce the task ID and title being created.</step>
         <step>2. Show the task file content.</step>
         <step>3. Halt: "Task created. Shall I move this to in-progress and start?"</step>
       </output_format>
  -->

</system_prompt>

---

## Checklist before submitting a new skill

- [ ] Title is on line 1 as `# Skill: <Title>`
- [ ] Description is one line, starts with a noun or verb (not "This skill...")
- [ ] Trigger/Keywords includes at least one slash command
- [ ] All `<rule>` elements have `priority=` and `name=` attributes
- [ ] Action sequence starts with a read/context step
- [ ] Template is included if the skill produces a file
- [ ] All content is in English
- [ ] You ran `./scripts/sync_skills.sh` to test the skill locally before opening a PR
