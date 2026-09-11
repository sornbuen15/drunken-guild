---
name: confluence-sync
description: >
  Synchronizes a project's own documents (brief, requirements, spec, architecture, policy, ADRs,
  and API docs) to the Confluence Cloud space, maintaining the page hierarchy. Apply when the user
  wants the project's documentation published or refreshed in Confluence. Trigger on
  `/confluence-sync`, "sync confluence", "publish confluence".
---

# Skill: Confluence Documentation Sync
**Version:** v2.0.0
**Description:** Publishes whichever project documents exist to Confluence Cloud, with ADRs grouped under one parent page.

---
<system_prompt>
  <role>
    When this skill applies, publish the project's documents to Confluence as they are — the
    ones that exist, from where the `project-docs` skill finds them — and report every page it
    created or updated.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="API Bridge Verification">
      Ensure the `scripts/confluence_bridge.py` script exists and is executable. The access token
      is read from the `JIRA_TOKEN` environment variable by the bridge itself; never print it, and
      never pass it on a command line.
    </rule>

    <rule priority="FATAL" name="Publish What Exists">
      Locate the documents with the `project-docs` skill and print its block. Publish each one it
      found; skip each one it did not, and list the skipped ones in the report. Never write a
      missing document in order to have something to publish.
    </rule>

    <rule priority="HIGH" name="API Reference Only If The Project Has One">
      If the project has `doc/openapi.md`, publish it. If it has only `doc/openapi.json` and its
      own converter to Markdown, run that converter first. drunken-guild ships no converter; if the
      project has none, skip the API Reference and say so.
    </rule>
  </execution_rules>

  <action_sequence>
    1. VERIFY the bridge (rule above).
    2. LOCATE documents with `project-docs`.
    3. PUBLISH root-level pages, each only if found:
         - `PROJECT_BRIEF.md` → `Project Brief`
         - `PROJECT_SPEC.md` → `Project Specification`
         - `REQUIREMENTS.md` → `Requirements`
         - `ARCHITECTURE.md` → `Architecture Guide`
         - `POLICY.md` → `Security & Integration Policy`
         - `doc/openapi.md` → `API Reference`
    4. ADRs, only if `adr/` exists and holds any:
         a. Create/update the parent page `Architecture Decision Records (ADRs)` under root, and
            keep the numeric `page_id` it returns.
         b. Push every `adr/ADR-*.md` as a child of that page, in filename order. Title each from
            the document's own first heading — `ADR-001: Autonomous Action Authorization` — not
            from a list written into this skill.
    5. REPORT (output format below).
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires `scripts/confluence_bridge.py` and a `JIRA_TOKEN` in the environment. Without either, stop and say which is missing.</constraint>
    <constraint priority="FATAL">Never generate a document that does not exist in order to publish it.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    The `project-docs` block, then one table:

    | Document | Confluence title | Page ID | Result (created / updated / skipped — not found) |
  </output_format>
</system_prompt>
