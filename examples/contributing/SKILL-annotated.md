# Annotated SKILL.md — Contributor Reference

> This file walks through every section of a `SKILL.md` with inline comments explaining what
> each field does and how to write it correctly.
>
> The skill used as the base is `breakdown` (`skills/flow/breakdown/SKILL.md`) — trimmed for
> annotation clarity. It was chosen because it exercises everything a coordination skill needs:
> frontmatter triggers ending in a slash command, an MCP requirement declared in `<constraints>`,
> `<execution_rules>` with `priority` attributes, an `<action_sequence>`, an `<output_format>`,
> and several rules that point at an authority instead of restating it.
>
> Read the live file alongside this one. This copy is shortened; the live one is the skill.

---

<!-- FRONTMATTER — required, and it comes FIRST.

     A skill without frontmatter is invisible: `install_skills.sh` reads `description:` to build
     INDEX.md, and Claude reads it to decide whether the skill is relevant at all.

     Two fields:
       name:        kebab-case, and it MUST match the directory name. The installer flattens
                    skills by directory basename, so two skills with one name collide and the
                    install refuses to run.
       description: an English summary that ALSO carries the activation triggers.

     There is NO separate `**Trigger/Keywords:**` line any more. Triggers live here, in the
     description, and the description ends with the slash command: "Trigger on /breakdown."
     Keep "Trigger on /x." on ONE line -- the installer greps for it line by line, and a
     description wrapped between "Trigger on" and "/breakdown" indexes with no trigger at all. -->

```yaml
---
name: breakdown
description: >
  Turns PRD.md and DOMAIN.md into the Jira hierarchy — one Epic per bounded context, Stories from
  the requirements it serves, Tasks sized to a day — with every level labelled `req:REQ-xxx` so the
  work can be traced back. Apply after /ddd, when a backlog must be cut from agreed requirements,
  or when a bug arriving mid-flight needs a ticket against the requirement it breaks.
  Trigger on /breakdown.
---
```

<!-- Write the description for the decision it has to support: "should I load this skill?"
     State WHEN to apply it, and end with the slash command. More phrasings means more coverage.

     Note what this one does with its when-clause. A skill that sits in the middle of a flow says
     which step it follows ("Apply after /ddd") and names the off-path case that still belongs to
     it ("a bug arriving mid-flight"). Both are phrasings a user actually types. A description
     that only described the happy path would leave the bug case landing nowhere. -->

---

# Skill: Breakdown

<!-- TITLE
     Format: "# Skill: <Human-Readable Title>"
     The display name — used in the README catalog and by contributors.
     Short and action-oriented. -->

**Version:** v1.0.0
**Description:** Proposes the whole Jira hierarchy from `PRD.md` and `DOMAIN.md`, and creates it — labelled and traceable — only after the Boss approves the plan.

<!-- VERSION is optional SemVer. Bump the minor when behaviour changes, the major when a rule
     that other skills depend on changes.

     DESCRIPTION is one line, and it should answer "what does this skill make the AI do?"
     Do NOT write "this skill..." — start with the noun or the verb. Note that this one carries
     the halt in the sentence itself: what it produces, and the condition under which it is
     allowed to produce it. -->

---

<!-- The horizontal rule separates the header from the system_prompt block.
     Do not remove it — it is part of the canonical structure. -->

