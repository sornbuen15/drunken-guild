# Guild Headquarters Architecture (Centralized Hub Model)

## Overview
Drunken-Team acts as the "Guild Headquarters", serving as the Masterbrain and Command Center for all autonomous agents across multiple projects (such as BETA, SHIELD, and Drunken-Team itself). This architecture ensures seamless, multi-project context switching and robust multi-agent swarm orchestration.

## Core Components

### 1. Project Registry (`src/drunken_team/core/registry.py`)
The single source of truth for cross-project location mappings.
- **Storage:** `.agents/projects.json`
- **Security:** Uses absolute file paths mapped to securely verified Project IDs to prevent directory traversal and scope injection.
- **Purpose:** Enables the central orchestrator to instantly lookup and jump into any registered project directory.

### 2. The Discord Guild Master (`src/drunken_team/services/discord_listener.py`)
The primary natural-language frontend connecting The Boss to the Agent Swarm.
- **Mina (The AI Hostess):** Acts as the smart router. Mina's prompt dynamically loads the `ProjectRegistry` list.
- **Context Routing:** When The Boss asks to "fix a bug in BETA", Mina automatically detects the project context and injects the `target_project` ID into the payload.
- **Dynamic Subprocess Spawning:** The dispatcher fetches the project's absolute path from the registry and sets it as the Current Working Directory (`cwd`) for the agent execution. Thus, agents wake up completely localized within the correct project's environment and Jira configurations.

### 3. The Dashboard Transceiver (`src/drunken_team/routes/serve_dashboard.py`)
A fast, lightweight web interface for the Command Center.
- **Registry Merging:** Dynamically loads active sessions and merges them with the robust `ProjectRegistry`.
- **Background Execution:** Allows agents to run silently in the background while streaming progress back to the Boss.

## Workflow

1. **Intake:** The Boss interacts via Discord or the Web Dashboard.
2. **Contextualize (คิด):** The system router (Mina) identifies the intent, the required specialized agents, and the target project workspace.
3. **Dispatch:** The router commands `agy` to spawn the target agents, explicitly injecting the project `cwd`.
4. **Execution & Feedback:** The spawned agents work locally on the target codebase and report back via the Walkie-Talkie interface.
