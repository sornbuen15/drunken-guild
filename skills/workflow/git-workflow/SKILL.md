---
name: git-workflow
description: >
  Best-practice Git discipline — branch naming, commit conventions, PR lifecycle, merge rules,
  and release hygiene. Apply whenever the user is creating a branch, writing a commit, opening
  a PR, or asking about Git workflow — even if they just say "how should I commit this?".
  Trigger on /git-workflow.
---

# Skill: Git Workflow & Branching Strategy
**Version:** v1.1.0
**Description:** Best-practice Git discipline — branch naming, commit conventions, PR lifecycle, merge rules, and release hygiene.

---
<system_prompt>
  <role>
    When this skill applies, enforce Git discipline: every code change must flow through the
    correct branch lifecycle. No direct commits to `main` or `develop`. The branch must be
    created before any file is touched.
  </role>

  <branch_strategy>
    <rule priority="FATAL" name="Branch Before You Touch">
      NEVER modify files on `main` or `develop` directly.
      The FIRST action for any task is: create the correct feature branch from `develop`.
      If uncommitted changes already exist on `develop`, branch immediately — the working tree changes will follow.
    </rule>

    <rule priority="FATAL" name="Branch Naming Convention">
      All branches MUST follow: `<type>/<kebab-case-description>`

      Allowed types: feat/ | fix/ | refactor/ | docs/ | chore/
      Examples: feat/kanban-io-skill | fix/agentic-kanban-single-assignee | docs/update-skill-index

      NEVER use: hotfix/, release/, your-name/, or freeform text.
    </rule>

    <rule priority="HIGH" name="One Branch Per Task">
      Each branch addresses exactly one task or concern. If a second concern is discovered mid-work, note it and create a separate branch after the current one is merged.
    </rule>
  </branch_strategy>

  <commit_conventions>
    <rule priority="FATAL" name="Conventional Commits">
      Every commit MUST follow: `<type>(<scope>): <short description>`

      Types: feat | fix | refactor | docs | chore | test
      Scope: skill name, agent name, or script affected (kebab-case)
      Description: imperative mood, lowercase, no trailing period, ≤72 characters

      Examples:
        feat(kanban-io): add single kanban read/write interface skill
        fix(agentic-kanban): enforce single assignee constraint
        chore(scripts): add kanban_read and kanban_write shell scripts

      NEVER use: "WIP", "misc", "updates", "changes", or unprefixed free text.
    </rule>

    <rule priority="HIGH" name="Atomic Commits">
      Each commit represents one logical change that can stand alone.
      Multiple logical changes = multiple commits, one per logical unit.
    </rule>

    <rule priority="HIGH" name="No Secrets in Commits">
      Never commit API keys, tokens, passwords, or credentials.
      If a secret is accidentally staged, remove it before committing — do NOT use --no-verify.
    </rule>
  </commit_conventions>

  <pr_lifecycle>
    <rule priority="FATAL" name="PR Targets develop Only">
      All feature/fix/refactor/docs branches merge into `develop`.
      NEVER open a PR directly to `main`. Only `develop` merges into `main` via a release PR.
    </rule>

    <rule priority="HIGH" name="PR Checklist">
      Before opening a PR, verify:
      - [ ] Branch name follows the convention above
      - [ ] All commits follow Conventional Commits
      - [ ] No unrelated file changes included
      - [ ] Skill files follow canonical SKILL.md structure (see CLAUDE.md)
      - [ ] Agent files follow canonical agent `.md` structure (see CLAUDE.md)
      - [ ] Sync scripts have NOT been run — installation is always a manual user step
    </rule>

    <rule priority="HIGH" name="PR Title and Description">
      PR title: `type(scope): description` (mirrors primary commit message)
      PR body must include: ## What (one paragraph), ## Why (one paragraph), ## Checklist (checked off).
    </rule>
  </pr_lifecycle>

  <release_flow>
    <rule priority="HIGH" name="develop → main Release">
      When `develop` is stable: open PR titled `chore(release): vX.Y.Z` → merge with merge commit (no squash, no rebase) → tag: `git tag vX.Y.Z`
      SemVer: MAJOR = breaking interface change | MINOR = new skill/agent/script | PATCH = fix or docs
    </rule>
  </release_flow>

  <execution_protocol>
    For any new task:
    1. BRANCH CHECK: Is the current branch a valid feature/fix/etc. branch? If not, create one now.
    2. SCOPE CHECK: Are planned changes limited to one concern? If not, split the work.
    3. COMMIT GUIDE: After changes, propose the commit message in Conventional Commits format before committing.
    4. PR GUIDE: When work is complete, walk through the PR checklist and draft the PR description.
  </execution_protocol>

  <constraints>
    <constraint priority="FATAL">Never commit directly to `main` or `develop`.</constraint>
    <constraint priority="FATAL">Always branch first — file changes come second.</constraint>
    <constraint priority="HIGH">One branch per task. One commit per logical unit.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Branch creation:  Branch created: `<type>/<name>` | Base: `develop` at `<short-sha>`
    Commit guidance:  Proposed commit: `<type>(<scope>): <description>` | Files staged: <list>
    PR guidance:      PR title: `<type>(<scope>): <description>` | Target: `develop`
                      Then output the full PR body template, pre-filled.
  </output_format>
</system_prompt>
