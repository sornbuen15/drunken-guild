---
name: git-workflow
description: >
  Use when planning a Git change, branch, commit, review request or release — "what does this repo
  require before I commit?", "how do I hand this change off?". Read repository policy and follow
  its actual branch and review rules. Trigger on /git-workflow.
---

# Skill: Git Workflow
**Version:** v2.3.0
**Description:** Applies the repository's documented branch, commit, review and release policy.

---
<system_prompt>
  <role>
    When this skill applies, inspect the repository's instructions and current Git state. Explain
    the workflow that repository actually uses. Do not import branch names or review assumptions
    from another project.
  </role>

  <branch_strategy>
    <rule priority="FATAL" name="Read Repository Policy">
      Read `AGENTS.md`, `CONTRIBUTING.md` and any repository Git workflow skill. If they conflict,
      report the conflict and follow the most specific current instruction available. Never infer
      an integration branch name or merge strategy without evidence.
    </rule>

    <rule priority="FATAL" name="Do Not Perform Unrequested Git Actions">
      Do not commit, push, create a review request, merge, tag or release unless the user or
      repository workflow authorizes that action. Explain the proposed target before
      taking an action that publishes or integrates changes.
    </rule>

    <rule priority="FATAL" name="Drunken Guild Repository Policy">
      When working in the Drunken Guild repository, base work on `develop`. A user-authorized
      review request may target `develop`. Never push to `main`, open a pull request targeting
      `main`, or merge into `main`. No release or exception can override this. Never merge into `main`. Agents never merge;
      a human reviews and decides whether to merge into `develop`.
    </rule>

    <rule priority="HIGH" name="Use A Working Branch When Required">
      Follow the repository's branch policy. When changes must be isolated, create a working branch
      before editing. Do not switch or rewrite a branch another process is using.
    </rule>

    <rule priority="FATAL" name="Branch Naming Convention">
      All branches MUST follow: `<type>/<TICKET-KEY->?<kebab-case-description>`

      Allowed types: feat/ | feature/ | fix/ | bugfix/ | refactor/ | docs/ | chore/

      **Include the ticket key when the project has a tracker.** `feature/DG-123-retire-board`
      is not decoration: tooling reads the key back off the branch name — `drunken-usage
      --by ticket` attributes a whole run to a ticket that way, and it has no other source.
      A branch without a key on a tracked project reports as untracked cost, silently.

      Omit the key only on a project with no tracker at all, where there is nothing to name.

      Examples:
        feature/DG-123-retire-local-board     tracked project
        fix/DG-260-doctor-verifies-project    tracked project
        fix/sync-aborts-on-frontmatter        untracked project
        docs/update-skill-index               untracked project

      Both `feat/` and `feature/` are accepted, and both `fix/` and `bugfix/`, because the
      projects sharing this skill already use different halves of each pair and renaming live
      branches to satisfy a style rule is not worth a broken reference.

      NEVER use: your-name/, or freeform text with no type prefix.

      `release/` is reserved: it is created only by the release flow below, never by hand for
      ordinary work.
    </rule>

    <rule priority="HIGH" name="Keep Change Scope Clear">
      Keep a branch or change set focused on one task. Record unrelated findings separately rather
      than silently expanding scope.
    </rule>
  </branch_strategy>

  <concurrent_agents>
    <rule priority="FATAL" name="One Working Tree Per Agent">
      Two agents should not share a mutable working tree. Use isolated worktrees or another
      project-supported isolation method when agents work concurrently.

      A project may use separate worktrees for concurrent tasks:

      ```
      git worktree add ../<repo>.<agent> <starting-branch>
      ```

      A harness that isolates each session itself also satisfies this guidance. Do not remove a
      worktree another person or process owns.

      Separate worktrees prevent concurrent sessions from modifying the same files.
    </rule>

  </concurrent_agents>

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

    <rule priority="HIGH" name="Agent Commit Attribution">
      An agent commit passes `--author`, never the operator's own git identity:
      `git commit --author="Claude Code <claude@drunken.local>" -m "..."` for Claude, and the
      same shape with its own name for any other agent (DG-293).

      The addresses are local-only and resolve to no real account — that is the point. `git log`
      then tells an agent's commit from the operator's on sight, the same way Assignee stays the
      accountable human while a ticket's `agent:<name>` label says who is typing.
    </rule>
  </commit_conventions>

  <pr_lifecycle>
    <rule priority="FATAL" name="Respect The Repository's Protected Branches">
      Follow the repository-specific protected-branch policy above. Do not assume that a release
      or integration target is authorized by a general Git workflow skill.
    </rule>

    <rule priority="FATAL" name="Merging Is A Human Action">
      Agents never merge. A human reviews changes and decides whether they meet the repository's
      integration policy.
    </rule>

    <rule priority="FATAL" name="No Local Merge, Ever">
      Never bypass repository review by merging directly into a protected branch. Follow its
      documented integration path.
    </rule>

    <rule priority="HIGH" name="PR Checklist">
      Before opening a PR, verify:
      - [ ] Branch name follows the convention above
      - [ ] All commits follow Conventional Commits
      - [ ] No unrelated file changes included
      - [ ] Skill files follow canonical SKILL.md structure (see AGENTS.md)
      - [ ] Agent files follow canonical agent `.md` structure (see AGENTS.md)
      - [ ] Sync scripts have NOT been run — installation is always a manual user step
    </rule>

    <rule priority="HIGH" name="PR Title and Description">
      PR title: `type(scope): description` (mirrors primary commit message)
      PR body must include: ## What (one paragraph), ## Why (one paragraph), ## Checklist (checked off).
    </rule>
  </pr_lifecycle>

  <merge_strategy>
    <rule priority="FATAL" name="One Strategy Per Target">
      The strategy is chosen by **what is being merged into**, not by preference or by how the
      branch happens to look. All of these are selected in the PR's merge button by a human.

      | into | strategy | why |
      |---|---|---|
      | target | policy |
      |---|---|
      | protected branch | use the repository's documented review and merge policy |
      | working branch | follow project guidance before rebasing or merging updates |

      Do not rewrite published history unless the project explicitly allows it and collaborators
      have coordinated.
    </rule>
  </merge_strategy>

  <release_flow>
    <rule priority="HIGH" name="Release Policy Comes From The Project">
      This skill does not define release targets, versioning or tag policy. Read the repository's
      release documentation and require explicit authorization before publishing.
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
    <constraint priority="FATAL">Do not commit to or publish a protected branch unless repository policy and user authorization explicitly allow it.</constraint>
    <constraint priority="FATAL">Agents do not merge changes.</constraint>
    <constraint priority="HIGH">One branch per task. One commit per logical unit.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Branch creation:  Branch created: `<type>/<name>` | Base: `<project integration branch>` at `<short-sha>`
    Commit guidance:  Proposed commit: `<type>(<scope>): <description>` | Files staged: <list>
    Review guidance:  Target: `<repository-defined review target>`
                      Then output the full PR body template, pre-filled.
  </output_format>
</system_prompt>
