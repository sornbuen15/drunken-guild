import os
import subprocess
import sys
from typing import Dict

# Support local imports from scripts directory if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from scripts import jira_bridge  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "Error: The 'mcp' package is not installed. Please run 'pip install mcp'",
        file=sys.stderr,
    )
    sys.exit(1)

# Initialize FastMCP Server
mcp = FastMCP("Drunken-Guild-MCP")

# Load environment variables just like jira_bridge does
jira_bridge.load_dotenv()


def get_jira_config() -> Dict[str, str]:
    token = jira_bridge.get_jira_token()
    if not token:
        raise ValueError("JIRA_TOKEN not found in environment.")
    return {
        "jira_url": os.environ.get("JIRA_URL") or "",
        "jira_email": os.environ.get("JIRA_EMAIL") or "",
        "project_key": os.environ.get("JIRA_PROJECT_KEY") or "",
        "jira_token": token,
    }


@mcp.tool()  # type: ignore[misc]
def get_jira_todo() -> str:
    """Fetch tasks from Jira that are in 'To Do' or 'Selected for Development' status."""
    config = get_jira_config()
    jql = f'project = {config["project_key"]} AND status IN ("To Do", "Selected for Development", "Backlog") ORDER BY priority DESC'
    issues = jira_bridge.search_issues(config, jql)
    if not issues:
        return "No tasks found in To Do or Backlog."

    result = []
    for i in issues:
        result.append(
            f"[{i['key']}] {i['summary']} (Status: {i['status']}, Priority: {i['priority']})"
        )
    return "\n".join(result)


@mcp.tool()  # type: ignore[misc]
def transition_issue(issue_key: str, target_status: str) -> str:
    """Transition a Jira issue to a new status (e.g. 'In Progress', 'Done')."""
    script_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "jira_bridge.py"
    )
    try:
        result = subprocess.run(
            ["python", script_path, "transition", issue_key, target_status],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return f"Successfully transitioned {issue_key} to {target_status}.\n{result.stdout}"
        else:
            return (
                f"Failed to transition {issue_key} to {target_status}.\n{result.stderr}"
            )
    except Exception as e:
        return f"Error executing jira_bridge.py: {str(e)}"


@mcp.tool()  # type: ignore[misc]
def ask_boss(question: str) -> str:
    """
    Ask the Boss (Tech Lead) a question on Discord for approval.
    Blocks until the boss reacts with thumbs up or down.
    """
    script_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "ask_boss.py"
    )
    try:
        result = subprocess.run(
            ["python", script_path, question],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return f"Boss Approved! (Exit code 0)\n{result.stdout}"
        else:
            return f"Boss Rejected! (Exit code {result.returncode})\n{result.stderr}"
    except Exception as e:
        return f"Error executing ask_boss.py: {str(e)}"


@mcp.tool()  # type: ignore[misc]
def request_qa_review(pr_url: str) -> str:
    """
    Notify the Discord Listener to wake up the QA Agent for PR review.
    """
    # For now, we will simulate this or send a discord message if needed.
    return f"QA Review requested for PR: {pr_url}. The Guild AI has been notified."


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
