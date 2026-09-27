# <Your Project Name> — Project Instructions

> **This is a template.** Copy it to your project root as `CLAUDE.md`, then replace every
> `<angle-bracket>` placeholder and delete the sections that do not apply. It is authored in
> `drunken-guild`'s `templates/CLAUDE.md`; a project's own copy is its own to change.
>
> It carries the **coordination and delivery rules** a project needs in order to work with the
> skills and agents this toolkit installs. It deliberately does not carry the skill-authoring
> rules — those live in the toolkit repo's own `CLAUDE.md` and apply only there.

---

## What this project is

<One paragraph. What is built here, who uses it, what it must not become.>

**Stack:** <languages, frameworks, database, hosting>
**Entry points:** <the two or three files a newcomer should read first>

---

<system_prompt>

  <capability_layers>
    Four layers reach this project, from three different places. Knowing which is which is what
    stops a skill being installed into a project that cannot run it.

    1. **Skills** — installed to `~/.claude/skills/` by the toolkit's `install_skills.sh`.
       Most need no MCP server at all.
    2. **Agents** — installed to `~/.claude/agents/` by `install_agents.sh`.
    3. **MCP servers** — NOT installed by either script. They are declared in **this project's
       own `.mcp.json`** and ship with the toolkit as a command (`drunken-jira-mcp`), put on PATH
       by `uv tool install`. Generate the config with
       `install_mcp.sh` rather than writing it by hand.
    4. **Project instructions** — this file.

    A skill that calls an MCP tool names the server it requires in its own `<constraints>` block.
    If a skill refuses to run, read that block before assuming the skill is broken.
  </capability_layers>

  <coordination_surface>
    <directive priority="FATAL" name="Jira Is The Only Coordination Surface">
      **Jira project:** `<KEY>` · **Board:** `<board name or id>`

      The **assignee** says whose work a ticket is; the **status** says where it is. Nothing else
      tracks either — not a file, not a checklist in a README, not a message thread.

      `TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW**, including for
      your own work.

      A ticket marked IN REVIEW is not merged code. Verify against the target branch before
      believing any claim that something is fixed.
    </directive>

    <directive priority="FATAL" name="There Is No Local Board">
      Do NOT create `.claude/board/` or `.agents/board/`. The `board_*` tools are retired and no
      installed skill calls them. If you find one that does, it is unconverted — report it
      rather than working around it.

      Why: a local board sitting next to Jira is a second surface that can disagree with the
      first. What is genuinely lost is claim expiry — the old board released a claim after
      1800s and **a Jira assignee never expires**. If an agent stops mid-ticket, the ticket
      stays assigned until a human reassigns it. Ten seconds of work, against a class of silent
      disagreement that costs weeks.
    </directive>

    <directive priority="FATAL" name="Point At The Ticket Rules, Do Not Restate Them">
      **How to write and run a ticket is the `jira-tickets` skill**, installed alongside the
      rest of this toolkit.

      The FINDING / SCOPE / ACCEPTANCE shape, the length budget, the fields this Jira can
      actually set, and what must be verified before anything is Done all live there.
      Read it before opening or closing a ticket, and **link to it rather than copying it**.
      It is the same file every agent is pointed at, so the rules cannot drift apart per agent.
    </directive>

    <mcp_tools>
      Coordination goes through `drunken-jira-mcp`, never a shell script:

        jira_create_issue      jira_search_issues     jira_start_task
        jira_transition_issue  jira_submit_for_review jira_assign
        jira_add_comment       jira_board_info        jira_move_to_backlog
        jira_move_to_board     jira_edit_labels       jira_edit_issue

      The server also offers prompts (`init_project`, `refinement`, `sprint_planning`,
      `review_retro`, `jira_daily_standup`). Each only names the skill that owns that process.

      **The backlog is not a second status.** `jira_move_to_backlog` and `jira_move_to_board`
      change nothing about status — a ticket parked in the backlog is still `IN PROGRESS` if
      that is what it was. Backlog membership answers "is this in the current working set", and
      nothing else. Read it as a status and the two-surfaces problem is back.

      **Probe, do not assume.** `jira_board_info` reports the issue types this project accepts
      and the settable field ids, and they differ per instance. Three limits are known to hold
      on a team-managed project and to change what a skill may write:

      - `priority` cannot be set. Every issue reads `Medium`. Urgency goes on as a **label**.
      - There are **no story points**. Nothing may write an estimate onto a ticket.
      - Not every board has a backlog. Probe before relying on one.
    </mcp_tools>

    <approvals>
      When something needs the Boss to approve it, the protocol is the `ask-boss` skill.
      The short version: if the Boss
      is reading the conversation, just ask them there. Otherwise submit async, park the task,
      take the next unblocked one, and collect **when you finish a task or start a session —
      never mid-task.**
    </approvals>

    <session_handoff>
      Read `SESSION_CHECKPOINT.md` at the start of a session if it exists, and rewrite it before
      ending one. It is untracked, and it is a handoff note, not a second board: Jira stays the
      record, and anything in the checkpoint that disagrees with Jira is wrong.
    </session_handoff>
  </coordination_surface>

  <project_documents>
    This project's own documents — brief, requirements, spec, architecture, policy, ADRs — are
    found and read as the **`project-docs` skill** says. Point at it; do not restate it.

    For a tool that cannot load skills, the minimum: look in `.ai/`, then the project root, then
    `.claude/`, then `docs/`. Read every document that exists. A brief is the only one required.
    Never write a missing architecture, policy or requirements document and treat it as decided.

    **Documents live in:** `<.ai/ — or wherever this project keeps them>`
  </project_documents>

  <core_directives>
    <directive priority="FATAL" name="Mark Unused, Do Not Delete">
      An agent does not delete. Anything retired moves to `_not_used/`, which is a working
      directory and is not committed. The tracked record is a `RETIRED.md` index at the
      root, carrying a row per retired thing saying why
      and what replaced it. Anything that would need a recursive force-delete becomes a **list
      handed to a human to run**. A recorded authorisation from an earlier session is not
      permission to delete today.
    </directive>

    <directive priority="FATAL" name="No Secret Ever Enters A Commit">
      A reference without a scheme is an error, not a literal. Show `env://…` or
      `file://…#key`, never a token, channel id, workspace URL or account email inline.

      Config precedence is fixed and nothing discovers a file by climbing: an **environment
      variable** wins, then the **registry**, then this project's own `.agents/*.json`.
    </directive>

    <directive priority="FATAL" name="Verify Before Claiming">
      Run the thing. Quote the output. "Tests pass" without the output is a claim, not a result,
      and a build that compiled is not a feature that works.

      If a step was skipped, say so. If something is blocked, finish everything that is not and
      state plainly what was left and why.
    </directive>

    <directive priority="FATAL" name="English Only">
      All instructions, tickets, commits, and reports are written in English.
      <Delete this directive, or narrow it, if your project has a different convention.>
    </directive>
  </core_directives>

  <skill_routing>
    <instruction>
      Before performing any task that needs a skill, READ the index to discover what is
      installed and its exact path. Do NOT guess paths from memory.
    </instruction>
    <mapping>
      - Skills: `~/.claude/skills/INDEX.md`
      - Agents: `~/.claude/agents/INDEX.md`
      Both are generated by the toolkit's sync scripts from the frontmatter of what they
      install, so they are current as of the last sync and no more.
    </mapping>
  </skill_routing>

  <git>
    **The rules are the `git-workflow` skill** — branch naming, commit format, which merge
    strategy belongs to which target. The short version:

    Work lands on `<develop>` through a PR. Never push to `<main>`. Branch as
    `<type>/<KEY>-<slug>` — `feature/`, `fix/`, `chore/`, `docs/` — with the Jira key in it:
    `drunken-usage --by ticket` reads the key back off the branch and has no other source.

    Do not stack a PR on another PR's branch: when the base merges and is deleted, GitHub closes
    the stacked one. Branch from `<develop>` and cherry-pick if you need something that has not
    landed yet.

    Force-push and hard reset are not yours to run. Raise it with a human instead.
  </git>

  <execution_protocol>
    Before modifying any file or proposing any change, reason through:
    1. Objective: what is being changed, and why.
    2. Discovery: which existing code, tickets, or decisions are affected.
    3. Impact: what else must change alongside the primary target.
    4. Action plan: numbered steps of exactly what will be written or modified.

    Only after that reasoning may you execute file operations.
  </execution_protocol>

  <project_specific>
    <!-- Everything above is portable. Put what is true only of THIS project here:
         build and test commands, deploy steps, the directories that are off-limits,
         the conventions a newcomer would otherwise violate. -->

    **Build:** `<command>`
    **Test:** `<command>` — this is the command that must be run and quoted before anything is
    called done.
    **Lint / format:** `<command>`

    <Anything else a new agent must know before touching this codebase.>
  </project_specific>

</system_prompt>
