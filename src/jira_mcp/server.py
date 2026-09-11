import argparse
import json
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.context import ProjectContext
from core.errors import ConfigError, as_tool_result

from . import assign, backlog
from .jira_client import BoardProfile, JiraClient
from .jql import scope_to_project

#: Said in every move result, because it is the thing an agent will otherwise
#: assume. Backlog membership and status are independent: a ticket parked in
#: the backlog keeps the status it had. Reading "moved to backlog" as "no
#: longer In Progress" would make board-versus-backlog a second coordination
#: surface that can disagree with status — the failure DG-250 cured.
_NOT_A_STATUS = (
    "Backlog membership is not status. These issues keep the status they had; "
    "only where they appear changed. Use jira_transition_issue to change status."
)

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
async def jira_search_issues(jql: str, detail: str = "brief") -> str:
    """
    Search this project's Jira with JQL.

    Returns key, summary, status, assignee, and parent when the issue has one.
    `detail="full"` adds priority and the description as plain text; it costs
    roughly twenty times more per issue, so ask for one issue by key instead of
    running a full search over many.

    The query is scoped to the project this server was launched for: it is
    wrapped as `project = "KEY" AND (your query)`. A clause naming another
    project is kept and simply matches nothing.
    """
    client = get_client()
    # S8 (DG-225). --project named the project and did not confine anything to
    # it. Scoping happens here, at the boundary, rather than inside JiraClient:
    # the client is also used by jira_create_issue and the transition tools,
    # which take a key rather than a query and are already project-bound.
    issues = await client.search_issues(
        scope_to_project(jql, client.project_key), brief=detail != "full"
    )
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
    summary: str,
    description: str,
    issue_type: str = "Task",
    parent: str = "",
    duedate: str = "",
    start_date: str = "",
    labels: str = "",
) -> str:
    """
    Create an issue in this project.

    SHAPE: three headings, FINDING / SCOPE / ACCEPTANCE, and nothing else.
    Declarative, not narrative -- the story of how you found it belongs in the
    commit and the PR. A task is <=120 words; a post-mortem or security finding
    may be as long as it needs.

    `parent` is an Epic or Story key; without it Timeline stays empty, and
    shared context belongs on the Epic rather than copied into each child.
    `labels` stands in for priority, which cannot be set on a team-managed
    project at all. `duedate` and `start_date` are ISO YYYY-MM-DD.

    Full rules, including the status lifecycle and what to verify before Done:
    the `jira-tickets` skill (`skills/kanban/jira-tickets/SKILL.md`).

    Warns, never refuses.
    """
    client = get_client()
    res = await client.create_issue(
        summary,
        description,
        issue_type,
        parent=parent or None,
        duedate=duedate or None,
        start_date=start_date or None,
        labels=[label.strip() for label in labels.split(",") if label.strip()] or None,
    )
    out = json.dumps(res, indent=2)

    warnings = [
        w
        for w in (await client.board_warning(), _orphan_warning(description, parent))
        if w
    ]
    return out + "".join(f"\n\n⚠ {w}" for w in warnings)


#: Where a description stops being a ticket and starts being a document. The
#: project's own older tickets run about 49 words; five written in one session
#: averaged 600. The line is deliberately generous -- this warns, and a warning
#: that fires on ordinary work gets ignored.
ORPHAN_WORD_LIMIT = 250


def _orphan_warning(description: str, parent: str) -> Optional[str]:
    """Long *and* parentless, or nothing at all.

    DG-234's mechanism, reused because it is already proven: say something and
    create the issue anyway. Rejecting is wrong here in both directions -- a
    post-mortem or a security finding *must* stay long, and a long ticket with
    an Epic to hang context on is exactly the right shape. It is the
    combination that signals context being copied instead of linked.
    """
    words = len(description.split())
    if words <= ORPHAN_WORD_LIMIT or parent:
        return None
    return (
        f"This description is {words} words and the issue has no parent. "
        "Context belongs on the Epic and should be linked, not copied into "
        "each child. Created anyway -- post-mortems and security findings are "
        "meant to be long."
    )


