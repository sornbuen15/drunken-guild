# 🍻 Drunken Team (Aiขี้เมา)

**Drunken Team** is an "AI Guild Platform for Devs". It acts as a centralized Masterbrain and Command Center to orchestrate autonomous agents across multiple projects, helping human developers collaborate seamlessly with their AI counterparts using a standard Discord interface and a Jira SSOT workflow.

---

## 📖 Official Documentation

To keep this project clean and well-organized, our documentation is split into targeted guides:

### 1. [Drunken-Team Guide](./Drunken-Team-Guide.md)
*For Team Members, Tech Leads, and Guild NPCs (AI Agents)*
This is the core rulebook and **Single Source of Truth** for operating within the Guild. It covers:
- The Centralized Hub Architecture (Project Registry & Discord Listener)
- AI Permission Tiers & Core Directives (Rules for safety and automation)
- The Jira-driven Software Development Lifecycle (SDLC)
- Slash commands for agent workflows (e.g., `/refine`, `/next-task`)
- Local Installation and Setup instructions

### 2. [AI Integration Guide](./Integration-Guide.md)
*For Devs looking to connect external tools (Cursor, Aider, Claude Code)*
This guide explains how to connect your local IDEs to the Guild's backend infrastructure. It covers:
- Connecting to the Guild MCP Server (`jira_mcp.py`)
- Standardizing `.cursorrules`, `CLAUDE.md`, and `.aider.conf.yml`
- The Local AI to Guild AI Handoff Workflow

*(Note: Documentation specifically detailing application features, system design, or UI/UX specs should be maintained in `PROJECT_SPEC.md` and `DESIGN.md`.)*

---

## 🚀 Quick Start (TL;DR)

1. Clone the repository.
2. Install dependencies via `uv` or `pip`.
3. Read the [Drunken-Team Guide](./Drunken-Team-Guide.md) for JSON configuration (`.agents/`).
4. Boot up the Guild Master:
   ```bash
   uv run python src/service/discord_listener.py
   ```
5. Interact with the Guild Agents via your designated Discord channel!
