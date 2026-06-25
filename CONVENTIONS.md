# Drunken-Agy Coding Conventions

This file (`CONVENTIONS.md`) is natively parsed by **Aider** to enforce architectural and workflow rules.

## SDLC and Workflow Rules

1. **Task Management (Jira SSOT):**
   - You are operating in a Jira-driven workflow.
   - Before writing any code, you must execute the shell command `python scripts/jira_bridge.py get-todo` to know what to build.
   - DO NOT rely on local markdown task boards or MCP servers for task tracking in this repository.

2. **Branching & PRs:**
   - All code modifications must occur on a new branch (e.g., `feature/...`).
   - Do not commit directly to `main`.
   - Use `gh pr create` to submit your work when finished.

3. **Documentation Sync:**
   - We sync documentation to Confluence using `scripts/confluence_bridge.py`.
   - Modify the `.md` files in this repo, not the remote wiki.

## Python Standards
- Use `pytest` for all unit testing. Place tests in the `tests/` directory.
- Avoid hardcoding secrets; always use `os.environ` and `python-dotenv` logic.
- Type hints are highly encouraged for all function signatures.
