# Contributing — Writing Skills & Agents

This guide is for anyone who wants to add a new skill or agent to the toolkit.

---

## Skills vs Agents — which do you need?

| You want to... | Build a... |
|---|---|
| Enforce a standard or workflow *during* a task (loaded via slash command) | **Skill** |
| Run a category of work *autonomously* in its own context window | **Agent** |

---

## Writing a New Skill

### 1. Create the file

```
skills/<category>/<skill-name>/SKILL.md
```

Choose an existing category (`architecture`, `backend`, `frontend`, `infrastructure`, `kanban`, `leadership`, `product`, `security`, `testing`, `workflow`) or create a new one if nothing fits.

### 2. Follow the canonical structure

Every `SKILL.md` must have these five sections in this order:

```
1. # Skill: <Title>
2. **Description:** — one-line summary
3. **Trigger/Keywords:** — slash command and keywords
4. ---
5. <system_prompt> block
```

See [`SKILL-annotated.md`](./SKILL-annotated.md) for a fully annotated example explaining every field.

### 3. Deploy

```bash
./scripts/sync_skills.sh
```

This copies your new skill to `~/.claude/skills/` where Claude Code can find it.

---

## Writing a New Agent

### 1. Create the file

```
agents/<agent-name>.md
```

### 2. Follow the canonical structure

```markdown
---
name: <kebab-case-name>
description: <one-line description of when to invoke this agent>
model: <claude model id>
tools: <comma-separated tool list>
---

<system_prompt>
  <role>...</role>
  <core_instructions>...</core_instructions>
  <constraints>...</constraints>
  <output_format>...</output_format>
</system_prompt>
```

**Model guidance:**
- Use `claude-opus-4-8` for orchestrators that make strategic decisions
- Use `claude-sonnet-4-6` for specialists that execute focused work

### 3. Deploy

```bash
./scripts/sync_agents.sh
```

---

## Rules for both skills and agents

- **English only** — all content, descriptions, constraints, and output formats
- **Never delete existing logic** when modifying a file — preserve all content unless told to remove it
- **No installation by AI** — never run sync scripts automatically; always remind the user to run them manually
