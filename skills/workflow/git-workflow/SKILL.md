---
name: git-workflow
description: >
  Use when creating a branch, writing a commit, opening a PR, merging or releasing — "what should
  I name this branch?", "how should I commit this?", "which merge strategy goes into main?".
  Branch naming, commit conventions, the PR lifecycle, which merge strategy belongs to which
  target, and release hygiene. Trigger on /git-workflow.
---

# Skill: Git Workflow & Branching Strategy
**Version:** v2.3.0
**Description:** Best-practice Git discipline — branch naming, commit conventions, PR lifecycle, which merge strategy belongs to which target, and release hygiene. An agent opens pull requests; a human merges them.

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

    <rule priority="HIGH" name="One Branch Per Task">
      Each branch addresses exactly one task or concern. If a second concern is discovered mid-work, note it and create a separate branch after the current one is merged.
    </rule>
  </branch_strategy>

  <concurrent_agents>
    <rule priority="FATAL" name="One Working Tree Per Agent">
      Two agents never share a checked-out working tree. Each works from its own `git worktree`
      of the repository, on its own branch — so a checkout switched or edited by one can never be
      pulled out from under another mid-session, whether they are handing off in turn or, by
      mistake, started at the same time. One task, one owner, one branch, one worktree, one PR.

      The first agent may work from the checkout its harness starts it in; any agent running beside
      it works from a sibling worktree, added once and left in place between sessions:

      ```
      git worktree add ../<repo>.<agent> <starting-branch>
      ```

      A harness that isolates each session itself satisfies the rule without that step — Claude
      Code's worktree sessions, and Remote Control's `--spawn worktree`, both do. No agent runs
      `git worktree remove` on a path it does not own, and none switches the branch checked out in
      another's worktree.

      DG-288: decided over two cheaper-looking alternatives, and why each was rejected —
      - **One agent read-only, the other writes.** Does not describe how agents are used: each one
        writes code, tests it, and opens its own PRs.
      - **Strict alternating turns.** Needs a turn marker every agent reads, which is a second
        coordination surface that can disagree with the first — the exact failure the retired
        local board was (DG-250).

      A worktree needs neither: two sessions can start at the same moment and still never touch
      the same file on disk, because neither ever sees the other's branch.
    </rule>

    <rule priority="HIGH" name="Unchanged Either Way">
      Opening a PR and waiting for a human to merge it is identical for every agent, worktree or
      not — see `<pr_lifecycle>` below. A worktree only decides who owns the filesystem while work
      is in progress; it changes nothing about review, CI, or merge.
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
    <rule priority="FATAL" name="Only develop Reaches main">
      Every working branch — feat, feature, fix, bugfix, refactor, docs, chore — targets
      `develop`.

      **`main` accepts a PR from `develop` and from nothing else.** No working branch may reach
      `main`, by PR or by any other route. That is the whole rule; opening a PR against `main`
      is allowed and is exactly how a release happens, it just has to come from `develop`.
    </rule>

    <rule priority="FATAL" name="Merging Is A Human Action">
      An agent **opens** pull requests — into `develop`, and into `main` for a release. An agent
      **never merges one**, and never asks to be allowed to.

      There is no exception for a PR the agent authored, a one-line change, a green CI, or an
      approval that arrived over Discord. A 👍 authorises the work in the PR; it does not press
      the button.

      When a PR is ready, say so, give the link, and stop.
    </rule>

    <rule priority="FATAL" name="No Local Merge, Ever">
      NEVER run `git merge` locally against `develop` or `main` and push the result. Not with
      `--squash`, not with `--no-ff`, not fast-forward.

      A local merge produces a commit on a protected branch that no PR ever described. It
      bypasses review, CI, and the record of why the change happened — and it looks identical
      afterwards to a change that went through the process. That is what makes it dangerous
      rather than merely irregular.

      The only place a merge happens is the remote, through a PR that a human merges.
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

  <merge_strategy>
    <rule priority="FATAL" name="One Strategy Per Target">
      The strategy is chosen by **what is being merged into**, not by preference or by how the
      branch happens to look. All of these are selected in the PR's merge button by a human.

      | into | strategy | why |
      |---|---|---|
      | `develop` ← working branch | **Squash** | one branch is one concern, so it becomes one commit. `develop` stays readable and each entry is revertable on its own. |
      | `main` ← `develop` | **Merge commit** (`--no-ff`) | a release is a set of changes, not one. The merge commit is the release boundary, and squashing it would erase which commits shipped together. |
      | your own branch ← `develop` | **Rebase**, locally, before pushing | keeps the branch a clean sequence on top of current `develop`. |
      | anything | **Fast-forward** — never | a fast-forward leaves no trace that a PR existed. The merge record IS the audit trail. |

      **Rebase only what you have not pushed.** Once a branch is on the remote and a PR is open,
      rebasing rewrites commits other people and CI are already referring to. Merge `develop`
      into your branch instead, or accept the conflict resolution at merge time.
    </rule>
  </merge_strategy>

  <release_flow>
    <rule priority="HIGH" name="develop → main Release">
      When `develop` is stable: open PR titled `chore(release): vX.Y.Z`, targeting `main` from
      `develop`. A human merges it, **with a merge commit** per the table above — no squash, no
      rebase. Tag only after that merge lands: `git tag vX.Y.Z`.

      Tagging before the merge tags a commit that is not on `main`, which is worse than not
      tagging at all because it looks right.

      SemVer: MAJOR = breaking interface change | MINOR = new skill/agent/script | PATCH = fix or docs

      **Retiring a skill, an agent, or a slash command is a breaking interface change.** Someone
      is invoking it.
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
    <constraint priority="FATAL">Never merge a pull request. An agent opens PRs; a human merges them. This holds for a PR you authored, a one-line change, a green CI, and an approval that arrived over Discord.</constraint>
    <constraint priority="FATAL">Never run `git merge` locally against `main` or `develop` and push the result — squash, no-ff or fast-forward alike. Merges happen on the remote, through a PR.</constraint>
    <constraint priority="FATAL">Never open a PR into `main` from anything except `develop`.</constraint>
    <constraint priority="FATAL">Always branch first — file changes come second.</constraint>
    <constraint priority="FATAL">Two agents never share a checked-out working tree. Each works from its own `git worktree`, on its own branch.</constraint>
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
