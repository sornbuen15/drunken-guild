# Session Checkpoint

This file acts as the short-term memory and context handoff between AI coding sessions.
**AIs must read this file at the start of a session and update it before ending their turn.**

## 1. Current Objective
- Briefly describe the current sprint goal or main feature being worked on.

## 2. Completed in Last Session
- Bullet points of what was achieved in the previous interaction.
- (e.g., Setup database connection, refactored Auth module).

## 3. Pending / Next Steps
- What needs to be done next?
- (e.g., Write tests for Auth module, fix the caching bug in Jira bridge).

## 4. Known Issues & Context
- Any blockers, edge cases discovered, or context the next AI needs to know to avoid repeating mistakes.
- (e.g., "The API is returning 403 because we need to pass a specific header", or "Do not touch file X because it breaks Y").
