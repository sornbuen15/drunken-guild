import argparse
import json
import sys

from mcp.server.fastmcp import FastMCP

from core.context import ProjectContext
from core.errors import ConfigError, as_tool_result

from . import assign
from .jira_client import JiraClient
from .jql import scope_to_project

# Create the FastMCP server instance
mcp = FastMCP("drunken-jira-mcp")

# JiraClient will be initialized on demand by get_client()
jira = None  # type: ignore[assignment]
ctx: ProjectContext | None = None


def get_client() -> JiraClient:
    global jira
    if not jira:
        if not ctx:
            raise ConfigError(
                "This server was started without a project, so it has no Jira "
                "credentials to use.",
                remediation=(
                    "Relaunch it as `drunken-jira-mcp --project <id>`, using an "
                    "id from your registry. `drunken-doctor` lists what is "
                    "registered and `drunken-init` adds a project."
                ),
            )
        jira = JiraClient(ctx)
    return jira


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_search_issues(jql: str) -> str:
    """
    Search for Jira issues using a JQL query, within this server's project.
    Returns a minified JSON string of issues (key, summary, status, priority, description, assignee).

    The query is scoped to the project this server was launched for: it is
    wrapped as `project = "KEY" AND (your query)`. A clause naming another
    project is kept and simply matches nothing. To search a different project,
    run a server bound to it.
    """
    client = get_client()
    # S8 (DT-225). --project named the project and did not confine anything to
    # it. Scoping happens here, at the boundary, rather than inside JiraClient:
    # the client is also used by jira_create_issue and the transition tools,
    # which take a key rather than a query and are already project-bound.
    issues = await client.search_issues(scope_to_project(jql, client.project_key))
    return json.dumps(issues, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_assign(issue_key: str, assignee: str) -> str:
    """
    Assign an issue, or clear its assignee.

    With the local board retired, this is how an agent says "this one is mine"
    and how work is handed to another. The assignee says whose it is; the
    status says where it is.

    `assignee` accepts an email, a display name, "me" for the calling identity,
    or "none" to unassign. A name that matches more than one assignable user is
    refused rather than guessed — a ticket assigned to the wrong person goes
    quiet on somebody else's queue and nothing reports it.
    """
    client = get_client()

    if assign.is_unassign(assignee):
        return json.dumps(await client.assign_issue(issue_key, None), indent=2)

    if assign.is_self_reference(assignee):
        account_id = await client.my_account_id()
        return json.dumps(await client.assign_issue(issue_key, account_id), indent=2)

    candidates = await client.assignable_users(assignee)
    user = assign.pick_user(candidates, assignee)
    result = await client.assign_issue(issue_key, str(user["accountId"]))
    result["assignee"] = user.get("displayName")
    return json.dumps(result, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_create_issue(
    summary: str, description: str, issue_type: str = "Task"
) -> str:
    """
    Create a new task/issue in the configured Jira project.

    Warns if the project has no agile board — the issue is created either
    way, but on a business-type project it will not appear on one.
    """
    client = get_client()
    res = await client.create_issue(summary, description, issue_type)
    out = json.dumps(res, indent=2)
    warning = await client.board_warning()
    return f"{out}\n\n⚠ {warning}" if warning else out


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_transition_issue(issue_key: str, target_status: str) -> str:
    """
    Move an issue between columns/statuses (e.g., 'To Do' -> 'In Progress').
    """
    client = get_client()
    res = await client.transition_issue(issue_key, target_status)
    return json.dumps(res, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_add_comment(issue_key: str, comment: str) -> str:
    """
    Add a comment to an issue to provide updates or audit trails.
    """
    client = get_client()
    res = await client.add_comment(issue_key, comment)
    return json.dumps(res, indent=2)


@mcp.resource("jira://issue/{issue_key}")  # type: ignore[misc]
async def get_issue_details(issue_key: str) -> str:
    """
    Get full JSON details of a specific Jira issue.
    """
    client = get_client()
    res = await client.get_issue(issue_key)
    return json.dumps(res, indent=2)


@mcp.resource("jira://board")  # type: ignore[misc]
async def get_default_project_board() -> str:
    """
    Get a snapshot of the current active board for the default project.
    """
    client = get_client()
    project_key = client.project_key
    jql = f"project = {project_key} AND status in ('To Do', 'In Progress', 'In Review')"
    issues = await client.search_issues(jql)
    return json.dumps(issues, indent=2)


@mcp.resource("jira://project/{project_key}/board")  # type: ignore[misc]
async def get_project_board(project_key: str) -> str:
    """
    Get a snapshot of the current active board for the project (returns To Do, In Progress, In Review issues).
    """
    client = get_client()
    jql = f"project = {project_key} AND status in ('To Do', 'In Progress', 'In Review')"
    issues = await client.search_issues(jql)
    return json.dumps(issues, indent=2)


@mcp.prompt()  # type: ignore[misc]
def jira_daily_standup() -> str:
    """
    Prompt template for a daily standup update based on active Jira issues.
    """
    return "Please summarize the current blockers and active work using the tickets in 'In Progress' and 'In Review' states."


@mcp.prompt()  # type: ignore[misc]
def init_project() -> str:
    """
    Triggers the initial project architecture phase.
    """
    return (
        "You are beginning the init-project phase.\n"
        "1. Read PROJECT_SPEC.md and DESIGN.md.\n"
        "2. If this is an existing project, briefly scan the source code structure.\n"
        "3. Generate a high-level Domain-Driven Design (DDD) architecture document.\n"
        "4. Develop a 'Walking Skeleton' (Feasibility Spike) to prove the tech stack.\n"
        "5. Present the DDD and Spike to the Boss. You MUST call the request_boss_approval MCP tool to get approval before creating any tickets."
    )


@mcp.prompt()  # type: ignore[misc]
def refinement() -> str:
    """
    Triggers the project backlog refinement phase.
    """
    return (
        "You are beginning the refinement phase.\n"
        "1. Read the approved architecture and DDD.\n"
        "2. Break down the work into structured Jira tasks.\n"
        "3. Use the jira_create_issue tool to populate the backlog.\n"
        "4. CRITICAL: Every task MUST have strict Acceptance Criteria (AC) which will be used for TDD."
    )


@mcp.prompt()  # type: ignore[misc]
def sprint_planning() -> str:
    """
    Triggers the sprint planning phase.
    """
    return (
        "You are beginning the sprint-planning phase.\n"
        "1. Read all tasks in the Backlog and the active board.\n"
        "2. Adjust priorities and move selected tasks to 'To Do'.\n"
        "3. Dependency Triage: Determine if tasks touch the same files. If yes, they must be executed in Sequence. If no, they can be executed in Parallel.\n"
        "4. Present the Sprint Plan to the Boss and ask: 'Execute in Sequence or Parallel?'"
    )


@mcp.prompt()  # type: ignore[misc]
def review_retro() -> str:
    """
    Triggers the sprint review and retro phase.
    """
    return (
        "You are beginning the review-retro phase.\n"
        "1. Evaluate the completed sprint.\n"
        "2. Identify any Tech Debt or Enhancements. Use jira_create_issue to add them to the backlog, but strictly tag them as [TECH-DEBT] or [ENHANCEMENT] with low priority.\n"
        "3. Ask the Boss: 'Proceed with next sprint planning? (Yes/No)'.\n"
        "4. Advise the Boss: 'Recommendation: Create a session checkpoint and close this session to clear memory context.'"
    )


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_start_task(issue_key: str) -> str:
    """
    Start working on a Jira task. Transitions the ticket to 'In Progress' and returns the Git command required for branching.
    """
    client = get_client()
    await client.transition_issue(issue_key, "In Progress")
    git_command = f"git checkout -b feature/{issue_key}"
    return json.dumps(
        {
            "status": "In Progress",
            "instruction": f"Task started. You MUST run this git command before coding: `{git_command}`",
        },
        indent=2,
    )


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_submit_for_review(
    issue_key: str, pr_link: str, files_changed: str
) -> str:
    """
    Submit a task for review. Transitions the ticket to 'In Review' and adds a comment with the PR link.
    """
    client = get_client()
    await client.transition_issue(issue_key, "In Review")

    comment = f"**Code Submitted for Review**\n\n*PR Link:* {pr_link}\n*Files Changed:* {files_changed}"
    await client.add_comment(issue_key, comment)

    return json.dumps(
        {
            "status": "In Review",
            "message": f"Successfully submitted {issue_key} for review. Integration tests should be run when all tasks reach In Review.",
        },
        indent=2,
    )


def parse_project_arg(argv: list[str]) -> str | None:
    """Read --project without ever exiting the process.

    Deliberately not `required=True`: argparse enforces that by calling
    sys.exit(2), which killed the server before the MCP handshake. The host
    then saw a process that simply vanished, with nothing to read and
    nothing to act on. A server that starts and says what is wrong when a
    tool is called is strictly more useful than one that is not there.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", type=str, default=None)
    args, _ = parser.parse_known_args(argv)
    project: str | None = args.project
    return project


def main() -> None:
    global ctx
    project = parse_project_arg(sys.argv[1:])

    if project:
        try:
            ctx = ProjectContext.build(project)
        except Exception as e:
            # Same reasoning as above, one layer down: a bad project id, an
            # unreadable registry, or an unresolvable secret must surface
            # from the tool call that needs it, carrying its remediation --
            # not as a dead process at startup.
            print(
                f"[drunken-jira-mcp] Could not load project {project!r}: {e}. "
                "Starting anyway; tools will report this with the fix.",
                file=sys.stderr,
                flush=True,
            )

    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        sys.argv.pop(idx)
        if len(sys.argv) > idx:
            sys.argv.pop(idx)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
