# Third-Party AI Integration Guide

The Drunken-Team repository is configured to be seamlessly compatible with various third-party AI coding agents. By default, it employs a strict Jira and Confluence Single Source of Truth (SSOT) workflow.

We have pre-configured native files to force third-party agents to adhere to these rules automatically.

---

## 🤖 Supported Agents & Native Configs

By simply cloning this repository, the following agents will automatically load their respective configuration files and adopt the project's SDLC:

### 1. Claude Code (CLI)
- **Native File:** `CLAUDE.md`
- **Behavior:** When you launch `claude` in the terminal, it reads `CLAUDE.md`. It learns that it must execute `python scripts/jira_bridge.py get-todo` to find tasks and use the bridge scripts to manage state.

### 2. Aider
- **Native File:** `CONVENTIONS.md`
- **Behavior:** Aider parses `CONVENTIONS.md` upon startup. It is instructed to strictly follow the branching and testing conventions, and to interface with Jira via the provided python scripts instead of guessing instructions.

### 3. Cursor IDE
- **Native File:** `.cursorrules`
- **Behavior:** The Cursor Agent and Chat features will respect `.cursorrules`, reminding the developer to use the Jira bridge for task management and the Confluence bridge for documentation syncs, preventing accidental direct edits to `main`.

---

## 🛠️ Manual Setup Requirements (Strict Mode)

For the agents to successfully execute the bridge scripts and enforce the full SDLC, you should set up the following tools.

### 1. Git & GitHub CLI (`gh`)
- **Requirement:** Required for creating feature branches and opening Pull Requests.
- **Setup:** Run `brew install gh` (macOS) and `gh auth login`.

### 2. Jira & Confluence Credentials
- **Requirement:** Required for task syncing and documentation publishing.
- **Setup:** Create a `.env` file at the root of the project:
  ```env
  JIRA_URL="https://your-domain.atlassian.net"
  JIRA_EMAIL="your_email@example.com"
  JIRA_TOKEN="your_api_token"
  JIRA_PROJECT_KEY="YOUR_KEY"
  ```
  *(Note: `.env` is ignored by Git to protect your secrets).*

### 3. 1Password CLI (Optional but Recommended)
- **Requirement:** If you don't want to store tokens in a plain-text `.env` file.
- **Setup:** Install `op` CLI and authenticate. You can wrap the agent launch command like `op run --env-file=.env -- claude` or use `op run -- aider`.

---

## ⚠️ Standalone Mode (If you don't have Jira/Git/1Password)

If you are a solo developer or simply want to use the codebase without the heavy enterprise SDLC constraints, **you can safely skip the tools above**.

To run the AI agents in "Standalone Mode":

1. **If you don't have Jira:**
   - **Action:** Delete or ignore the `scripts/jira_bridge.py` file.
   - **Agent Prompt:** Tell your AI (Claude/Aider): *"Ignore the Jira rules in your config. We will use a local `TODO.md` file for task tracking instead."*

2. **If you don't have Git / GitHub CLI (`gh`):**
   - **Action:** You can work directly on the `main` branch.
   - **Agent Prompt:** Tell your AI: *"Ignore the Pull Request and branching rules. Write and save code directly to the current files."*

3. **If you don't have Confluence:**
   - **Action:** Delete or ignore `scripts/confluence_bridge.py`. Keep your documentation locally in Markdown format.

4. **If you don't have 1Password:**
   - **Action:** Just use the standard local `.env` file as shown in the Manual Setup section. It works perfectly out of the box.

Once configured (or bypassed), simply launch your preferred AI agent and start building!
