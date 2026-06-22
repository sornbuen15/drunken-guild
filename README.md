# Drunken AGY - Ultimate Antigravity Extension Suite
*Brought to you by Drunken Programmer*

Drunken AGY is a collection of lightweight, robust, and token-optimized utility tools and custom integrations designed to supercharge your experience with **Google Antigravity** (or other agentic AI systems). 

Instead of dealing with massive payloads or complex setups, this suite brings developer-focused workflows, interactive approvals, real-time visualizers, and third-party platform bridges with zero overhead.

---

## Features

1. **Tavern Dashboard Visualizer** (`dashboard/`):
   A premium, medieval-themed visual dashboard of "Drunken AGY Inn". See all your specialized agents sitting in the tavern. Toggle their status between **Work Mode** (sitting focused, coding) and **Rest Mode** (swaying drunk, drinking ale, telling funny programming stories) with an interactive terminal interface!

2. **Workspace Customization Syncing** (`sync_customizations.py`):
   Easily synchronize custom skills and specialized agent profiles to your local projects (`.agents/`) or globally (`~/.gemini/config/`).

3. **Discord Integration Suite**:
   * **Discord Agent Listener** (`discord_listener.py`): Run `agy` tasks asynchronously directly from a designated Discord channel.
   * **Interactive Boss Approvals** (`ask_boss.py`): Implement human-in-the-loop approvals. Let the agent prompt "the Boss" on Discord for a 👍/👎 reaction before performing critical operations.

4. **Jira Cloud Integration Bridge** (`jira_bridge.py`):
   * **Token-Optimized Queries:** Minimizes massive Jira REST payloads (50KB+) down to essential JSON (<0.5KB), saving up to **95% of Context Token space**.
   * Manage tasks, query backlogs, and transition issues without token bloat.

---

## Folder Structure

```text
drunken-agy/
├── README.md               # User guide & Setup documentation
├── .gitignore              # Out-of-the-box repository security configuration
├── agents/                 # Packaged global/workspace specialized agent profiles
│   ├── AGENTS.md           # Global/Workspace pipeline rules
│   └── *.md                # Specialized role definitions
├── skills/                 # Packaged global/workspace custom skills
│   ├── INDEX.md            # Skills catalog index
│   └── */SKILL.md          # Skill configuration files
├── dashboard/              # Tavern state visualizer interface
│   ├── index.html          # Dashboard page
│   ├── style.css           # Curated CSS styling & state animations
│   ├── app.js              # State engine & agent dialogue generator
│   └── tavern_bg.jpg       # Pixel art cozy tavern background
└── scripts/
    ├── sync_customizations.py # Installer/updater synchronization script
    ├── serve_dashboard.py     # Local web server runner for the Tavern Dashboard
    ├── discord_listener.py    # Discord-to-Agent command gateway
    ├── ask_boss.py            # Human-in-the-loop Discord approval script
    └── jira_bridge.py         # JIRA API bridge script (zero dependencies)
```

---

## 1. Tavern Dashboard Visualizer

Step inside the "Drunken AGY Inn" to visualize and interact with your agent squad.

### Start the Dashboard Server:
Run the server launcher in your terminal:
```bash
python3 /path/to/drunken-agy/scripts/serve_dashboard.py
```
This automatically starts a local web server at `http://localhost:8080` and opens the dashboard in your default browser.

### Interactions:
* **Agent Nodes:** Click on any agent (e.g., Wizard for Principal Engineer, Ninja for Security Engineer) to inspect their details.
* **Work Mode (นั่งทำงาน):** Agent glows cyan, enters a focus animation, and outputs professional, technical logs or answers.
* **Rest Mode (ไอ้ขี้เมา):** Agent sways, drinks, and responds with humorous, incoherent programming stories.
* **Tavern Bell:** Ring the bell to put all agents to work, or send everyone to the bar!
* **Agent Console:** Send prompts to the selected agent and see how they reply depending on their level of intoxication.

---

## 2. Workspace Customization Syncing (Install/Update)

Use the sync script to deploy or update custom skills and agent configurations.

### Make Scripts Executable:
```bash
chmod +x /path/to/drunken-agy/scripts/*.py
```

### Install/Update Locally in a Workspace (`.agents/`):
```bash
python3 /path/to/drunken-agy/scripts/sync_customizations.py --workspace
```
This automatically updates existing skills/agents or installs new ones to the workspace's `.agents/` directory.

### Install/Update Globally (`~/.gemini/config/`):
```bash
python3 /path/to/drunken-agy/scripts/sync_customizations.py --global
```

