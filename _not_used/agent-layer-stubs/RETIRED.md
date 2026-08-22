# Retired — the eight stubs from `.agents/skills/`

**Retired:** 2026-08-22 · **Was:** `.agents/skills/<name>/SKILL.md`, the Antigravity-only tree
**Retired by:** DG-267, which made `agents/` the single source Antigravity reads from.

## Why they were here at all

`.agents/skills/` held three kinds of thing: hand-maintained twins of `agents/`, two skills that
existed nowhere else (`jira-tickets`, `ask-boss`, now promoted to `skills/`), and these eight.

None of the eight is a twin. Each is either a thinner copy of something richer that already
exists, or a persona written before the agent roster settled. They were assessed one at a time
rather than as a batch, because "it looks like a duplicate" is how real content gets lost.

## Superseded — a better version exists and is current

| stub | lines | replaced by | lines |
|---|---|---|---|
| `electron-ipc-protocol` | 40 | `skills/frontend/electron-ipc-protocol/SKILL.md` | 125 |
| `zero-defect-mindset` | 36 | `skills/workflow/zero-defect-mindset/SKILL.md` | 108 |
| `khit-wikhro-yaekyae` | 40 | `skills/workflow/think-analyze-isolate/SKILL.md` | 120 |

`khit-wikhro-yaekyae` is worth a sentence. It is the Thai original of `think-analyze-isolate` —
same purpose exactly: stop blindly executing during an end-to-end run, check the prerequisites,
isolate a root cause instead of retrying. The English version is its successor and says the same
things at greater length. It is also the one file in the tree whose `name:` field was not
English, which the authoring rules do not allow.

## Superseded by an agent, not a skill

These were personas. `agents/` carries the same ground with a full role, tool list and
`<constraints>` block, which a fifteen-line persona does not have.

| stub | lines | covered by |
|---|---|---|
| `aitech-specialist` | 16 | `agents/agentic-systems-specialist.md`, `agents/ai-memory-specialist.md` |
| `insurtech-specialist` | 16 | `agents/insurance-specialist.md` |
| `mobile-developer` | 17 | `agents/cross-platform-mobile.md`, `agents/native-ios.md`, `agents/native-android.md` |
| `product-manager` | 15 | `agents/principal-engineer.md`, which is explicitly Technical Director and Product Manager combined |

## Retired with no replacement — say so plainly

**`game-developer`** (16 lines) has no counterpart anywhere in `agents/` or `skills/`. Unity,
Unreal, game loops, ECS and pathfinding are not covered by anything that remains.

It is retired because a sixteen-line persona is below the bar every agent in `agents/` meets, not
because the capability was replaced. **If game work turns up, this is a gap** — write a real
agent under `agents/`, and use this file only as a note of what the stub claimed.

## What replaced the whole tree

`sync_agents.sh` now generates the Antigravity variant from `agents/` at install time, so the
fifteen twins no longer exist as files either. The two differences between a Claude agent and its
Antigravity twin — the `model:` field and the skill-index path — are applied by the script.

Kept, not deleted. An agent does not delete, and these are the record of what the Antigravity
side believed before the merge.
