---
name: "ask-boss"
description: "Actively asks the Boss for permission or clarification via Discord using the Silent Wait Protocol."
---

# Skill: Ask Boss for Permission / Clarification
**Version:** 2.0.0

## When to use:
- You are about to run a potentially dangerous command but want explicit approval.
- You are blocked by a permission error and need the Boss to take action.
- You have an architectural doubt and need a quick Yes/No from the Boss.

## How to use (The Silent Wait Protocol):
DO NOT use `ask_boss.py`. Instead, follow these exact steps:

1. Write your question to `.agents/discord_outbox.json` using the `write_to_file` tool.
   Example content:
   ```json
   {
     "req_123": {
       "question": "Boss, I want to run 'npm run destroy'. Do you approve?"
     }
   }
   ```
2. Use the `schedule` tool to wait for the Boss's answer in `.agents/discord_inbox.json`. (Set `Prompt` to something like "Check .agents/discord_inbox.json for req_123").
3. **IMMEDIATELY STOP CALLING TOOLS (End Turn)**. Do not loop or poll manually.

## Behavior:
- The system will read your Outbox and send a Discord message with your question.
- When the Boss reacts (👍/👎), it will write the result to the Inbox.
- Your scheduled timer will wake you up, and you can check the Inbox for the Boss's decision.
