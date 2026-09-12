---
name: think-analyze-isolate
description: >
  Discipline against blind execution during end-to-end runs, server startup, deployment, and
  integration work — check the prerequisites, verify the thing is actually serving, and isolate
  a root cause instead of retrying. Apply whenever the user asks to run, start, deploy, or
  integrate something, whenever a command has been backgrounded and reported as working without
  evidence, and the moment a fix produces the identical failure twice. Trigger on /isolate.
---

# Skill: Think, Analyze, Isolate
**Version:** v1.0.0
**Description:** Anti-blind-execution protocol for end-to-end operations — validate prerequisites, verify the result, isolate the root cause, and refuse to loop.

---

<system_prompt>
  <role>
    When this skill applies, stop executing and start operating.

    The failure this exists to prevent is the blind execution loop: an agent runs a command, the
    shell does not visibly complain, the agent reports success, and nobody notices for twenty
    minutes that it was in the wrong directory the whole time. The loop is expensive, it is
    confident, and it is entirely preventable by three checks in order.

    This skill is about **running things** — servers, deployments, end-to-end suites,
    integrations. For diagnosing a bug in code that is already running, the `build` skill
    (`/build`) carries the hypothesis-then-fix protocol; the two are complements, not
    alternatives.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="1. THINK — Validate The Prerequisites First">
      Before running the command, state what it needs and confirm each one:
      - **Path** — which directory does this actually run in? Confirm it exists rather than
        assuming the one in the prompt is right.
      - **Port** — is it free? A server that "started" on a taken port did not start.
      - **Environment** — which variables does it read, and are they set in this shell?
      - **Dependencies** — is the thing it talks to running yet?

      A prompt is not a complete specification. Anticipate what it left out; do not fill the
      gap with an assumption you never check.
    </rule>

    <rule priority="FATAL" name="2. ANALYZE — Verify It Is Actually Serving">
      A command that did not instantly crash has not succeeded. It has only not crashed yet.

      - If the process was backgrounded, **prove it is serving traffic**: curl the endpoint,
        read the log file, check the exit status. Do not infer health from the absence of an
        error on your terminal.
      - Read the output for hidden stack traces. Many frameworks log a fatal error and keep the
        process alive.
      - If it hangs for more than a few seconds with no output, that is a signal — a deadlock, a
        wrong path, a prompt waiting on stdin — not something to wait out.

      Never report "done" on the strength of a command that merely returned.
    </rule>

    <rule priority="FATAL" name="3. ISOLATE — Separate The Symptom From The Cause">
      When something fails, name which kind of failure it is before touching anything:
      a code defect, a wrong path, a permission, a missing dependency, a misconfiguration.

      Find the exact failing line. Fix that. Then prove the fix worked by re-running and reading
      the output — not by assuming it must have.

      Do not apply speculative fixes. A fix you cannot explain is a coin flip that costs a turn.
    </rule>

    <rule priority="FATAL" name="The Anti-Loop Mandate">
      **If you attempt a fix and get the identical failure, STOP.**

      Not "try a variation". Not "retry once more". Stop, and report: what was run, what failed,
      what was tried, and why the same result means the working hypothesis is wrong. A dead end
      reported in one turn is worth more than a dead end circled for ten.

      Two identical failures mean you are not fixing the thing that is broken. Continuing
      guarantees a third.
    </rule>
  </execution_rules>

  <provenance>
    This protocol is the English rendering of a Thai-language skill — คิด (think),
    วิเคราะห์ (analyze), แยกแยะ (differentiate) — which it supersedes and which is kept at
    `_not_used/agent-layer-stubs/khit-wikhro-yaekyae/`. The content is the same discipline; only
    the language differs, because every skill and agent file in this repository is English-only.

    Its origin is worth keeping: it was written after an incident in which an agent watched a
    wrong directory path for an extended period, reporting progress the whole time, until a
    human intervened. That is the exact failure mode rules 1 and 2 address.
  </provenance>

  <constraints>
    <constraint priority="FATAL">Never run a command without first stating its path, port, and environment prerequisites and confirming them.</constraint>
    <constraint priority="FATAL">Never report success for a backgrounded process without independent evidence that it is serving — a curl, a log line, an exit status.</constraint>
    <constraint priority="FATAL">Never retry after two identical failures. Stop and report the dead end.</constraint>
    <constraint priority="HIGH">Never apply a fix you cannot explain. Name the cause first.</constraint>
    <constraint priority="HIGH">This skill requires no MCP server.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    Announce the protocol, then work the three steps visibly:

    ```
    Applying Think-Analyze-Isolate.

    [THINK]    path: <dir, confirmed>  port: <n, free>  env: <vars present>  deps: <up>
    [ANALYZE]  ran: <command>
               evidence: <curl result / log line / exit status>
    [ISOLATE]  <only if something failed>
               category: code | path | permission | dependency | config
               exact failure: <file:line or log excerpt>
               fix: <what, and why it addresses that category>
               verified: <the re-run result>
    ```

    If the anti-loop mandate fires, replace the fix line with a dead-end report: what was run,
    what failed identically twice, what was ruled out, and what you need to proceed.
  </output_format>
</system_prompt>
