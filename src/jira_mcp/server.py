import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from core.context import ProjectContext
from core.errors import ConfigError, ValidationError, as_tool_result
from core.registry import ProjectRegistry

from . import assign, backlog, edits
from . import labels as label_ops
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

#: One client per project, built on first use and kept.
#:
#: Kept, because :mod:`core.secrets` consults each backend once per process and
#: a backend like 1Password prompts for biometrics on every read — resolving per
#: tool call would make the server unusable. Keyed by project id, because this
#: one process serves every project now.
_clients: dict[str, JiraClient] = {}


def forget_clients() -> None:
    """Drop every resolved client. For tests, and for a credential reload."""
    _clients.clear()


def get_client(project: str) -> JiraClient:
    """The Jira client for *project*, or a refusal that says what to do.

    *project* is the **project id from the registry** — the name
    ``drunken-doctor`` lists — not the Jira project key. One server serves every
    project, so this is the only thing that says which one a call is about.

    Nothing here falls back. Not to a single registered project, not to the
    first key in the registry file, not to the working directory. DG-341 is what
    a fallback costs: a server pinned to one project answered every session on
    the machine, and the sessions that were not that project got its board while
    reporting success. A refusal is recoverable; a wrong board is not noticed.
    """
    key = (project or "").strip()
    if not key:
        registry = ProjectRegistry()
        known = registry.project_ids()
        raise ConfigError(
            "No project was given, so there is nothing to act on.",
            remediation=(
                "Pass the project id as the first argument of the tool. "
                + (
                    f"Registered: {', '.join(known)}. "
                    if known
                    else f"The registry at {registry.registry_path} has no "
                    "projects yet; add one with `drunken-init`. "
                )
                + "It is the registry id (as `drunken-doctor` lists it), not "
                "the Jira project key. The project's AGENTS.md names which one "
                "to use."
            ),
        )

    client = _clients.get(key)
    if client is None:
        # `get_project_config` validates the id and refuses an unknown one,
        # naming what is registered — so a traversal attempt and a typo both
        # arrive as words rather than as a path join or an empty board.
        client = JiraClient(ProjectContext.build(key))
        _clients[key] = client
    return client


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_search_issues(project: str, jql: str, detail: str = "brief") -> str:
    """
    Search a project's Jira with JQL. `project` is the registry id, not the
    Jira key. The query is wrapped as `project = "KEY" AND (yours)`, so a clause
    naming another project matches nothing. `detail="full"` adds priority and
    description at about twenty times the cost.
    """
    client = get_client(project)
    # S8 (DG-225). --project named the project and did not confine anything to
    # it. Scoping happens here, at the boundary, rather than inside JiraClient:
    # the client is also used by jira_create_issue and the transition tools,
    # which take a key rather than a query and are already project-bound.
    issues = await client.search_issues(
        scope_to_project(jql, client.project_key), brief=detail != "full"
    )
    return json.dumps(issues, indent=2)


# With the local board retired, this is how an agent says "this one is mine" and
# how work is handed over: the assignee says whose it is, the status says where
# it is. An ambiguous name is refused rather than guessed — a ticket assigned to
# the wrong person goes quiet on somebody else's queue and nothing reports it.
@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_assign(project: str, issue_key: str, assignee: str) -> str:
    """
    Assign an issue in `project`, or clear it. `assignee` takes an email, a
    display name, "me", or "none". A name matching more than one assignable
    user is refused rather than guessed.
    """
    client = get_client(project)

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
    project: str,
    summary: str,
    description: str,
    issue_type: str = "Task",
    parent: str = "",
    duedate: str = "",
    start_date: str = "",
    labels: str = "",
) -> str:
    """
    Create an issue in `project`. Its shape and word budget are the
    `jira-tickets` skill's. `parent` is an Epic or Story key — without one the
    Timeline stays empty. `labels` is comma-separated and stands in for
    priority, which this Jira cannot set. Dates are ISO YYYY-MM-DD. Warns,
    never refuses.
    """
    client = get_client(project)
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

    Derived from the project the call named. The agent never passes a board
    id: a board is a fact about a project, looked up, not something a caller
    gets to assert.
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


