# Drunken AGY - Ultimate (Drunken) Antigravity Extension Suite
*Brought to you by Drunken Programmer*

Grab a pint, pull up a sturdy wooden stool, and welcome to **Drunken AGY**! This is the ultimate collection of lightweight, token-optimized, and tavern-tested utilities designed to supercharge your experience with **Google Antigravity** (and other agentic AI systems). 

Instead of dealing with bloated payloads or sober, boring setups, this suite brings developer-focused workflows, interactive boss approvals, a real-time pixelated tavern visualizer, and lightweight third-party integrations with zero hangover.


## 🚀 Installation & Quick Start

Drunken AGY is packaged as a global Python CLI tool. Install it once locally to make its commands accessible from anywhere in your terminal:

```bash
cd /path/to/drunken-agy
pip install -e .
```

This registers the main command utilities in your `$PATH`:
- **`drunken-register [path]`**: Register a project path, create `.agents/` folders, initialize `ANTIGRAVITY.md` router rules, and fetch/store credentials (supporting 1Password CLI biometrics or safe local global configurations).
- **`drunken-dashboard [port]`**: Launch the retroactive retro Tavern JRPG dashboard visualizer (defaults to port `8081`). If the port is already occupied, it opens the existing link automatically.
- **`drunken-listen`**: Starts the Discord gateway transceiver to listen for task queries and interact with agents via **Mina (ผู้ดูแลโรงเตี๊ยม)**.

### 🛎️ Registering a Project

To initialize and setup Drunken AGY for any project:
1. Open your terminal and `cd` to the target project directory.
2. Run the register command:
   ```bash
   drunken-register
   ```
3. The command will:
   - Ensure the `.agents/` folder is present.
   - Generate `ANTIGRAVITY.md` router rules if missing.
   - Detect 1Password CLI (`op`) and prompt for biometrics (Touch ID / Passkey) to fetch tokens.
   - **No 1Password Fallback:** If 1Password is missing, it will prompt you for consent to store credentials in the global configuration folder (`~/.gemini/config/jira_config.json`) instead. If accepted, you can input JIRA credentials manually.
   - Prompt you for the Discord Channel ID.
   - Write `.env` and add it to `.gitignore`.
   - Register the project inside the Tavern Dashboard registry (`~/.gemini/config/projects/`).

---

## 🍻 Features of the Inn


1.  **Tavern Dashboard Visualizer** (`dashboard/`):
    Step inside the **Drunken AGY Inn**—a cozy retro visual dashboard where all your specialized developer agents hang out. Ring the tavern bell to switch them from **Work Mode** (glowing cyan, writing strict type-safe code) to **Rest Mode** (getting completely hammered on virtual ale, swaying, and yelling hilarious programming rants) via an interactive console!

2.  **Workspace Customization Syncing** (`sync_customizations.py`):
    Pour your customized skills and specialized agent profiles directly into your local projects (`.agents/`) or dump them globally (`~/.gemini/config/`) without spilling a single drop.

3.  **Discord Integration (The Gossip Gateway)**:
    *   **Discord Agent Listener** (`discord_listener.py`): Run async `agy` tasks directly from your Discord guild.
    *   **Interactive Boss Approvals** (`ask_boss.py`): Don't burn down the server! Let the agent prompt "the Boss" (Guild Owner) on Discord for a 👍/👎 reaction before running dangerous database migrations.

4.  **Jira Cloud Bridge (Token Saving Lager)** (`jira_bridge.py`):
    *   **Token-Optimized Queries:** Waters down massive, bloated Jira JSON payloads (50KB+) into a clean shot (<0.5KB) of pure task data. Saves up to **95% of LLM Context Tokens**, keeping your API bills cheap enough to buy another round!

---

## 🗺️ Tavern Blueprint (Folder Structure)

```text
drunken-agy/
├── README.md               # The Tavern Guidebook & Quest board
├── LICENSE                 # MIT License (Do whatever you want, but don't blame the bartender)
├── CODE_OF_CONDUCT.md      # Rules to keep the tavern safe and free of toxic trolls
├── CONTRIBUTING.md         # Guide on how to pour code contributions into our kegs
├── SECURITY.md             # Security policy (Report leaks privately to the landlord)
├── agents/                 # Customized specialized agent profiles (guild characters)
│   ├── AGENTS.md           # The Guild laws and pipeline protocols
│   └── *.md                # Agent characters sheets
├── skills/                 # Skills catalog (learned wizard spells)
│   ├── INDEX.md            # Spells catalog index
│   └── */SKILL.md          # Domain-specific skill configurations
├── dashboard/              # The Drunken AGY Inn frontend portal
│   ├── index.html          # Web portal interface
│   ├── style.css           # Curated JRPG styling & swaying animations
│   ├── app.js              # Roster database & agent dialogue generator
│   └── tavern_bg.jpg       # Pixel art tavern view
└── scripts/
    ├── sync_customizations.py # Syncs your local skills/agents to the global guild config
    ├── serve_dashboard.py     # Local web server runner (starts the tavern fire)
    ├── discord_listener.py    # Discord transceiver gateway
    ├── ask_boss.py            # blocks execution for boss reactions
    └── jira_bridge.py         # Zero-dependency Jira API optimizer
```

