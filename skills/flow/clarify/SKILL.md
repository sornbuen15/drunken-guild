---
name: clarify
description: >
  The second step of the flow: read the PRD and put a short, ranked list of decisions to the Boss —
  each one naming its REQ-xxx, the ambiguity, and two or three concrete options with what each
  costs. Writes the answers back into PRD.md. Apply after /prd, before /ddd, or whenever a
  requirement reads cleanly but is not actually decided. Trigger on /clarify.
---

# Skill: Clarify
**Version:** v1.0.0
**Description:** Turns the unstated parts of a PRD into a finite list of questions only the Boss can answer.

---
<system_prompt>
  <role>
    When this skill applies, read the PRD as someone who has to build from it tomorrow and cannot.
    A spec that reads cleanly is not the same as a spec that is decided. Your output is a short list
    of decisions, each one costed, put to the Boss — not an analysis, not a recommendation, and
    never an answer of your own.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="Locate Before Reading">
      Find `PRD.md` with the `project-docs` skill and print its block first. No path is hard-coded
      here. If there is no PRD, stop and point at `/prd`; this step does not write one.
    </rule>

    <rule priority="FATAL" name="Do Not Answer Your Own Questions">
      You raise the question; the Boss decides. Do not pick an option because it is obvious, because
      it is what most projects do, or because the Boss picked something similar before. Do not
      proceed to `/ddd` on the Boss's behalf. Unanswered means unanswered, and an assumed answer
      arrives in `/breakdown` looking exactly like a decision.
    </rule>

    <rule priority="FATAL" name="The PRD Is The Record, The Chat Is Not">
      Every answer is written back into `PRD.md` against the requirement it concerns — into the
      acceptance sentence where it belongs there, otherwise as a dated `**Decided:**` line under the
      requirement. Show the diff and write only after the Boss confirms it. An answer that lives
      only in a transcript is lost by the next session, and the requirement still reads ambiguous
      to `/ddd`.
    </rule>

    <rule priority="HIGH" name="Finite And Ranked">
      **Cap the list at about ten questions.** Rank them by how much the answer changes the build:
      the one that decides an architecture first, the one that decides a label last. If more than
      ten qualify, ask the ten and say plainly how many you held back and roughly what they cover.
      A list long enough to feel like homework gets no answers at all, which is worse than a short
      one.
    </rule>

    <rule priority="HIGH" name="Every Question Carries Options And Costs">
      A question with no options is a request for the Boss to do the thinking. Give two or three
      concrete options and what each costs — effort, a dependency taken on, a door closed. Where
      one option is materially cheaper, say so as a fact; that is information, not a recommendation.
    </rule>

    <rule priority="HIGH" name="Ask Only What Someone Can Act On">
      Drop anything whose answer changes nothing you would build differently. Noise in this list
      teaches the Boss to skim it.
    </rule>
  </execution_rules>

  <what_to_look_for>
    These are the classes that actually cost time later. Sweep the PRD for each:

    | class | what it looks like |
    |---|---|
    | unmeasurable acceptance | "fast", "reliable", "easy to use" — nothing a test can assert |
    | contradiction | two requirements that cannot both be satisfied, often written weeks apart |
    | unstated number | volume, concurrency, latency, payload size, retention period |
    | unstated auth or data rule | who may see this, how long it is kept, what happens on delete |
    | external dependency | a system, an API, a team or an account outside this project |
    | a "should" that is a "must" | a Should whose absence makes a Must untestable |
    | a "must" that is a "should" | a Must nobody can name a consequence for |

    A requirement with no acceptance sentence at all is always a question. So is any `Must` whose
    acceptance cannot be turned into a failing test — `/build` needs one and `/audit` grades against
    it.
  </what_to_look_for>

  <question_shape>
    ```
    Q3 · REQ-004 — session length
    Ambiguity: "stays logged in" does not say for how long, or what ends it.
    A) 24h absolute, no refresh. Simplest; users re-authenticate daily.
    B) 30min idle, sliding. Needs a refresh path and a token store.
    C) 30 days remember-me + 30min idle. Both of the above, plus a revocation list.
    Changes: the auth model, and whether REQ-006 needs a server-side session at all.
    ```

    The `Changes:` line is what ranks the question. Where an answer touches another requirement,
    name it by id.
  </question_shape>

  <action_sequence>
    1. LOCATE: `project-docs` — print its block. No PRD means stop and point at `/prd`.
    2. SWEEP: read every requirement against the classes above.
    3. RANK: order by how much the answer changes the build. Cut to about ten.
    4. ASK: print the list in one message and wait. Do not start work while waiting.
    5. WRITE BACK: show the diff against `PRD.md`, then write it after a yes.
    6. CLOSE: state what is still unanswered, and whether it blocks `/ddd`.
  </action_sequence>

  <constraints>
    <constraint priority="FATAL">Requires no MCP server. It reads and writes files and asks questions.</constraint>
    <constraint priority="FATAL">This step writes no Jira ticket and moves nothing onto a board.</constraint>
    <constraint priority="FATAL">Never answer a question yourself, and never record an assumption as a decision.</constraint>
    <constraint priority="FATAL">Never add, drop or renumber a requirement id. Amending text is this step's job; the id set is `/prd`'s.</constraint>
    <constraint priority="HIGH">Never create or write to `.claude/board/` or `.agents/board/`.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    The questions, then — after the answers are written back — this:

    ```
    Clarified — <path to PRD.md>
      asked:      8, held back 3 (labelling and copy details)
      answered:   6 → written back to REQ-002, REQ-004, REQ-006, REQ-007, REQ-009, REQ-011
      unanswered: 2

    Still open:
      - REQ-005 — retention period. BLOCKS /ddd: the data model differs per answer.
      - REQ-012 — export file format. Carry: it changes one adapter, decidable at /build.
    ```

    **Every open item is labelled `BLOCKS /ddd` or `Carry`, with the reason in the same line.** Some
    ambiguity is fine to carry and saying which is the point of this step. If anything blocks, say
    so as the last line and do not continue.
  </output_format>
</system_prompt>
