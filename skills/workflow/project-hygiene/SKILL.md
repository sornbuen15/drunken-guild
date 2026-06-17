---
name: project-hygiene
description: >
  Repository maintenance standard — Git workflow, squash merging, README, and Architecture
  Decision Records. Apply whenever the user is committing changes, managing branches, updating
  documentation, or wants to maintain a clean and well-documented repository. Trigger on /git.
---

# Skill: Project Hygiene & Documentation
**Version:** v1.2.0
**Description:** Repository maintenance standard — Git workflow, squash merging, README, and Architecture Decision Records.

---
<system_prompt>
  <role>
    When this skill applies, apply Open Source Maintainer discipline: treat undocumented code
    as broken code, and a messy Git history as a liability.
  </role>

  <core_instructions>
    <instruction category="Strict Branching Strategy">
      - **Step 1: Sync Base.** Always ensure your base branch is up-to-date: `git checkout develop && git pull origin develop`
      - **Step 2: Create Task Branch.** NEVER work directly on `develop` or `main`. Create a dedicated branch for the task: `git checkout -b <type>/<task_name>`
      - Valid `<type>` prefixes: `feature/` (new implementations), `fix/` (bug fixes), `refactor/` (code structure changes), `chore/` (configs, tooling).
    </instruction>

    <instruction category="Conventional Commits">
      All Git commit messages MUST follow the Conventional Commits specification (e.g., `feat:`, `fix:`, `chore:`, `refactor:`). The body must explain the "Why", not just the "What". Make atomic commits frequently as you progress through a task.
    </instruction>

    <instruction category="Squash Merging (Clean History)">
      To maintain a strictly clean and linear git history, all completed task branches MUST be squash-merged back into the develop branch.
      Execution flow for completion:
      1. `git checkout develop`
      2. `git merge --squash <feature_branch_name>`
      3. `git commit -m "<type>(<scope>): <Task Summary Title>"`
      4. `git branch -D <feature_branch_name>`
    </instruction>

    <instruction category="Working Tree Discipline">
      If you need to switch contexts, pull new changes, or pause a task, ALWAYS use `git stash` to protect uncommitted changes.
    </instruction>

    <instruction category="Reproducible Onboarding (README)">
      Project documentation (README.md) must always contain explicit, step-by-step instructions on how a new developer can run the project locally from a fresh clone, including required environment variables.
    </instruction>

    <instruction category="Architecture Decision Records (ADR)">
      When a major architectural change or library addition is made, propose creating an ADR (Architecture Decision Record) to document the context, alternatives considered, and the final decision.
    </instruction>
  </core_instructions>

  <constraints>
    <fatal_constraint>
      NO DIRECT COMMITS TO MAIN OR DEVELOP: All code modifications MUST happen on a separate task branch before being squash-merged to develop.
    </fatal_constraint>
    <fatal_constraint>
      NO GENERIC COMMITS: NEVER generate commit messages like "Fixed bug", "Update files", or "WIP".
    </fatal_constraint>
    <fatal_constraint>
      NO CREDENTIALS IN REPO: ALWAYS ensure `.gitignore` is updated before committing new environment files, keystores, or IDE configurations.
    </fatal_constraint>
  </constraints>

  <output_format>
    Before generating Git commands, Commit messages, or Markdown documentation, briefly review the files being committed or documented to ensure no secrets are leaked and that you are on the correct branch.
  </output_format>
</system_prompt>
