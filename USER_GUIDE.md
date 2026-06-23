# 🍻 Drunken AGY Inn: User Guide & Roster Manual

Welcome to the official manual for the **Drunken AGY Suite**—a set of lightweight, token-optimized, and JRPG-tavern-themed utilities designed to extend Google's Antigravity agentic CLI. 🎮🍺

---

## 🧭 Table of Contents
1. [📋 Pre-requisites](#1-pre-requisites)
2. [⚖️ Required vs. Optional Components](#2-required-vs-optional-components)
3. [🚀 Installation](#3-installation)
4. [🛠️ Post-Install Configuration](#4-post-install-configuration)
5. [💬 Discord Integration & Listener Setup](#5-discord-integration--listener-setup)
6. [🎮 Running the JRPG Tavern Dashboard](#6-running-the-jrpg-tavern-dashboard)

---

## 📋 1. Pre-requisites
To get the most out of the suite, ensure you have:
*   **Python:** version `3.8` or newer.
*   **Git:** installed and configured.
*   **Jira Cloud (Optional):** Your Atlassian Jira Cloud domain URL and an API Token generated from your security profile.
*   **Discord Bot (Optional):** A Discord developer bot token, with **Message Content Intent** enabled in the Discord Developer Portal.

---

## ⚖️ 2. Required vs. Optional Components

| Component | Status | Purpose & Enabled Features |
| :--- | :--- | :--- |
| **Python 3.8+** | **Required** | Runs the CLI utilities, scripts, and JRPG web server. |
| **Google Antigravity CLI** | **Required** | The parent framework that manages the agent directories (`.agents/`). |
| **1Password CLI (`op`)** | *Optional* | **(Recommended)** If installed and configured with biometric auth (Touch ID / Passkey), tokens for Jira and Discord are dynamically retrieved from your vault. No plaintext credentials are saved on your disk. |
| **Jira Integration** | *Optional* | Compresses large Jira API payloads (50KB+) into minimal shots of pure data (<0.5KB). Saves up to **95% of LLM Context Tokens**! |
| **Discord Bot Integration** | *Optional* | Allows running remote agent commands and using `ask_boss.py` to trigger interactive approvals (👍/👎 reactions) from anywhere. |

---

## 🚀 3. Installation

### Local Installation
Install the package globally in editable mode so its command endpoints are exposed directly in your terminal path:

```bash
cd /path/to/drunken-agy
pip install -e .
```

This exposes the following commands:
*   `drunken-register` — Register project workspaces.
*   `drunken-setup` — Generate environment configurations.
*   `drunken-dashboard` — Launch the visual dashboard.
*   `drunken-listen` — Run the Discord command listener.

---

## 🛠️ 4. Post-Install Configuration

After installation, navigate to your target project folder and run the setup scripts:

### 1) Registering a Workspace (`drunken-register`)
Run the register command at the root of any target workspace:
```bash
drunken-register
```
**This script will:**
1.  Initialize the `.agents/` workspace folder.
2.  Generate the `ANTIGRAVITY.md` routing rules if missing.
3.  Check for 1Password CLI and biometric security setup.
4.  **Fallback:** If 1Password is absent, it asks for consent to store configurations globally (`~/.gemini/config/jira_config.json`) and prompts you to input your Jira credentials manually.
5.  Prompt you for your Discord Channel ID.
6.  Generate a local `.env` and append it to `.gitignore` automatically.

### 2) Setting up Environment (`drunken-setup`)
To rebuild or update your workspace credentials:
```bash
drunken-setup
```
This utility grabs tokens from your 1Password vaults or global configurations and compiles them into a local `.env` file at your current working directory.

---

## 💬 5. Discord Integration & Listener Setup

Once you have your Discord Bot Token configured:

1.  Start the gateway listener command in your terminal:
    ```bash
    drunken-listen
    ```
2.  **Discord Guild Commands:**
    *   Directly type any command format you'd send to the `agy` CLI (e.g. `models` or `--print "Check my code structure"`). The bot runs it and answers in the chat.
    *   Type **`!detail`** to dump the raw background execution logs (`agy_discord_raw.log`).
3.  **Human-in-the-Loop Approvals (`ask_boss.py`):**
    Embed the script in your automated pipelines or tasks to prompt the owner before running risky procedures:
    ```bash
    python3 scripts/ask_boss.py "Do you approve deploying this commit to production?"
    ```
    *The script pauses and blocks further steps until the Boss reacts with 👍 (approves - exits with `0`) or 👎 (denies - exits with `1`) in Discord.*

---

## 🎮 6. Running the JRPG Tavern Dashboard

To launch the retro visualizer dashboard:

### 1) Start the Server
```bash
drunken-dashboard [port]
```
*(By default, runs at port `8888` or `8081` and automatically opens `http://localhost:<port>` in your web browser).*

> [!TIP]
> If the port is already in use, the dashboard launcher detects the existing service and opens the active link without causing binding errors.

### 2) Interactive Controls
*   **Specialist Roster:** Click on any agent node (e.g. Ranger for QA, Rogue for Security, Archmage for Principal) to view character sheets.
*   **Work Mode:** Agent glows cyan and prints strict engineering code/logs in the console.
*   **Rest Mode:** Agent sways, drinks virtual ale, and screams funny programming rants when you chat with them.
*   **Tavern Bell:** Ring the bell to toggle the active mode of all agents concurrently.
