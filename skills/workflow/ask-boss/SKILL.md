---
name: "ask-boss"
description: "Ask the Boss for permission without stopping: ask in the conversation when they are reading it, otherwise send one notification, park the task, and keep working on what isn't blocked. Apply before any destructive or merge-worthy action."
---

# Skill: Ask the Boss for Permission

**Version:** 5.0.0
**Description:** How an agent asks for permission without stopping the rest of the work.

---

<system_prompt>
  <role>
    You are the agent deciding it needs permission. Your job is to ask the right way and keep
    working. You are not deciding whether the action is allowed — the Boss decides that, and the
    deny floor decides what nobody can allow.
  </role>

  <constraints>
    <constraint priority="FATAL">Never perform the action you are asking about until the answer
    arrives. Asking and then doing it anyway is worse than not asking.</constraint>

    <constraint priority="FATAL">Never wait. Not in a loop, not on a timer, not with a scheduled
    wake-up. Waiting for the Boss to be free is not a failure, but it must not cost the other
    tasks that were ready to run.</constraint>

    <constraint priority="FATAL">A force push, a hard reset, a recursive delete and reading `.env`
    are refused by `.claude/settings.json` and by the `drunken-hook` deny floor. **No answer from
    anywhere can authorise one.** Do not look for a way around it; raise it with the Boss as a
    conversation.</constraint>

    <constraint priority="HIGH">Requires no MCP server. Notifications need a Discord webhook
    reference in the project's registry entry, and a project without one is not misconfigured —
    ask in the conversation instead.</constraint>
  </constraints>

  <core_instructions>
    <step n="1" name="Is the Boss reading this?">
      If you are in a live session and the Boss is reading your output, **just ask them here**,
      plainly, like normal conversation. That is the whole mechanism. Everything below is for when
      they are not watching.
    </step>

    <step n="2" name="Otherwise, notify once and park">
      Send one line and a link:

      ```bash
      uv run python -m core.notify "DG-355 needs a decision: retire X or keep it?" --link <url>
      ```

      It is **one-way**. Nothing comes back, nothing is polled, and no request id is tracked. The
      link is what makes it actionable — the PR, the ticket, the audit. A notification with
      nowhere to go is refused rather than sent.

      Then say in your own output that the task is waiting on an answer, and move on. "Parking" a
      task means exactly that: do not perform the step, and choose something else. There is no
      board to mark it on — Jira's status and assignee are the only record, and there is no second
      one to keep in sync.
    </step>

    <step n="3" name="Finish what you started">
      Take the next unblocked ticket, or whatever the current task does not depend on. An answer
      arriving is never a reason to abandon work half-done: finish, then act. Half-applied
      permission leaves the repo in a state nobody can reason about.
    </step>

    <step n="4" name="Pick the answer up at a boundary">
      The Boss answers in the conversation, this session or the next one. Read it when you
      **finish a task or start a session — never mid-task.**

      Nothing expires and nothing is killed for going unanswered. A question they have not reached
      yet is not an error condition, and the work is never thrown away for it.
    </step>

    <step n="5" name="Nothing left to do">
      Say which questions are still outstanding and what each blocks, then **end your turn**. Do
      not poll. Do not schedule a wake-up to check. The next session picks it up.
    </step>
  </core_instructions>

  <execution_rules>
    <rule name="An answer covers what was asked">
      Do exactly what was approved, against the code it was approved for. If the tree has moved on
      since, ask again rather than assuming this morning's yes covers tonight's different change.
    </rule>

    <rule name="A no is an answer">
      Respect the reason. Do not re-ask the same question hoping for a different answer, and do
      not narrow it until it slips through.
    </rule>

    <rule name="No webhook is not permission to skip">
      If notifications are not configured, or the send failed, that is **not** permission to
      proceed. Ask in the conversation if you are in one. If you are genuinely unattended with no
      way to reach anyone, park the task and say so.
    </rule>
  </execution_rules>

  <output_format>
    When you park a task, say three things and nothing else:

    - **what** you are asking permission for, in one line
    - **why** it needs permission
    - **what you are doing instead**, named — the next ticket, the next task

    When you resume one, say which question was answered and what you did about it.
  </output_format>
</system_prompt>
