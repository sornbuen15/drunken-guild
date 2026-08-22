# Annotated SKILL.md — Contributor Reference

> This file walks through every section of a `SKILL.md` with inline comments explaining what
> each field does and how to write it correctly.
>
> The skill used as the base is `issue-intake` — trimmed for annotation clarity. It was chosen
> because it exercises everything a coordination skill needs: frontmatter triggers, an MCP
> requirement declared in `<constraints>`, and a rule that points at an authority rather than
> restating it.

---

<!-- FRONTMATTER — required, and it comes FIRST.

     A skill without frontmatter is invisible: `sync_skills.sh` reads `description:` to build
     INDEX.md, and Claude reads it to decide whether the skill is relevant at all.

     Two fields:
       name:        kebab-case, and it MUST match the directory name. The installer flattens
                    skills by directory basename, so two skills with one name collide and the
                    install refuses to run.
       description: an English summary that ALSO carries the activation triggers.

     There is NO separate `**Trigger/Keywords:**` line any more. Triggers live here, in the
     description, and the description ends with the slash command: "Trigger on /issue."
     Keep "Trigger on /x." on ONE line -- the installer greps for it line by line, and a
     description wrapped between "Trigger on" and "/issue" indexes with no trigger at all. -->

```yaml
---
name: issue-intake
description: >
  Captures user-reported bugs and problems as properly classified Jira tickets via
  drunken-jira-mcp. Apply whenever the user reports a bug, says something is broken, mentions a
  problem they found, or wants to log an issue — even casually, like "heads up, the login page is
  throwing a 500". Trigger on /issue.
---
```

<!-- Write the description for the decision it has to support: "should I load this skill?"
     State WHEN to apply it, include the casual phrasings a user actually types ("something is
     broken"), and end with the slash command. More phrasings means more coverage. -->

---

# Skill: Issue Intake

<!-- TITLE
     Format: "# Skill: <Human-Readable Title>"
     The display name — used in the README catalog and by contributors.
     Short and action-oriented. -->

**Version:** v3.0.0
**Description:** Captures user-reported bugs and problems as properly classified Jira tickets via drunken-jira-mcp.

<!-- VERSION is optional SemVer. Bump the minor when behaviour changes, the major when a rule
     that other skills depend on changes.

     DESCRIPTION is one line, and it should answer "what does this skill make the AI do?"
     Do NOT write "this skill..." — start with the noun or the verb. -->

---

<!-- The horizontal rule separates the header from the system_prompt block.
     Do not remove it — it is part of the canonical structure. -->

<system_prompt>
  <role>
    When this skill applies, follow the Issue Intake protocol — the front door for user-reported
    problems: capture, classify, and route issues into Jira via drunken-jira-mcp tools.
    Do not fix, investigate, or suggest solutions.
  </role>

  <!-- ROLE — required.
       One paragraph. Set the obligation and, just as importantly, the NON-obligation.
       "Do not fix, investigate, or suggest solutions" is doing more work here than the
       positive half: it is what stops the skill from quietly becoming a debugging session. -->

  <ticket_rules>
    The ticket shape, the field limits, and the lifecycle are NOT restated here. They live in
    `~/Projects/drunken-team/.agents/skills/jira-tickets/SKILL.md` and that file is authoritative.
    Read it before writing a ticket.
  </ticket_rules>

  <!-- POINT AT AUTHORITIES, DO NOT COPY THEM.
       This is the single most important habit in this repo. Three projects holding three copies
       of one rule is the failure the whole Jira migration was about. If a rule already has a
       home, link to it and name the two or three consequences that matter locally — never
       paste the rule itself. A copy cannot be kept in sync; a link cannot go out of sync. -->

  <workflow>

    <!-- WORKFLOW / ACTION SEQUENCE — domain-specific, optional, but usually worth having.
         Ordered steps, written as imperatives. Start with context-gathering, end with a
         verification or a halt gate. Steps reinforce the rules; they are not redundant with
         them. -->

    <step name="1. Capture">
      Extract from the user's message: problem statement, location, onset, severity, evidence.
    </step>

    <step name="2. Classify">
      Severity becomes a **label**, never the `priority` field.
      Call `jira_board_info` first to confirm the issue types this project accepts and the
      settable field ids. They differ per instance — never hardcode one found in a payload.
    </step>

    <step name="3. Create">
        jira_create_issue({ summary, description, labels }) → { key }
        jira_search_issues({ jql: "key = <key>" }) — confirm before reporting success.
    </step>

    <!-- Note the last line of step 3. A tool call that returned is not a ticket that exists.
         Every skill that writes something should read it back before claiming success. -->

  </workflow>

  <constraints>

    <!-- CONSTRAINTS — required.
         Priority attributes signal severity:
           priority="FATAL"  → never acceptable; the skill must refuse
           priority="HIGH"   → strong preference; deviation needs an explicit user override
         No MEDIUM or LOW. If a rule is not at least HIGH, it is a workflow step, not a
         constraint.

         Write each one as a prohibition with a consequence, not a preference. "Never set
         `priority`" beats "prefer labels" because there is nothing left to interpret. -->

    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server, declared in the project's `.mcp.json`. Without it this skill cannot run — say so rather than falling back to a file or a shell script.</constraint>

    <!-- ^ A skill that calls an MCP tool MUST name the server it needs, right here. A project
         without that server otherwise gets a skill that fails in a confusing way instead of one
         that explains itself. Most skills in this repo need no server at all and say nothing. -->

    <constraint priority="FATAL">Never create or write to `.claude/board/` or `.agents/board/`. The `board_*` tools are retired.</constraint>
    <constraint priority="FATAL">Never set `priority`. It is not settable here; use labels.</constraint>
    <constraint priority="FATAL">Never investigate, diagnose, or fix the reported issue — only capture and route it.</constraint>
    <constraint priority="HIGH">Always confirm the created ticket via `jira_search_issues` before reporting success.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>

    <!-- The English-only constraint appears in every skill and agent in this repo. It is a
         FATAL project directive, not a per-skill preference. -->

  </constraints>

  <output_format>

    <!-- OUTPUT FORMAT — required.
         Specify the structure of what the AI prints TO THE CONVERSATION. If the skill's main
         product is a file, describe the report about that file here, and put the file's shape
         in a <template> block of its own.

         Be concrete. A format the AI has to invent is a format that changes every run. -->

    **Issue captured:** &lt;ISSUE-KEY&gt;
    **Type:** &lt;type&gt; | **Labels:** &lt;label, label&gt; | **Suggested specialist:** @&lt;agent-slug&gt;
    **Where it is:** Backlog (not in the current working set; status TODO)
    **Next step:** Run /refine to move this onto the board when ready to schedule it.
  </output_format>

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
- [ ] Rules that live elsewhere are LINKED, not copied
- [ ] All content is in English
- [ ] You ran `./scripts/install/sync_skills.sh` and confirmed the skill appears in `INDEX.md`
      with the trigger you expected
