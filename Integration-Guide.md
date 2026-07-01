# Drunken-Team: AI Integration Guide

This guide explains how to connect the **Drunken-Team (AI Guild Platform)** with user-side AI tools (Local AI) such as Cursor, Aider, or Claude Code, enabling developers to seamlessly pick up and hand off tasks with the Guild AI on the server.

---

## 1. The MCP Server (Model Context Protocol)
To allow your Local AI to communicate directly with the Guild's systems, we provide the **Guild MCP Server**.
- **Purpose:** Acts as a Central API for the AI to fetch Jira tasks, update statuses, or invoke the QA Agent.
- **Supported Tools:**
  - `get_jira_todo()`: Fetches ready-to-do tasks from the Jira board.
  - `transition_issue()`: Moves a Jira ticket status (e.g., In Progress -> Done).
  - `request_qa_review()`: Sends an alert to the Discord Listener to wake up the Guild's QA Agent to review a Pull Request.
  - `ask_boss()`: Sends a prompt to ask the Boss (Admin/Tech Lead) for approval via Discord.

*(Note: The MCP system has been recently upgraded to FastMCP. You can now start the server natively!)*

---

## 2. Local AI Configuration & Prompts
To ensure each tool understands the rules of the Drunken-Team, we provide standard templates that must be placed at the root of your project:

### 2.1 Cursor Integration (`.cursorrules`)
If you use Cursor IDE, place the `.cursorrules` file to govern Cursor's behavior:
- Forces Cursor to invoke the Guild MCP before writing code to identify "What needs to be done."
- Prevents direct pushes to the `main` branch (forces PR creation).
- Forces the generation of a Markdown summary before handing off to the QA Agent.

### 2.2 Claude Code Integration (`CLAUDE.md`)
For Claude Code (CLI) users, the `CLAUDE.md` file serves as the rulebook:
- Forces the AI to check task statuses via `python scripts/jira_bridge.py get-todo` before proposing work.
- Acts as a Guardrail preventing Claude Code from running destructive shell commands or deleting files arbitrarily.

### 2.3 Aider Integration (`.aider.conf.yml` / `CONVENTIONS.md`)
For Aider:
- Aider automatically pulls coding guidelines from `CONVENTIONS.md` as linting rules.
- Enforces an Auto-commit hook requiring Aider to always prefix commit messages with the `[ISSUE-KEY]` so Jira can track the Git branch.

### 2.4 Context Handoff (`SESSION_CHECKPOINT.md`)
To prevent AI from losing context between sessions, this file acts as the short-term memory.
- The AI will read this file at the start of a session.
- The AI will write/update this file at the end of its turn to leave breadcrumbs for the next session.

---

## 3. Workflow Handoff
The collaborative workflow between the Local AI (Dev Machine) and Guild AI (Central) consists of 4 steps:
1. **Intake:** Dev takes a task -> Local AI calls MCP `get_jira_todo` -> Receives the ticket and transitions it to 'In Progress'.
2. **Execution:** Local AI writes code according to requirements, adhering to `PROJECT_SPEC.md` and `DESIGN.md`.
3. **Handoff:** Once completed, Local AI opens a PR and calls MCP `request_qa_review(pr_url)`.
4. **Validation:** Guild AI (via Discord Listener) receives the alert -> Pulls the code and runs tests. If tests fail, it leaves a comment on the PR; if they pass, it transitions the ticket to 'Done'.

---

## 4. Integrating with an Existing Project
For legacy projects written manually that you wish to integrate into the Drunken-Team (AI Guild Platform), follow these 4 steps:

1. **Install Drunken-Team as a Global CLI**
   Treat Drunken-Team as a CLI package installed on the Dev's machine:
   ```bash
   # On the Dev Machine
   git clone https://github.com/sornbuen15/drunken-team.git
   cd drunken-team
   uv tool install .
   ```
   This allows the use of commands like `drunken-mcp` and `drunken-register` globally.

2. **Provision the Target Project**
   Navigate to the existing project folder and run the registration command:
   ```bash
   cd /path/to/existing-project
   drunken-register .
   ```
   The system will prompt for Jira Token / URL and Discord Token, generate an `.env` file, and automatically add it to `.gitignore`.

3. **Apply the AI Templates**
   Copy the Guild's rules from `.guild_templates/` in Drunken-Team and place them in the root of your existing project:
   ```bash
   cp /path/to/drunken-team/.guild_templates/.cursorrules .
   cp /path/to/drunken-team/.guild_templates/CLAUDE.md .
   cp /path/to/drunken-team/.guild_templates/.aider.conf.yml .
   cp /path/to/drunken-team/.guild_templates/CONVENTIONS.md .
   cp /path/to/drunken-team/.guild_templates/SESSION_CHECKPOINT.md .
   ```
   These files will enforce the Local AI to adhere to the Zero-Defect standards.

4. **Configure MCP for the AI Tool**
   - **For Cursor:** Go to `Settings > Features > MCP > Add New Server`. Select Type as `command` and enter the command `drunken-mcp`.
   - Now, when the Dev assigns a task, the Local AI will follow `.cursorrules` -> invoke `drunken-mcp` -> fetch the Jira ticket -> and eventually submit a PR for QA review!

---
*Note: This document covers only the integration and handoff methods. For in-depth project details or feature designs, please refer to `PROJECT_SPEC.md` and `DESIGN.md` separately.*
