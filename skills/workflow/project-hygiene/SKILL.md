---
name: project-hygiene
description: >
  Repository maintenance standard — commit hygiene, README, and Architecture Decision
  Records. Defers every branch and merge rule to `git-workflow`. Apply whenever the user is committing changes, managing branches, updating
  documentation, or wants to maintain a clean and well-documented repository. Trigger on /git.
---

# Skill: Project Hygiene & Documentation
**Version:** v1.2.0
**Description:** Repository maintenance standard — commit hygiene, README, and Architecture Decision Records. Branch and merge rules are `git-workflow`'s, not restated here.

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

    <instruction category="Merging (Clean History)">
      A completed task branch reaches `develop` as a **single squashed commit** — one branch is
      one concern, so `develop` gets one revertable entry for it.

      **That squash happens on the remote, in the PR, and a human presses the button.** Do not
      do it locally. The sequence this skill used to prescribe —
      `git checkout develop` → `git merge --squash <branch>` → `git commit` — puts a commit on
      a protected branch that no PR ever described, bypassing review and CI, and afterwards it
      is indistinguishable from a change that went through the process. It also contradicted
      this skill's own FATAL constraint against direct commits to `develop`, four lines below.

      Nor does the branch get deleted afterwards by an agent: **an agent does not delete.**
      Deleting the merged branch is the human's click, in the same PR.

      Completion flow:
      1. Push the branch.
      2. Open a PR into `develop`.
      3. Say it is ready, give the link, stop.

      **The full rules — which strategy belongs to which target, branch naming, who may merge —
      live in `git-workflow` (`/git-workflow`) and are not restated here.** One rule, one home.
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
      NO DIRECT COMMITS TO MAIN OR DEVELOP: All modifications happen on a separate task branch, which reaches `develop` by a PR that a human squash-merges. Never by a local merge and push.
    </fatal_constraint>
    <fatal_constraint>
      NEVER MERGE A PR: An agent opens pull requests; a human merges them. No exception for your own PR, a one-line change, or a green CI.
    </fatal_constraint>
    <fatal_constraint>
      NEVER DELETE A BRANCH: `git branch -D` is not yours to run. An agent does not delete — the merged-branch cleanup is the human's click in the PR.
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