---

## 3. Discord Integration Suite

Bring human-in-the-loop interactions and remote task execution to your agent workflows via Discord.

### Configuration (`discord_config.json`)
Create a configuration file at `.agents/discord_config.json` inside your workspace root:
```json
{
  "bot_token": "YOUR_DISCORD_BOT_TOKEN",
  "channel_id": 123456789012345678
}
```

*Note: Alternatively, you can set the environment variables `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` in your terminal session.*

---

### Feature A: Discord Agent Listener (`discord_listener.py`)
This script listens to a specific Discord channel, executes any typed command using the `agy` CLI, and reports the status back to Discord.

#### Running the Listener:
```bash
python3 /path/to/drunken-agy/scripts/discord_listener.py
```

#### How to Use in Discord:
* **Run any agy command:** Simply type the command or flags (e.g., `models`, `help`, or `--print "Refactor codebase"`). The bot will execute it.
* **Ask the Agent directly:** Type any prompt in the channel, and the listener will wrap it automatically in `agy --print "<prompt>"` to execute the task.
* **Get Raw logs:** Type `!detail` in the channel to fetch the unfiltered execution log file (`agy_discord_raw.log`).

---

### Feature B: Interactive Boss Approvals (`ask_boss.py`)
Use this script in your agent workflows to halt execution and seek approval from the "Boss" (Guild Owner) on Discord before performing dangerous commands (e.g., deploying, database migrations, deleting resources).

#### Running the script:
```bash
python3 /path/to/drunken-agy/scripts/ask_boss.py "Do you approve deploying to production?"
```

#### How it works:
1. The script sends the question to the Discord channel and attaches 👍 and 👎 reactions.
2. It blocks execution and waits for the server/guild owner to react.
3. If approved (👍), the script exits with `0` (Success).
4. If rejected (👎), the script exits with `1` (Failure).

---

## 4. Jira Cloud Integration Bridge

Place a configuration file at `.agents/jira_config.json` inside your workspace:
```json
{
  "project_key": "YOUR_JIRA_PROJECT_KEY",
  "jira_url": "https://your-company.atlassian.net",
  "jira_email": "developer@company.com"
}
```

Provide the API token via the environment variable:
```bash
export JIRA_TOKEN="your-jira-api-token"
```

### Usage:
```bash
# Retrieve To Do items
python3 /path/to/drunken-agy/scripts/jira_bridge.py get-todo

# Transition an issue to a target state
python3 /path/to/drunken-agy/scripts/jira_bridge.py transition PROJ-101 "In Progress"

# Create a new task in the project
python3 /path/to/drunken-agy/scripts/jira_bridge.py create "New Task Summary" "Task Description Details"
```

---

## 🧭 Setup & Task Tracking: Jira Cloud vs. Local Kanban Board

This suite supports two workflows for task management and execution orchestration. Depending on your team's workflow and connectivity, you can choose one or combine both:

### Option A: Local Kanban Board (Kanban MCP) — *Offline & Local-Only*
If you prefer a clean, private, offline-first workflow, you can manage your tasks directly on your local machine using the **Kanban MCP Server**.
* **How it works:** It stores tasks as simple Markdown files inside the `.agents/board/` directory, divided into lanes (`todo`, `doing`, `done`).
* **Why use it:** 
  * **Completely local & fast:** No external API tokens or internet connections are required.
  * **AI Orchestration Scaffold:** Perfect for when you want the AI to break down a large prompt into small technical steps and track its own progress without cluttering the team's shared project tracker.
* **Setup:** Ensure the `kanban-board` MCP server is registered in your client configuration. The AI will automatically discover and use the `board_*` tools to orchestrate and track its own workflow.

### Option B: Jira Cloud Bridge — *Shared Team Collaboration*
If you work within a team that uses Jira Cloud, you can use the **Jira Cloud Bridge** (`jira_bridge.py`) or the `@modelcontextprotocol/server-jira` MCP server.
* **How it works:** It communicates directly with your Atlassian Jira Cloud project instance via REST APIs.
* **Why use it:** 
  * **Single Source of Truth:** Integrates with the official project tracker so your team can see status updates, assignments, and ticket creation in real-time.
  * **Zero-Overhead Parsing:** The bridge script automatically filters down large, token-heavy Jira payloads (often 50KB+) into minimal JSON (<0.5KB), saving up to **95% of LLM Context Tokens**.
* **Setup:** Configure `.agents/jira_config.json` and set your `JIRA_TOKEN` environment variable.

