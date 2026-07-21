---
title: Migrate Jira Sync Logic into MCP Server (Resolve Workflow Conflict)
priority: CRITICAL
assigned_to: "@principal-engineer"
---
# Security & Workflow Conflict
The kanban-board MCP server only writes locally. Other agents (like Mina) who only know MCP but do not have the custom `<jira_sync>` rule end up creating tasks that do not sync to Jira.
We need to bake the `jira_bridge.py` logic natively into the `kanban-board` MCP server so that any agent using the tool automatically pushes to Jira Cloud without needing external scripts.
