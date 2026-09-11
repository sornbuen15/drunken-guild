---
name: project-docs
description: >
  The one contract for a project's own documents — which ones exist, where to look for them, how
  to read them together, and what to do when one is missing or two disagree. Apply before any
  skill or task that reads a project's brief, requirements, spec, architecture or policy:
  /init-project, a codebase audit, a test report, a Confluence sync, or planning a feature.
---

# Skill: Project Documents
**Version:** v1.0.0
**Description:** The one contract for finding and reading a project's brief, requirements, spec, architecture and policy.

---
<system_prompt>
  <role>
    When this skill applies, locate the project's documents before acting on any of them, read
    every one that exists, and never stand in for one that does not. Other skills defer to this
    one for where documents live and what their absence means; they do not restate it.
  </role>

  <documents>
    | document | answers |
    |---|---|
    | `PROJECT_BRIEF.md` | what is built, for whom, the stack, the constraints, what is out of scope |
    | `PROJECT_SPEC.md` | what the system must do, in detail — features, phases, flows |
    | `REQUIREMENTS.md` | Must / Should / Could / Won't, performance and security targets, Definition of Done |
    | `ARCHITECTURE.md` | how it is built — layers, boundaries, dependencies |
    | `POLICY.md` | what it may and may not do; the gates an audit or test report passes or fails against |
    | `adr/` | decisions already made, each with its reasoning |

    A **brief** is `PROJECT_BRIEF.md` or `PROJECT_SPEC.md`. Either one is enough to start. When
    both exist, read both: the spec is the detail under the brief, not a replacement for it.

    Templates for `PROJECT_BRIEF.md` and `REQUIREMENTS.md` are in drunken-guild's `templates/`.
    The other four have none on purpose — they record what a project has actually decided.
  </documents>

  <lookup>
    Search relative to the **project root** — the directory that holds the project's own
    `CLAUDE.md` or `AGENTS.md` — not wherever the session happens to have been opened. A project
    whose code sits one level below a wrapper directory has its root where that file is.

    Look in this order, and take the first location that has each document:

      1. `.ai/` — the shared layer every agent reads, and the recommended home for new projects
      2. the project root itself
      3. `.claude/`
      4. `docs/`

    **The same document in two locations is two surfaces.** If `PROJECT_SPEC.md` is in both
    `.ai/` and `.claude/`, stop and ask which is authoritative. The order above is for finding a
    document, not for deciding between two copies of one.
  </lookup>

  <reading_together>
    Documents are read together, not ranked. The brief and spec say what to build; requirements
    say how much of it matters and when it is done; architecture says where it lands; policy says
    what nothing may violate.

    When two disagree — the brief puts a feature out of scope and the spec requires it, a
    requirement contradicts a policy — stop and quote both passages. Picking one silently is a
    product decision nobody made.
  </reading_together>

  <missing_documents>
    <rule priority="FATAL" name="Read What Exists">
      Proceed on the documents present. Say in your output which were read, from where, and which
      were looked for and not found. An absent document is a fact to report, not a gap to fill.
    </rule>

    <rule priority="FATAL" name="No Brief, No Start">
      With neither `PROJECT_BRIEF.md` nor `PROJECT_SPEC.md` in any of the four locations, stop.
      Name both files and the four locations searched, and point at `templates/PROJECT_BRIEF.md`.
      Do not reconstruct a brief from the code or the conversation and carry on as if it existed.
    </rule>

    <rule priority="FATAL" name="Never Generate A Missing Document And Treat It As Decided">
      Do not write `ARCHITECTURE.md`, `POLICY.md`, `REQUIREMENTS.md` or a spec on your own
      initiative. A generated architecture or policy reads to every later skill as the project's
      decision when nobody decided it — an audit then grades the code against a guess, and a
      backlog is cut to fit it.

      A skill that needs a missing document uses the defaults it states for itself, and says that
      it did.

      You may **offer** to draft a missing document from the brief and requirements. Write it only
      after the Boss says yes, head it
      `> Draft — generated from <sources> on <YYYY-MM-DD>. Not yet reviewed.`, and leave removing
      that line to a human. Until it is gone, treat the document as absent.
    </rule>
  </missing_documents>

  <constraints>
    <constraint priority="FATAL">Requires no MCP server. It reads files and nothing else.</constraint>
    <constraint priority="FATAL">Never move, rename or merge a project's documents to fit this lookup. Report what you found instead.</constraint>
    <constraint priority="FATAL">Never treat a document headed as a draft as the project's decision.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Before acting on the documents, print what was found:

    ```
    Project documents — root: <path>
      read:       PROJECT_BRIEF.md (.ai/), REQUIREMENTS.md (.ai/), POLICY.md (root)
      not found:  PROJECT_SPEC.md, ARCHITECTURE.md
      conflicts:  none
    ```

    If the output is a stop — no brief, a document in two places, two documents disagreeing —
    print the same block with the reason on its own line, and nothing after it.
  </output_format>
</system_prompt>
