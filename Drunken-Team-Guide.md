# 🍻 Drunken Team: The Ultimate AI Guild Guide

This guide serves as the **Single Source of Truth** for both Developers (Devs) and AI Agents within the project (Guild NPCs). It consolidates working rules, architectural structure, Permission Tiers, and all Workflows into one place.

*(Note: This document is Meta-Documentation explaining "how to work" in the Guild. For application feature specifications or System Design, please refer to `PROJECT_SPEC.md` and `DESIGN.md`)*

---

## 🏗️ 1. Architecture: The Centralized Hub Model
Drunken-Team (or **"Drunken AI"**) acts as the "Guild Headquarters" or main command center for all Agents.

### 1.1 Core Components
* **Project Registry (`src/core/registry.py`):**
  The central repository (Single Source of Truth) referencing the locations of other projects, enabling AI to seamlessly jump across and manage multiple projects without getting lost.
* **The Discord Guild Master (`src/service/discord_listener.py`):**
  The frontline (Frontend) that receives natural language commands from the Boss. It features **Mina (The AI Hostess)** acting as a Router to extract intent and open Subprocesses to spawn Agents into the correct project.
* **The Dashboard Transceiver (`src/route/serve_dashboard.py`):**
  A JRPG-tavern-themed GUI for humans to monitor the status of the Guild and actively running Agents.

---

## 🛡️ 2. AI Core Directives: Permission Tiers
To achieve Zero Friction Automation, the AI must strictly adhere to the Permission Tiers:

* **🟢 Tier 0: Zero Friction (Execute Immediately)**
  - Read/Write code within the project freely.
  - Run Python scripts via `uv run` (Do not use raw `python` to avoid messing with the OS environment).
  - NEVER trigger the Global Keychain (1Password); environment isolation is mandatory.
* **🟡 Tier 1: OS / App Consent (Ask Once)**
  - Before accessing cameras/microphones/special folders, the AI must warn the human that an OS Pop-up will appear.
* **🟠 Tier 2: Team Protocol (Destructive Actions)**
  - Destructive commands (`rm -rf`, `drop db`) **MUST NOT be executed immediately**.
  - Must be listed in a Markdown table and passed to the `ask_boss.py` script to wait for the Boss to react with 👍 / 👎 on Discord.
* **🔴 Tier 3: OS Elevation (Strictly Forbidden)**
  - The `sudo` command is strictly forbidden for AI. AI should write a separate script for the human to execute manually.

---

## 🗺️ 3. Software Development Workflow (SDLC)
We employ an advanced Agentic SDLC, relying on two SSOT points:

### 3.1 Task Management (Jira is SSOT)
- All tasks (Intake, Refinement) MUST flow exclusively through the Jira Board (Backlog -> To Do -> In Progress -> Done).
- Do not use plain Markdown files to store Tasks.
- AI must always use `scripts/jira_bridge.py` to fetch and update tasks.

### 3.2 Documentation (Git is SSOT)
- Technical documents must be written as Markdown in the Git Repo (Docs-as-Code).
- Once merged into `main`, use `/confluence-sync` to push documents to Confluence.

### 3.3 Git Protocol & PR Gates
1. Always create a Feature Branch (never push directly to `main`).
2. When finished, open a Pull Request (PR).
3. **Merge Authorization:** AI can merge code ONLY IF it calls `ask_boss.py` to request permission from the Boss via Discord and receives a 👍!

---

## 🚀 4. How to Execute the Workflow (Commands)
For Devs and Tech Leads, these are the primary commands to issue to Agents:
- `/refine`: Instruct the AI to filter the Backlog and prepare tasks into To Do.
- `/next-task`: Instruct the AI to pick the next task from To Do and assess it (Execution Plan) before writing code.
- `/audit`: Review Code Health, Technical Debt, and Security.
- `/confluence-sync`: Sync `.md` documents directly to Confluence.

---

## 💻 5. Installation & Setup
1. **Pre-requisites:** Python 3.8+, `uv` (Package Manager), and Git.
2. **Setup Env:** Copy `sandbox.env.template` (if available) to `.env` and configure Discord Token / Jira Token.
3. **Running the Guild:**
   - Run the Discord Bot: `uv run python src/service/discord_listener.py`
   - Run the Dashboard: Open `dashboard/index.html` to view status.