def _require_backlog_board(profile: BoardProfile, project_key: str) -> int:
    """The board id to move against, or a refusal that says what to do instead.

    Derived from the project this server was launched for. The agent never
    passes a board id — same rule as S2: the binding is what the server was
    started with, never an argument to a tool.
    """
    if not profile.known:
        raise ConfigError(
            f"Could not reach Jira's agile API to find {project_key}'s board.",
            remediation=(
                "Check the credential with `drunken-doctor`, then try again. "
                "This is a lookup failure rather than a missing board."
            ),
        )

    if profile.id is None:
        raise ConfigError(
            f"{project_key} has no agile board, so it has no backlog to move "
            "work into. A business-type Jira project cannot have one.",
            remediation=(
                "The work has to live in a software-type project to have a "
                "board. Nothing else is affected: search, transition, assign "
                "and comment all work on a business-type project. See DG-237."
            ),
        )

    if profile.backlog is False:
        raise ConfigError(
            f"{project_key}'s board ({profile.display_name!r}, type {profile.type!r}) "
            "has no backlog, so there is nowhere to move issues to or from.",
            remediation=(
                "Enable the backlog for this board in Jira's board settings, or "
                "use jira_transition_issue to move work between columns instead. "
                "Board type does not decide this — a kanban board can have a "
                "backlog and this one does not."
            ),
        )

    return int(profile.id)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_board_info() -> str:
    """
    What this project's Jira board is, and what it can actually do.

    Reports the board's id and type, what it is attached to, and whether it has
    a backlog. The attachment is `project_key`, `project_name` and
    `display_name`; the board's own `name` is deliberately absent because it is
    frozen at creation and nothing can change it — see BoardProfile. The
    latter probed rather than inferred, because type does not predict it. A
    kanban board may have no backlog while a team-managed 'simple' board has
    one. `backlog: null` means the question could not be answered, which is not
    the same as no.

    Also reports the issue types this project accepts and the ids of the
    optional fields `jira_create_issue` can set. Field ids differ per instance
    -- read them here rather than hardcoding one found in a payload.

    Looked up once per process and cached, so asking is free after the first
    call.
    """
    client = get_client()
    profile = await client.board_profile()
    return json.dumps(
        {
            "project": client.project_key,
            "board": {
                "id": profile.id,
                "project_key": profile.project_key,
                "project_name": profile.project_name,
                "display_name": profile.display_name,
                "type": profile.type,
            },
            "backlog": profile.backlog,
            "sprints": False,
            "known": profile.known,
            "issue_types": await client.issue_types(),
            "settable_fields": await client.settable_fields(),
            "note": (
                "No board on this site supports sprints, surveyed 2026-08-16. "
                "Backlog membership is independent of status. Priority is not "
                "settable on a team-managed project; use labels. Field ids are "
                "per instance -- read them here, never hardcode one."
            ),
        },
        indent=2,
    )


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_move_to_backlog(issue_keys: str) -> str:
    """
    Move active issues off this project's board and into its backlog.

    `issue_keys` is one key or several, separated by commas or spaces, e.g.
    "DG-251" or "DG-251, DG-250". At most 50 per call, which is Jira's limit.

    Only issues from the project this server was launched for can be moved; a
    key from another project is refused before the request is sent, because the
    underlying agile endpoint would otherwise move it without complaint.

    This does not change status. A ticket parked in the backlog keeps the status
    it had — use jira_transition_issue for that.
    """
    client = get_client()
    keys = backlog.scope_keys(issue_keys, client.project_key)
    board_id = _require_backlog_board(await client.board_profile(), client.project_key)
    result = await client.move_to_backlog(board_id, keys)
    return json.dumps({**result, "note": _NOT_A_STATUS}, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_move_to_board(issue_keys: str) -> str:
    """
    Move issues out of this project's backlog and back onto its board.

    The way back from jira_move_to_backlog. Same rules: keys from this project
    only, at most 50 at a time, and status is left exactly as it was.
    """
    client = get_client()
    keys = backlog.scope_keys(issue_keys, client.project_key)
    board_id = _require_backlog_board(await client.board_profile(), client.project_key)
    result = await client.move_to_board(board_id, keys)
    return json.dumps({**result, "note": _NOT_A_STATUS}, indent=2)


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


#: DG-339. Each prompt names the skill that owns its process, and stops there.
#: They used to describe the processes themselves, and described them
#: differently from the skills: a `DESIGN.md` no other surface mentions, the
#: blocking approval as the default, "adjust priorities" on a Jira where
#: `priority` cannot be set, a board move read as a status change. A prompt is
#: one more place a rule can be written, which makes it one more place it can
#: disagree. tests/test_jira_mcp_prompts.py holds every prompt -- including any
#: added later -- to naming a skill that exists.
_WITHOUT_THE_SKILL = (
    "If that skill is not installed, say so and stop. Do not reconstruct the "
    "process from memory: a remembered process is how two of them come to disagree."
)


def _follow(process: str, owner: str, scope: str) -> str:
    return (
        f"You are starting {process}. Follow {owner}. It owns this process; "
        f"this prompt does not restate it.\n{scope}\n{_WITHOUT_THE_SKILL}"
    )


@mcp.prompt()  # type: ignore[misc]
def jira_daily_standup() -> str:
    """A daily standup, owned by the `local-progress-reporter` skill."""
    return _follow(
        "a daily standup",
        "the `local-progress-reporter` skill (`/report`)",
        "Cover what is In Progress, what is In Review, and what is blocked. "
        "In Review is in flight, not done.",
    )


@mcp.prompt()  # type: ignore[misc]
def init_project() -> str:
    """Day-0 backlog generation, owned by the `spec-to-backlog` skill."""
    return _follow(
        "project initiation",
        "the `spec-to-backlog` skill (`/init-project`)",
        "It reads the project's documents through the `project-docs` skill "
        "first, and needs only a brief to start.",
    )


@mcp.prompt()  # type: ignore[misc]
def refinement() -> str:
    """Choosing what moves onto the board, owned by `backlog-refinement`."""
    return _follow(
        "backlog refinement",
        "the `backlog-refinement` skill (`/refine`)",
        "Refinement chooses what moves from the backlog onto the board. It "
        "changes no ticket's status and creates no tickets; creating them is "
        "`spec-to-backlog`.",
    )


@mcp.prompt()  # type: ignore[misc]
def sprint_planning() -> str:
    """Planning the next working set: `backlog-refinement`, then `task-estimation`."""
    return _follow(
        "sprint planning",
        "the `backlog-refinement` skill (`/refine`), then the `task-estimation` "
        "skill (`/estimate`)",
        "This Jira has no sprints. Planning here means choosing what moves "
        "from the backlog onto the board, then sizing it.",
    )


@mcp.prompt()  # type: ignore[misc]
def review_retro() -> str:
    """Review and retro: `local-progress-reporter`, then `audit-to-backlog`."""
    return _follow(
        "a review and retrospective",
        "the `local-progress-reporter` skill (`/report`) for the review, then "
        "the `audit-to-backlog` skill (`/audit`) to turn what went wrong into "
        "backlog tickets",
        "Before ending the session, rewrite SESSION_CHECKPOINT.md if the "
        "project keeps one.",
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