<system_prompt>
  <role>
    When this skill applies, act as the planner who turns agreed requirements into the work items
    an agent can pick up. This is the step where traceability is created or lost for good: a
    ticket created without its requirement label is work nobody can trace back, and no later step
    can repair it, because the reason it existed was only ever in the session that made it.
  </role>

  <!-- ROLE — required.
       One paragraph. Set the obligation, and say what makes this step different from the ones
       around it. This role earns its length with the second sentence: it names the one mistake
       that cannot be undone later. A role that only said "create Jira tickets from the PRD"
       would be a job description; this one tells the model what it is guarding. -->

  <the_hierarchy>

    REQ-xxx  →  Epic  →  Story  →  Task  →  Subtask

    - **Epic** — one per bounded context in `DOMAIN.md`. No more, no fewer.
    - **Story** — from the requirements that context serves. A user-visible outcome.
    - **Task** — the work. A **vertical slice finishable in a day**: that is the sizing test.
    - **Subtask** — only when a Task genuinely has ordered steps that must be done in that order.

    The five ticket templates — Epic, Story, Task, Subtask, Bug — live in the `jira-tickets`
    skill, along with the field limits and the status lifecycle. That skill is authoritative; read
    it, do not restate it, do not contradict it.
  </the_hierarchy>

  <!-- POINT AT AUTHORITIES, DO NOT COPY THEM.
       This is the single most important habit in this repo, and the last paragraph above is the
       pattern to copy. Three projects holding three copies of one rule is the failure the whole
       Jira migration was about. If a rule already has a home, link to it and name the two or
       three consequences that matter locally — never paste the rule itself. A copy cannot be
       kept in sync; a link cannot go out of sync.

       Read the shape of that pointer closely. It does three things in two sentences: it names the
       authority (`jira-tickets`), it says exactly what lives there (templates, field limits,
       lifecycle), and it says what this skill may do with it — "read it, do not restate it, do
       not contradict it". Naming the file is not enough on its own; without the second half, the
       next contributor helpfully pastes a summary in and the copy begins.

       Note also what the block DOES keep locally: the shape of the tree and the one-day sizing
       test. Those are `breakdown`'s own rules and have no other home, so they belong here. The
       test is not "is this rule important" — it is "does this rule already live somewhere else". -->

  <execution_rules>

    <!-- EXECUTION RULES — domain-specific, optional, and the usual home for the rules that are
         about the WORK rather than about the skill's limits. Each `<rule>` takes both attributes:

           priority=  FATAL or HIGH, same meaning as in <constraints> below
           name=      a short Title Case handle, so the rule can be cited in review and in a
                      commit message without quoting the paragraph

         A rule is a paragraph, not a line: state the rule, then state what breaks if it is
         ignored. The consequence is the part that survives being skimmed. -->

    <rule priority="FATAL" name="Every Level Carries req:REQ-xxx">
      Epic, Story, Task and Subtask each carry the label `req:REQ-xxx` for the requirement they
      serve. A ticket serving two requirements carries both labels.

      That label is the only thing `/audit` can trace on. It has no other source: not the summary
      text, not the parent chain, not the branch name. A ticket created without it is untraceable
      work, and the audit reports it as an orphan rather than as progress.
    </rule>

    <!-- ^ The second paragraph is the whole reason the rule holds. "It has no other source" is a
         falsifiable claim about the system, and it tells the model why no workaround exists.
         A rule stated without its mechanism gets negotiated away the first time it is
         inconvenient. -->

    <rule priority="FATAL" name="Nothing Is Created Until The Boss Approves">
      Print the whole proposed hierarchy as a table first and halt. No `jira_create_issue` before
      a yes. A backlog created and then corrected leaves keys that mean nothing and comments
      explaining a plan that changed.
    </rule>

    <!-- THE HALT-FOR-APPROVAL PATTERN.
         Any skill whose output is expensive to undo needs one of these, and it has three parts,
         all of which must be present or the halt does not hold:

           1. WHAT to print before stopping — here, "the whole proposed hierarchy as a table".
              Vague is fatal: "summarise the plan" is satisfied by one sentence, and a Boss
              cannot approve what they cannot see.
           2. WHICH CALL is forbidden until the answer arrives — named, by tool name. "Wait for
              approval" is advice; "no `jira_create_issue` before a yes" is a gate.
           3. WHY the undo is not free — keys that mean nothing, comments explaining a plan that
              changed. Jira has no delete here, so "we can fix it after" is false, and the rule
              says so rather than assuming the reader knows.

         The halt also shows up twice more in this file — as step 6 of the <action_sequence> and
         as a `<constraint>`. That repetition is deliberate and is the one place this repo
         tolerates it: the rule explains, the sequence positions it, the constraint forbids the
         opposite. They are three views of one rule in one file, not three copies of a rule in
         three files.

         When the halt belongs on an action outside the skill's own reach — installing, deleting,
         anything irreversible off-repo — `ask-boss` is the authority on how to ask without
         stalling the session. Point at it; do not re-derive the protocol. -->

    <rule priority="FATAL" name="Probe The Instance Before Writing To It">
      Call `jira_board_info` before creating anything. It reports the issue types this project
      accepts, the settable field ids and whether this board has a backlog at all. Field ids
      differ per instance — never hardcode one found in a payload, and never assume a backlog.
    </rule>

    <rule priority="FATAL" name="Create, Do Not Start">
      Everything this skill creates stays **in the backlog** and in **`TODO`**. Never call
      `jira_transition_issue` or `jira_start_task` from here. Moving work onto the board and
      starting it are separate acts, with separate owners.
    </rule>

    <!-- ^ Scope, stated as a prohibition. A planning skill that also starts the work is a skill
         nobody can run safely on a whim. When two acts have different owners, say so in the rule
         — that is the sentence a contributor will otherwise "simplify" away. -->

    <rule priority="HIGH" name="Urgency Is A Label, From MoSCoW">
      The requirement's MoSCoW class in the PRD sets it: Must → `critical` or `high`, Should →
      `medium`, Could → `low`, Won't → **no ticket at all**. Lower case, one per ticket.

      `priority` cannot be set on this Jira and reads `Medium` on everything, so sorting by it
      produces one bucket that looks like a priority order.
    </rule>

    <!-- ^ HIGH, not FATAL, and the difference is real: a Boss can overrule the mapping for one
         ticket. What is FATAL is the constraint further down that forbids setting `priority` at
         all. Judgement calls are HIGH; facts about what the instance cannot do are FATAL. -->

  </execution_rules>

  <action_sequence>

    <!-- ACTION SEQUENCE — domain-specific, optional, but usually worth having.
         Ordered steps, written as imperatives. Start with context-gathering, end with a
         verification or a halt gate. Steps reinforce the rules; they are not redundant with
         them — the rules say what must be true, the sequence says in what order to make it so. -->

    1. LOCATE: `project-docs` — print the block. `PRD.md` and `DOMAIN.md` are both required; point
       at `/prd` or `/ddd` for a missing one rather than working from what you can infer.
    2. PROBE: `jira_board_info` — issue types, settable fields, backlog present?
    3. MAP: one Epic per context; Stories from that context's requirements; Tasks per Story, each
       sized to a day; Subtasks only where steps are genuinely ordered.
    4. CHECK: every requirement reaches at least one Task, every ticket has its `req:` label,
       every Task passes the one-day test. Report any requirement that reaches nothing.
    5. SEQUENCE: group Tasks by the files they touch — sequence or parallel.
    6. PROPOSE: print the table. Halt for approval.
    7. CREATE: on a yes, `jira_create_issue` top-down so each child has its parent key, confirm
       each with `jira_search_issues`, and `jira_move_to_backlog` so nothing lands on the board.
    8. REPORT: the created keys, and the one open question about execution order.

    <!-- Three things to take from this sequence.

         Step 1 is a second pointer at an authority — `project-docs` owns where a project's
         documents live, so this skill names it and prints its block instead of hardcoding paths
         that differ per project. A sequence step can be a pointer too.

         Step 4 is a coverage check, and it runs BEFORE the halt. Handing the Boss a plan you have
         not checked wastes the one review you get.

         Step 7 confirms each creation with `jira_search_issues`. A tool call that returned is not
         a ticket that exists. Every skill that writes something should read it back before
         claiming success. -->

  </action_sequence>

  <output_format>

    <!-- OUTPUT FORMAT — required.
         Specify the structure of what the AI prints TO THE CONVERSATION. If the skill's main
         product is a file, describe the report about that file here, and put the file's shape
         in a <template> block of its own.

         Be concrete. A format the AI has to invent is a format that changes every run.

         A skill that halts has TWO outputs — the proposal and the result — and both belong here.
         Describing only the happy-path report leaves the more important one, the thing the Boss
         has to approve, up to improvisation. -->

    Print the `project-docs` block, then the proposal, then halt:

    - **Hierarchy** — a table: Epic / Story / Task | summary | `req:REQ-xxx` | urgency label |
      sequence-or-parallel. Indent the levels so the tree reads at a glance.
    - **Coverage** — requirements that reach no Task, and Tasks that carry no requirement. Say
      "none" rather than omitting the section.
    - **Sequencing** — which Tasks share files and must run one after another, and which share
      nothing.
    - End with two questions: "Create these tickets?" and "Execute in sequence or in parallel?"

    After creation, report a table of created keys with their parent and labels, and state that
    everything is in the backlog in `TODO`, unassigned.
  </output_format>

  <!-- ^ "Say 'none' rather than omitting the section" is worth stealing. An omitted section is
       ambiguous between "nothing to report" and "did not check"; an explicit "none" is a claim
       the Boss can hold you to. -->

  <constraints>

    <!-- CONSTRAINTS — required.
         Priority attributes signal severity:
           priority="FATAL"  → never acceptable; the skill must refuse
           priority="HIGH"   → strong preference; deviation needs an explicit user override
         No MEDIUM or LOW. If a rule is not at least HIGH, it is a workflow step, not a
         constraint.

         Write each one as a prohibition with a consequence, not a preference. "Never set
         `priority`" beats "prefer labels" because there is nothing left to interpret.

         Constraints are one line each. Where a rule needs a paragraph to explain itself, it
         belongs in <execution_rules> and appears here as the short prohibition — which is
         exactly what the middle four below are. -->

    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server, declared in the project's `.mcp.json`. Without it this skill cannot run — say so rather than falling back to a file or a shell script.</constraint>

    <!-- ^ A skill that calls an MCP tool MUST name the server it needs, right here. A project
         without that server otherwise gets a skill that fails in a confusing way instead of one
         that explains itself. Most skills in this repo need no server at all and say nothing.

         The tail matters as much as the name: "rather than falling back to a file or a shell
         script". Without it, a missing server becomes an improvised `.md` backlog or a hand-rolled
         shell call to the Jira API — a second surface, created by helpfulness. -->

    <constraint priority="FATAL">Never create or write to `.claude/board/` or `.agents/board/`. The `board_*` tools are retired.</constraint>
    <constraint priority="FATAL">Never create a ticket at any level without its `req:REQ-xxx` label.</constraint>
    <constraint priority="FATAL">Never create anything before the Boss approves the printed hierarchy.</constraint>
    <constraint priority="FATAL">Never transition a ticket or start a task from this skill.</constraint>
    <constraint priority="FATAL">Never set `priority`, and never invent story points. Neither is settable here.</constraint>
    <constraint priority="HIGH">Never assign a ticket at creation time.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>

    <!-- The English-only constraint appears in every skill and agent in this repo. It is a
         FATAL project directive, not a per-skill preference. -->

  </constraints>

