---
name: "ask-boss"
description: "Actively asks the Boss for permission or clarification via Discord, blocking execution until the Boss reacts with 👍 (approve) or 👎 (reject)."
---

# Skill: Ask Boss for Permission / Clarification
**Version:** 1.0.0

## When to use:
- You are about to run a potentially dangerous command but want explicit approval that isn't covered by the system UI.
- You are blocked by a permission error and need the Boss to take action.
- You have an architectural doubt and need a quick Yes/No from the Boss.

## How to use:
Run the `scripts/ask_boss.py` script via `run_command`:
```bash
python scripts/ask_boss.py "Boss, I want to run 'npm run destroy'. Do you approve?"
```

## Behavior:
- The script will send a Discord message with your question and add 👍 and 👎 reactions.
- The script will **block execution** and wait.
- If the Boss clicks 👍, the script exits with code `0`. You may proceed.
- If the Boss clicks 👎, the script exits with code `1`. You must abort the action.

## Rules:
- Do not use this for every tiny file permission if `run_command` can handle it naturally.
- Use this when working in the Terminal and you need the Boss's attention immediately on Discord.
