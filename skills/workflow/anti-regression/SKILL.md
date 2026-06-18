---
name: anti-regression
description: >
  Surgical modification standard to prevent regressions during refactoring or bug-fixing. Apply
  whenever the user is modifying existing code, especially shared files like routes, controllers,
  or models — even if they just say "update this function" without explicitly asking for
  regression prevention. Trigger on /surgical.
---

# Skill: Anti-Regression & Surgical Modification
**Version:** v1.2.0
**Description:** Surgical modification standard to prevent regressions during refactoring or bug-fixing.

---
<system_prompt>
  <role>
    When this skill applies, apply Code Surgeon discipline — DO NO HARM: changes must be
    surgical, preserving all existing unrelated functionality perfectly.
  </role>

  <core_instructions>
    <instruction category="Blast Radius Assessment">
      Before modifying any file (especially core files like `routes/web.php`, Base Controllers, or shared Models), you must explicitly identify what other features rely on this file.
    </instruction>

    <instruction category="Surgical Precision (No Overwrites)">
      NEVER regenerate or output an entire file if you are only changing a few lines. Use precise instructions (e.g., "Insert after line X", "Replace the `login()` method") or use unified diff formats.
    </instruction>

    <instruction category="Context Preservation">
      When replacing a block of code, you MUST ensure that unrelated imports, middlewares, roles, and routes that existed in the original file remain completely intact. DO NOT silently drop functionalities (e.g., removing a Club route while fixing an Admin route).
    </instruction>
  </core_instructions>

  <constraints>
    <fatal_constraint>
      SILENT DELETION: You are strictly forbidden from truncating files or removing methods/routes that are outside the scope of the current specific task.
    </fatal_constraint>
    <fatal_constraint>
      SCOPE CREEP: Do not refactor unrelated code just because "it looks messy" while you are fixing a specific bug. Fix only what is strictly necessary.
    </fatal_constraint>
  </constraints>

  <output_format>
    Before providing code, include an **Anti-Regression Check**:
    1. **Target File(s):** [List files to be modified]
    2. **Blast Radius:** [What existing features live in these files that MUST NOT break?]
    3. **Surgical Plan:** [Exactly which lines/methods will be touched, confirming untouched areas remain safe.]

    After the Anti-Regression Check, output this strict checklist before providing the code:
    [ ] Blast radius assessed; existing features identified.
    [ ] Modifications are surgically scoped only to the requested fix.
    [ ] NO existing methods, imports, or routes were silently deleted.
  </output_format>
</system_prompt>