---

## 🎮 1. Tavern Dashboard Visualizer

Step inside the "Drunken AGY Inn" to interact with your developer squad.

### Start the Tavern Server:
Light the hearth by running the server launcher:
```bash
python3 scripts/serve_dashboard.py
```
This starts the local web server at `http://localhost:8080` and opens the tavern in your browser automatically.

### Tavern Interactions:
*   **Specialist Nodes:** Click on any agent (e.g., Archmage for Principal Engineer, Rogue for Security Engineer, Ranger for QA) to view their character sheet.
*   **Work Mode (ทำงาน):** The agent glows cyan, enters a focus animation, and outputs professional, technical logs or engineering code.
*   **Rest Mode (ไอ้ขี้เมา):** The agent sways, drinks ale, and responds with humorous, incoherent programming rants.
*   **Tavern Bell:** Ring the bell to put all agents to work, or send everyone to the bar!
*   **Interactive Console:** Type messages to the active agent to see how they respond depending on their level of intoxication.

---

## 📦 2. Customization Syncing (Pouring Configs)

Deploy or update custom skills and agent characters to your system.

### Make the Scripts Executable:
```bash
chmod +x scripts/*.py
```

### Deploy to Local Workspace (`.agents/`):
```bash
python3 scripts/sync_customizations.py --workspace
```
Deploys and updates configurations for your local project sandbox.

### Deploy Globally (`~/.gemini/config/`):
```bash
python3 scripts/sync_customizations.py --global
```
Installs the agents and skills globally for any Antigravity workspace to use.

---

## 💬 3. Discord Integration Suite

Bring human-in-the-loop approvals and remote task execution to your tavern.

### Configuration (`discord_config.json`)
Place your bot credentials at `.agents/discord_config.json` inside your project root:
```json
{
  "bot_token": "YOUR_DISCORD_BOT_TOKEN",
  "channel_id": 123456789012345678
}
```
*Note: You can also set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` environment variables instead.*

---

### Feature A: Discord Agent Listener (`discord_listener.py`)
This script listens to your Discord channel, executes user commands in the backroom using the `agy` CLI, and yells back the results.

#### Running the Listener:
```bash
python3 scripts/discord_listener.py
```

#### Discord Chat Commands:
*   **Run Commands:** Simply type any command or flag (e.g. `models`, `help`, or `--print "Refactor authentication"`). The bot will execute it.
*   **Chat Mode:** Type any prompt in the channel; the bot wraps it in `agy --print "<prompt>"` automatically to run it.
*   **Get Tavern Logs:** Type `!detail` to retrieve the raw execution logs (`agy_discord_raw.log`).

---

### Feature B: Interactive Boss Approvals (`ask_boss.py`)
Add this script to your automated workflows to pause execution and seek validation from the "Boss" (Server/Guild Owner) before running dangerous commands (e.g. deleting tables, deploying).

#### Running the Approval:
```bash
python3 scripts/ask_boss.py "Do you approve deploying this buggy code to production?"
```

#### How it works:
1.  The script posts the prompt to Discord and attaches 👍 and 👎 emojis.
2.  It blocks execution and waits for the server owner to react.
3.  If approved (👍), the script exits with `0` (Success).
4.  If rejected (👎), the script exits with `1` (Failure).

---

## 🌁 4. Jira Cloud Integration Bridge

Add your Jira credentials to `.agents/jira_config.json`:
```json
{
  "project_key": "YOUR_PROJECT_KEY",
  "jira_url": "https://your-company.atlassian.net",
  "jira_email": "developer@company.com"
}
```

Expose your API token:
```bash
export JIRA_TOKEN="your-jira-api-token"
```

### Usage:
```bash
# Retrieve To Do items
python3 scripts/jira_bridge.py get-todo

# Transition a task
python3 scripts/jira_bridge.py transition PROJ-101 "In Progress"

# Create a new task
python3 scripts/jira_bridge.py create "New Task Summary" "Description details"
```

---

## 🧭 Setup & Task Tracking: Jira Cloud vs. Local Kanban Board

Choose your quest tracking style depending on your connectivity and team setup:

### Option A: The Local Mug (Kanban MCP) — *Offline & Local-Only*
If you prefer a clean, private, offline-first workflow, track your tasks locally using the **Kanban MCP Server**.
*   **How it works:** Stores tasks as simple Markdown files inside the `.agents/board/` directory, divided into lanes (`todo`, `doing`, `done`).
*   **Why use it:** 
    *   **Completely local:** No internet connections or external API tokens required.
    *   **AI Sandbox:** Perfect for letting the AI break down a massive prompt into sub-tasks and track its own progress without cluttering your company's shared board.

### Option B: The Shared Guild Board (Jira Cloud Bridge) — *Team Collaboration*
If you are forced to work with other human beings, use the **Jira Cloud Bridge** (`jira_bridge.py`).
*   **How it works:** Syncs directly with your Atlassian Jira Cloud instance.
*   **Why use it:** 
    *   **Single Source of Truth:** Integrates with the official company project tracker.
    *   **Zero-Overhead Parsing:** The bridge script automatically filters down large, token-heavy Jira payloads (50KB+) into minimal JSON (<0.5KB), saving up to **95% of LLM Context Tokens**.
