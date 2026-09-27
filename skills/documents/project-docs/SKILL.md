---
name: project-docs
description: >
  Use when a step has to find, create or reconcile a project's own documents — "where does this
  project keep its PRD?", "there are two PRD.md files, which one wins?". The one contract for
  locating PRD.md, DOMAIN.md, audit reports and ADRs: the map in AGENTS.md, the defaults without
  one, and what a duplicate or an absent file means. /prd, /clarify, /ddd, /breakdown, /build and
  /audit all start here.
---

# Skill: Project Documents
**Version:** v2.0.0
**Description:** Where a project's documents live, and what to do when one is missing or in two places.

---
<system_prompt>
  <role>
    When this skill applies, locate the project's documents before acting on any of them, and never
    stand in for one that does not exist. Every flow step defers to this skill for where a document
    lives; none of them restates it, and none of them hard-codes a path.
  </role>

  <the_map>
    **`AGENTS.md` at the project root is the map.** It carries a `## Documents` section naming each
    document and its path, because a project is allowed to keep its documents somewhere else and the
    skills must follow rather than insist.

    The project root is the directory holding `AGENTS.md` — not wherever the session was opened. A
    project whose code sits below a wrapper directory has its root where that file is.

    | document | what it answers |
    |---|---|
    | `PRD.md` | what is being built and for whom, and every requirement, each with an id `REQ-xxx` |
    | `DOMAIN.md` | the contexts, the shared vocabulary and the core entities — the Epics come from here |
    | `audit/` | one report per audit run: what traced, what did not |
    | `docs/` | what people read — guides and API reference |
    | `docs/decisions/` | ADRs: decisions already made, each with its reasoning |

    **When there is no map, these are the defaults**, and a skill that uses them says so:
    `.ai/PRD.md`, `.ai/DOMAIN.md`, `.ai/audit/`, `docs/`, `docs/decisions/`.

    An older project may still have its requirements split across `PROJECT_BRIEF.md`,
    `REQUIREMENTS.md` and `PROJECT_SPEC.md`. Read them where the map says they are; `/prd`
    consolidates them into one `PRD.md` when the Boss asks it to. Do not consolidate silently.
  </the_map>

  <rules>
    <rule priority="FATAL" name="Read What Exists, Report What Does Not">
      Proceed on the documents present. Say which were read, from where, and which were looked for
      and not found. An absent document is a fact to report, not a gap to fill.
    </rule>

    <rule priority="FATAL" name="Two Copies Is A Stop">
      The same document in two locations is two surfaces that can disagree. Name both paths and ask
      which is authoritative. The defaults above are for finding a document, never for choosing
      between two copies of one.
    </rule>

    <rule priority="FATAL" name="Never Generate A Missing Document And Treat It As Decided">
      A generated `DOMAIN.md` or a generated requirement reads to every later step as the project's
      decision when nobody decided it — `/breakdown` then cuts a backlog to fit a guess and `/audit`
      grades the code against it.

      `/prd` and `/ddd` exist to write these documents **with the Boss**, which is not the same as
      inventing one on your own initiative. Outside those two steps, offer a draft and write it only
      after the Boss says yes, headed
      `> Draft — generated from <sources> on <YYYY-MM-DD>. Not yet reviewed.`
      Until a human removes that line, treat the document as absent.
    </rule>

    <rule priority="HIGH" name="Requirements Are Read By Id">
      Every requirement in `PRD.md` has an id `REQ-xxx`, and that id is what the Jira hierarchy and
      the audit trace against. A requirement without one cannot be traced — report it rather than
      assigning it an id yourself.
    </rule>
  </rules>

  <constraints>
    <constraint priority="FATAL">Requires no MCP server. It reads files and nothing else.</constraint>
    <constraint priority="FATAL">Never move, rename or merge a project's documents to fit the defaults. Report what you found instead.</constraint>
    <constraint priority="FATAL">Never treat a document headed as a draft as the project's decision.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Before acting on the documents, print what was found:

    ```
    Project documents — root: <path>, map: AGENTS.md | defaults
      read:       PRD.md (.ai/), DOMAIN.md (.ai/)
      not found:  docs/decisions/
      conflicts:  none
    ```

    If the result is a stop — two copies of one document, a requirement without an id, a document
    the step needs and cannot find — print the same block with the reason on its own line, and
    nothing after it.
  </output_format>
</system_prompt>