</system_prompt>

---

## The required blocks, in order

| # | Block | Required | Notes |
|---|---|---|---|
| 1 | YAML frontmatter | yes | `name:` matches the directory; `description:` carries the triggers and ends with the slash command |
| 2 | `# Skill: <Title>` | yes | display name |
| 3 | `**Version:**` | no | SemVer |
| 4 | `**Description:**` | yes | one line |
| 5 | `---` | yes | separates header from the prompt |
| 6 | `<system_prompt>` | yes | must contain `<role>`, `<constraints>`, `<output_format>` |

Domain blocks — `<execution_rules>`, `<workflow>`, `<action_sequence>`, `<template>`,
`<report_structure>` — may be added freely. `<role>`, `<constraints>` and `<output_format>` are
never optional.

---

## Checklist before submitting a new skill

- [ ] YAML frontmatter is present, and `name:` matches the directory name exactly
- [ ] `description:` states when to apply the skill and ends with `Trigger on /<command>.`
- [ ] `Trigger on /<command>.` is on a single line, not wrapped
- [ ] The slash command does not collide with an existing one — check `skills/INDEX.md`
- [ ] Title is `# Skill: <Title>`, description is one line, not starting with "This skill..."
- [ ] `<role>`, `<constraints>` and `<output_format>` are all present
- [ ] Every `<rule>` and `<constraint>` has `priority=`, and rules have `name=`
- [ ] If the skill calls an MCP tool, a `<constraint>` names the server it requires
- [ ] Rules that live elsewhere are LINKED, not copied — named, with what they own and the
      instruction not to restate or contradict them
- [ ] If the skill does anything expensive to undo, it prints a concrete proposal, names the call
      it will not make before a yes, and says why the undo is not free
- [ ] All content is in English
- [ ] You ran `./scripts/install/install_skills.sh --index-only` and confirmed the skill appears
      in `INDEX.md` with the trigger you expected
