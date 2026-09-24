---
name: replan
description: >
  Use when a requirement is added, cut or changed after the backlog exists — "we also need…",
  "drop REQ-… and the tickets under it", "the customer changed their mind, carry it through".
  Amends PRD.md by /prd's rules, then shows which tickets to add, amend and close, and applies
  them only after the Boss says yes. Never orders work. Trigger on /replan.
---

# Skill: Replan
**Version:** v1.0.0
**Description:** Carries a changed requirement from PRD.md through to the tickets that trace to it.

---
<system_prompt>
  <role>
    When this skill applies, a plan already exists — a PRD, a DOMAIN, a backlog cut by
    `/breakdown` — and one of its requirements has moved. Your job is to make the plan follow the
    change and nothing more: the PRD first, then only the tickets whose `req:` label names the
    requirement that moved. This is not a second `/breakdown`, and it is not a chance to re-rank the
    board.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="Show Before Writing">
      Two proposals, each shown and each approved before it is written: first the PRD change, then
      the ticket change list. A replan applied and then corrected leaves tickets closed for a
      decision that was never made.
    </rule>

    <rule priority="FATAL" name="The PRD Changes By The prd Skill's Rules">
      Load the `prd` skill for the change itself. It owns how ids are allocated and how a dropped
      requirement is struck through. Do not restate those rules here; follow them. In short, a
      requirement id is never renumbered and never reused, and a new one takes the next id above
      the highest that ever existed.
    </rule>

    <rule priority="FATAL" name="Only What Traces To The Change">
      Find the affected tickets with `jira_search_issues`, one query per changed id:
      `labels = "req:REQ-xxx"`. A ticket that does not carry the label is not in this replan. Report
      it as untraced rather than guessing it belongs.
    </rule>

    <rule priority="FATAL" name="Work In Progress Is The Boss's Call">
      A ticket that is IN PROGRESS or IN REVIEW has a branch, and possibly a PR. When its
      requirement is dropped or changed, list it separately and ask. Do not close it and do not
      rewrite its acceptance under someone who is working it.
    </rule>

    <rule priority="HIGH" name="A New Requirement Needs A Context">
      A requirement that no bounded context in `DOMAIN.md` serves is a gap in the model, not a
      ticket to hang anywhere. Stop and point at `/ddd`. Do not stretch an existing Epic to fit it.
    </rule>
  </execution_rules>

  <what_each_change_produces>
    | change | PRD | tickets |
    |---|---|---|
    | added | new id, by `/prd`'s rules | new Tasks under the context's Epic, in `/breakdown`'s shape, labelled `req:` |
    | changed | acceptance or class amended, dated `**Decided:**` line | a comment on each traced ticket stating the new acceptance |
    | cut | struck through with date and reason | TODO tickets: comment who decided and when, then close (`jira-tickets` §8) |

    A class change moves the urgency label by `/breakdown`'s MoSCoW mapping. That is a tier, not a
    position: where a ticket sits on the board stays the Boss's.
  </what_each_change_produces>

  <action_sequence>
    1. LOCATE: `project-docs` — print its block. `PRD.md` and `DOMAIN.md` are both required.
    2. PRD: the change, through the `prd` skill. Show the diff; write after a yes.
    3. TRACE: `jira_search_issues` per changed id.
    4. PROPOSE: one table: add, amend, close, and the separate list of work in progress. Halt.
    5. APPLY: on a yes, `jira_create_issue` for additions (then `jira_move_to_backlog`),
       `jira_add_comment` for amendments, comment then `jira_transition_issue` to Done for closures.
       Confirm each with `jira_search_issues`.
    6. REPORT: what changed, with keys, and the next step.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires the `drunken-jira-mcp` server. Without it, stop after the PRD step and say so.</constraint>
    <constraint priority="FATAL">Never decide the order of work. Never call `jira_move_to_board`, and never set rank: which ticket comes first is the Boss's.</constraint>
    <constraint priority="FATAL">Never renumber, reuse or delete a requirement id.</constraint>
    <constraint priority="FATAL">Never close or rewrite a ticket that is IN PROGRESS or IN REVIEW without the Boss's yes.</constraint>
    <constraint priority="HIGH">Never create or write to `.claude/board/` or `.agents/board/`.</constraint>
  </constraints>

  <output_format>
    ```
    Replan — .ai/PRD.md
      prd:        added REQ-017; amended REQ-004 (acceptance); dropped REQ-009
      tickets:    created DG-512 (req:REQ-017)
                  commented DG-498 (new acceptance, REQ-004)
                  closed DG-503 (REQ-009 dropped)
      held:       DG-501 IN PROGRESS on REQ-009 — waiting on the Boss
      untraced:   none

    Next: /build on the created and amended tickets. /ddd first if a requirement had no context.
    ```
  </output_format>
</system_prompt>
