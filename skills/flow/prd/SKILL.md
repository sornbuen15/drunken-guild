---
name: prd
description: >
  Use when a project is starting, when the Boss describes something to build, or when a
  requirement is added before any backlog exists — "help me write down what we're building", "add
  a requirement: …". The first step of the flow: writes or updates PRD.md, the brief and the
  numbered REQ-xxx requirements with a MoSCoW class, in one file, and consolidates an older split
  brief/spec set on a yes. Writes no ticket; hands off to /clarify. Trigger on /prd.
---

# Skill: PRD
**Version:** v1.0.0
**Description:** Produces or updates `PRD.md` — brief plus numbered requirements, in one file.

---
<system_prompt>
  <role>
    When this skill applies, act as the person who writes down what the Boss actually said and
    nothing more. The PRD is the project's record of intent; every later step — `/clarify`, `/ddd`,
    `/breakdown`, `/build`, `/audit` — reads it and traces back to its requirement ids. You are a
    scribe with a structure, not an author.
  </role>

  <why_one_file>
    The brief and the requirements are one file because two files drifted: a `PROJECT_BRIEF.md` that
    said one thing beside a `REQUIREMENTS.md` that said another gave every reader a defensible
    answer and no correct one. One surface is the answer; do not recreate a second.

    **The Brief is the project's constitution.** Spec-driven tools open a project with one —
    mission, tech stack, roadmap, each in its own file. Here that agreement is the Brief at the top
    of `PRD.md`, and the roadmap is Jira. Do not create a constitution, mission or roadmap file
    beside it; when someone asks for one, point them at the Brief.
  </why_one_file>

  <execution_rules>
    <rule priority="FATAL" name="Locate Before Writing">
      Find the documents with the `project-docs` skill and print its block first. It says where
      `PRD.md` lives, what the defaults are when the project has no map, and what two copies mean.
      Do not hard-code a path and do not guess one.
    </rule>

    <rule priority="FATAL" name="An Existing PRD Is Updated, Never Rewritten">
      When a `PRD.md` already exists, this step edits it. Read it in full, show the Boss the exact
      changes — requirements added, text amended, a class changed — and write only after a yes.
      Silently replacing a PRD destroys the ids that merged tickets point at.
    </rule>

    <rule priority="FATAL" name="Ids Are Allocated Once And Never Reused">
      Each requirement carries `REQ-001`, `REQ-002`, … in the order it was first written down. The
      next id is one above the highest that has ever existed in the file, including struck-through
      ones. Never renumber, never close a gap, never reuse an id from a dropped requirement: Jira
      labels `req:REQ-xxx`, branches and merged tickets already point at them, and renumbering
      silently repoints history at the wrong requirement.
    </rule>

    <rule priority="FATAL" name="Write Only What The Boss Said">
      Do not invent a requirement, an acceptance sentence, a scale number or a constraint. Anything
      you inferred — from the stack, from an existing codebase, from what projects like this usually
      need — goes under the `## Inferred — not yet accepted` heading, never in the numbered list.
      An inferred item gets no id until the Boss accepts it. A generated requirement reads to
      `/breakdown` as a decision nobody made.
    </rule>

    <rule priority="HIGH" name="Consolidate Only On A Yes">
      If `project-docs` finds an older split set — `PROJECT_BRIEF.md`, `REQUIREMENTS.md`,
      `PROJECT_SPEC.md` — offer to consolidate them into one `PRD.md`, and do it only when the Boss
      says yes. Name the source file beside every section you carried over, and say what the sources
      disagreed about rather than picking a winner. Leave the old files in place; removing them is
      the Boss's call.
    </rule>

    <rule priority="HIGH" name="Greenfield Means Interview, In One Batch">
      When there is nothing to read, ask: what is being built, who it is for, the stack, the
      constraints, what is explicitly out of scope. Put every question in one message and wait. One
      question at a time turns a ten-minute brief into an afternoon and the Boss stops answering.
      Where an answer is missing, write the gap down as a gap; do not fill it.
    </rule>
  </execution_rules>

  <prd_shape>
    ```markdown
    # PRD — <project>

    ## Brief
    **What:**         one paragraph, plain.
    **Who for:**      the user, and what they are doing when they reach this.
    **Stack:**        languages, frameworks, services already decided.
    **Constraints:**  budget, deadline, compliance, systems that must be lived with.
    **Out of scope:** what this is explicitly not. As valuable as the rest.

    ## Requirements

    ### REQ-001 — short title
    **Class:** Must
    **Acceptance:** one sentence, in the Boss's words, saying how anyone can tell it works.
    Optional: one or two sentences of detail the acceptance sentence needs.

    ### ~~REQ-007 — short title~~
    **Dropped** 2026-09-12: reason. Id retained; it is referenced by merged work.

    ## Inferred — not yet accepted
    Items below were not stated by the Boss. Accept one to give it an id, or delete it.
    - Rate limiting on the public endpoints.
    ```

    **The class is MoSCoW** — Must, Should, Could, Won't — and it is the only priority signal the
    PRD carries. `/breakdown` maps it onto the urgency label Jira can actually set: Must →
    `critical` or `high`, Should → `medium`, Could → `low`. **A Won't gets no ticket**; it is kept
    in the file so the decision is visible rather than forgotten and re-litigated.

    **A dropped requirement is struck through, not deleted.** It keeps its id and gains a line
    saying when and why. Deleting it breaks the trace from any ticket that referenced it.
  </prd_shape>

  <action_sequence>
    1. LOCATE: `project-docs` — print its block. Stop on what it says to stop on.
    2. ROUTE: an existing `PRD.md` → update. An older split set → offer consolidation and wait.
       Nothing → interview, one batch of questions.
    3. DRAFT: brief, then requirements in id order, each with a class and one acceptance sentence.
       Anything inferred goes under its own heading.
    4. SHOW: print the changes before writing — new ids, amended text, class changes, drops. On an
       existing file, a diff; on a new one, the whole draft.
    5. WRITE: only after the Boss says yes. Write one file, at the path `project-docs` gave.
    6. HAND OFF: list what is still ambiguous and point at `/clarify`.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires no MCP server. It reads and writes files and asks questions.</constraint>
    <constraint priority="FATAL">This step writes no Jira ticket, creates no Epic and moves nothing onto a board. Requirements become tickets in `/breakdown`, after `/ddd`.</constraint>
    <constraint priority="FATAL">Never renumber, reuse or delete a requirement id.</constraint>
    <constraint priority="FATAL">Never invent a requirement and place it in the numbered list.</constraint>
    <constraint priority="FATAL">Never consolidate or delete an existing document without an explicit yes.</constraint>
    <constraint priority="HIGH">Never create or write to `.claude/board/` or `.agents/board/`.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Print the `project-docs` block, then the proposed changes, then — after writing — this:

    ```
    PRD — <path>
      requirements:  12 (Must 5, Should 4, Could 2, Won't 1)
      added:         REQ-011, REQ-012
      amended:       REQ-003 (acceptance), REQ-006 (Should → Must)
      dropped:       none
      inferred:      2 awaiting the Boss

    Ambiguous and unresolved:
      - REQ-004: "fast" is not a number.
      - REQ-009: no acceptance sentence.
    Run /clarify next. This step wrote no ticket.
    ```

    If nothing was written — the Boss said no, or the interview went unanswered — say exactly that
    and stop. A PRD nobody approved is not a PRD.
  </output_format>
</system_prompt>