# The board's own `name` is deliberately not reported: it is frozen at creation
# and nothing can change it, so it goes stale against the project it names.
# `backlog` is probed rather than inferred, because type does not predict it — a
# kanban board may have none while a team-managed 'simple' board has one. Looked
# up once per process and cached, so asking is free after the first call. (These
# were in the docstring until DG-361; a comment costs nothing, a description
# costs every session.)
@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_board_info(project: str) -> str:
    """
    What `project`'s board is and what it can do: id, type, what it is attached
    to, whether it has a backlog, the issue types it accepts, and the settable
    field ids. Field ids differ per instance — read them here, never hardcode
    one. `backlog: null` means the question could not be answered, not no.
    """
    client = get_client(project)
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
async def jira_move_to_backlog(project: str, issue_keys: str) -> str:
    """
    Move issues off `project`'s board into its backlog. `issue_keys` is one or
    several, comma- or space-separated, at most 50 (Jira's limit). A key from
    another project is refused before the request is sent. Does not change
    status.
    """
    client = get_client(project)
    keys = backlog.scope_keys(issue_keys, client.project_key)
    board_id = _require_backlog_board(await client.board_profile(), client.project_key)
    result = await client.move_to_backlog(board_id, keys)
    return json.dumps({**result, "note": _NOT_A_STATUS}, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_move_to_board(project: str, issue_keys: str) -> str:
    """
    Move issues out of `project`'s backlog back onto its board. Same rules as
    jira_move_to_backlog: this project's keys only, at most 50, status
    untouched.
    """
    client = get_client(project)
    keys = backlog.scope_keys(issue_keys, client.project_key)
    board_id = _require_backlog_board(await client.board_profile(), client.project_key)
    result = await client.move_to_board(board_id, keys)
    return json.dumps({**result, "note": _NOT_A_STATUS}, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_transition_issue(
    project: str, issue_key: str, target_status: str
) -> str:
    """
    Move an issue in `project` between statuses, e.g. 'To Do' -> 'In Progress'.
    `target_status` is the status name.
    """
    client = get_client(project)
    res = await client.transition_issue(issue_key, target_status)
    return json.dumps(res, indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_add_comment(project: str, issue_key: str, comment: str) -> str:
    """
    Add a comment to an issue in `project`.
    """
    client = get_client(project)
    res = await client.add_comment(issue_key, comment)
    return json.dumps(res, indent=2)


# DG-368. Operations, not a replacement set, so two agents labelling one ticket
# cannot drop each other's label — see label_ops (labels.py).
@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_edit_labels(
    project: str, issue_key: str, add: str = "", remove: str = ""
) -> str:
    """
    Add and/or remove labels on one issue in `project`, comma-separated. Other
    labels are left as they are.
    """
    client = get_client(project)
    keys = backlog.scope_keys(issue_key, client.project_key)
    if len(keys) != 1:
        raise ValidationError(
            f"One issue per call, got {len(keys)}.",
            remediation="Call once per issue key.",
        )
    (key,) = keys
    payload = label_ops.update_payload(add, remove)
    return json.dumps(await client.edit_labels(key, payload), indent=2)


# DG-367. Only the fields passed are sent, so one correction cannot clear
# another field — see edits.py. Labels stay with jira_edit_labels.
@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_edit_issue(
    project: str, issue_key: str, summary: str = "", description: str = ""
) -> str:
    """
    Correct the summary and/or description of one issue in `project`. An empty
    argument is left unchanged.
    """
    client = get_client(project)
    keys = backlog.scope_keys(issue_key, client.project_key)
    if len(keys) != 1:
        raise ValidationError(
            f"One issue per call, got {len(keys)}.",
            remediation="Call once per issue key.",
        )
    (key,) = keys
    payload = edits.fields_payload(summary, description)
    return json.dumps(await client.edit_issue(key, payload), indent=2)


# Both resource URIs carry the project, for the same reason every tool takes
# it. `jira://board` — "the default project" — is gone: there is no default, and
# a URI that implied one would be read as though there were.
@mcp.resource("jira://project/{project}/issue/{issue_key}")  # type: ignore[misc]
async def get_issue_details(project: str, issue_key: str) -> str:
    """
    Get full JSON details of a specific Jira issue.
    """
    client = get_client(project)
    res = await client.get_issue(issue_key)
    return json.dumps(res, indent=2)


@mcp.resource("jira://project/{project}/board")  # type: ignore[misc]
async def get_project_board(project: str) -> str:
    """
    Get a snapshot of a project's active board (To Do, In Progress, In Review).
    """
    client = get_client(project)
    jql = (
        f"project = {client.project_key} "
        "AND status in ('To Do', 'In Progress', 'In Review')"
    )
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
    """The day's state, owned by the `audit` skill."""
    return _follow(
        "a daily standup",
        "the `audit` skill (`/audit`)",
        "Cover what is In Progress, what is In Review, and what is blocked. "
        "In Review is in flight, not done.",
    )


@mcp.prompt()  # type: ignore[misc]
def init_project() -> str:
    """The start of the flow, owned by the `prd` skill."""
    return _follow(
        "a new project",
        "the `prd` skill (`/prd`)",
        "The flow is /prd, then /clarify, then /ddd, then /breakdown. No "
        "ticket exists before /breakdown, and nothing is created there before "
        "the Boss approves the hierarchy.",
    )


@mcp.prompt()  # type: ignore[misc]
def refinement() -> str:
    """What is in the working set, owned by the `jira-tickets` skill."""
    return _follow(
        "choosing what moves onto the board",
        "the `jira-tickets` skill",
        "Backlog membership and status are independent axes: moving a ticket "
        "onto the board changes what is in the working set and nothing else. "
        "Which tickets move is the Boss's decision, not a skill's.",
    )


@mcp.prompt()  # type: ignore[misc]
def sprint_planning() -> str:
    """Cutting the work, owned by the `breakdown` skill."""
    return _follow(
        "planning the work",
        "the `breakdown` skill (`/breakdown`)",
        "This Jira has no sprints and no story points. A task is a vertical "
        "slice finishable in a day, and tasks touching the same files run in "
        "sequence.",
    )


@mcp.prompt()  # type: ignore[misc]
def review_retro() -> str:
    """Review and retro, owned by the `audit` skill."""
    return _follow(
        "a review and retrospective",
        "the `audit` skill (`/audit`)",
        "Every requirement traces to a task and to a test that passes on the "
        "merged tree; each gap becomes a ticket. Before ending the session, "
        "rewrite SESSION_CHECKPOINT.md if the project keeps one.",
    )


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def jira_start_task(project: str, issue_key: str) -> str:
    """
    Move an issue in `project` to In Progress and return the branch command to
    run before coding.
    """
    client = get_client(project)
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
    project: str, issue_key: str, pr_link: str, files_changed: str
) -> str:
    """
    Move an issue in `project` to In Review and comment the PR link. The
    argument is `pr_link`; `files_changed` is a one-line summary.
    """
    client = get_client(project)
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


def main() -> None:
    """Start the server. It takes no arguments, and that is the fix.

    `--project` is gone (DG-341). It was what user scope was able to pin: one
    entry in `~/.claude.json` reaches every session on the machine, so a server
    launched with `--project drunken-guild` answered sessions that were not that
    project, handing them its board while reporting success.

    With the project arriving per call, one configuration is correct everywhere
    and there is nothing to pin. An unexpected argument is ignored rather than
    fatal, for the reason `--project` used to be parsed loosely: argparse's own
    failure is `sys.exit(2)`, which killed the process before the MCP handshake
    and left the host with nothing to read.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
