"""Vendor-neutral file-based Kanban board MCP server. **UNUSED as of DG-250.**

.. warning::

   Nothing declares this server any more. Jira is the only coordination
   surface: ``jira_assign`` says whose work a ticket is, and the status says
   where it is.

   It is kept rather than deleted — an agent does not delete, and marking a
   thing unused beats removing it — so a project that genuinely wants a local
   board can still run it. **Do not wire it back into drunken-team, TWA or
   ISAC.**

   The reason is not that it was broken. A local board next to Jira is a
   *second surface that can disagree with the first*, which is the failure this
   repository spent 2026-08-13 curing: four disagreeing surfaces in DG-249, one
   credential copied to three places in DG-248. The evidence was already on
   disk — this project's own board held three cards, last touched 2026-07-22,
   still using the ``DAGY-`` prefix DG-244 retired, while every real ticket of
   that period went through Jira.

   What is genuinely lost with it: claims expired after
   :data:`~board_mcp.board.CLAIM_TTL_SECONDS` and were released automatically,
   and a Jira assignee never expires.

Original description follows.

Exposes 16 tools (the original 12 from kanban-server.js, ``board_report``, and
the DG-233 scheduling trio: ``board_block_task``, ``board_unblock_task``,
``board_available_tasks``).
Every tool accepts a ``project`` argument resolved through
:class:`~core.registry.ProjectRegistry`, so both Claude Code and Antigravity
can share the same board state without vendor lock-in.

Board directory resolution per project
---------------------------------------
1. ``<project_root>/.claude/board``  — preferred (Claude Code convention)
2. ``<project_root>/.agents/board``  — fallback (drunken-team self-board)
3. ``<project_root>/.claude/board``  — created fresh for new projects

Registry path
-------------
Resolved through :func:`core.paths.registry_path`, so this server reads the
same registry as the Jira and Discord servers: ``$DRUNKEN_HOME/projects.json``
by default, overridable with ``DRUNKEN_REGISTRY_PATH``.

Until DG-242 it derived the path from its own ``__file__`` instead, pointing at
the repo's ``.agents/projects.json``.  That was the §1.3 bug — under
``uv tool install`` the expression resolves inside the virtualenv rather than a
checkout — and it also meant the board and the Jira server could disagree about
which projects exist, with neither of them saying so.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Final, Literal

from mcp.server.fastmcp import FastMCP

from core import paths
from core.errors import RegistryError, as_tool_result
from core.registry import ProjectRegistry

from .board import BoardManager

# ---------------------------------------------------------------------------
# Registry path resolution
# ---------------------------------------------------------------------------


def registry_path() -> str:
    """The one registry every server reads.

    Resolved per call rather than once at import: ``DRUNKEN_REGISTRY_PATH`` is
    how a container points at a mounted file, and a value captured at import
    time would ignore anything set afterwards.
    """
    return str(paths.registry_path())


mcp = FastMCP("drunken-board-mcp")


#: Which project this server instance is entitled to serve. Set from
#: ``--project`` by :func:`main`, and readable directly so a container can bind
#: the server without a command line.
ENV_BOARD_PROJECT: Final = "DRUNKEN_BOARD_PROJECT"


def bound_project() -> str | None:
    """The one project this server may serve, or ``None`` if unbound."""
    return os.environ.get(ENV_BOARD_PROJECT) or None


def _authorize(project: str) -> None:
    """S2 (DG-225). ``project`` used to be a lookup key, and a key opens
    whatever it names.

    ``main()`` said so out loud — *"--project (ignored by board, kept for
    compat)"* — so a server launched to serve one project would serve any other
    registered one on request. Looking the project up in the registry is
    authentication; nothing behind it was authorisation.

    Default deny. An unbound server has no way to know what it is entitled to
    serve, and guessing is the finding itself.
    """
    allowed = bound_project()
    if allowed is None:
        raise RegistryError(
            "This board server is not bound to a project, so it will not serve "
            f"{project!r}.",
            remediation=(
                "Launch it with --project <id>, or set "
                f"{ENV_BOARD_PROJECT}=<id> in its environment. One board "
                "server serves one project: the board is filesystem-bound and "
                "the project is the boundary, not a lookup key."
            ),
        )
    if project != allowed:
        raise RegistryError(
            f"This board server is bound to {allowed!r} and will not serve "
            f"{project!r}.",
            remediation=(
                f"Call it with project={allowed!r}, or run a second server "
                f"bound to {project!r}. Crossing between projects in one "
                "server is what S2 was."
            ),
        )


def _get_manager(project: str) -> tuple[BoardManager, str]:
    """Resolve *project* key to (BoardManager, project_root).

    Raises :exc:`RegistryError` when the project is not registered, or when
    this server is not entitled to serve it.
    """
    _authorize(project)
    registry = ProjectRegistry(registry_path=registry_path())
    data = registry.get_project(project)
    if data is None:
        raise RegistryError(
            f"Unknown project {project!r}.",
            remediation=(
                f"Register it with: drunken-init --project {project} "
                "--path <absolute-path>. `drunken-doctor` lists what is "
                "already registered."
            ),
        )
    project_root: str = data["path"]

    claude_board = os.path.join(project_root, ".claude", "board")
    agents_board = os.path.join(project_root, ".agents", "board")

    if os.path.isdir(claude_board):
        board_dir = claude_board
    elif os.path.isdir(agents_board):
        board_dir = agents_board
    else:
        board_dir = claude_board  # will be created on first write

    return BoardManager(board_dir), project_root


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_next_id(project: str) -> str:
    """
    Returns the next available task ID (e.g. TWA-038). Informational only —
    the actual ID is computed atomically inside board_create_task.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.next_id(), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_create_task(
    project: str,
    lane: str,
    slug: str,
    content: str,
    milestone: str = "",
) -> str:
    """
    Atomically create a new task card in the specified lane under a file lock
    to prevent ID collisions.  lane must be one of: backlog, todo, in-progress,
    blocked, done.  slug is a kebab-case filename suffix, e.g. 'implement-jwt-auth'.
    content is the full Markdown body.  milestone (optional) is injected into
    the Status block (e.g. 'M3') if not already present.
    """
    manager, _ = _get_manager(project)
    ms: str | None = milestone if milestone else None
    return json.dumps(manager.create_task(lane, slug, content, ms), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_claim_task(project: str, task_id: str, agent_slug: str) -> str:
    """
    Atomically claim a todo/ task for the requesting agent.  Validates
    assigned_to match and prevents concurrent double-claim.  Must succeed
    before board_move_task to in-progress.  Claims expire after 1800 s so a
    second agent can take over when the first goes offline.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.claim_task(task_id, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_release_claim(project: str, task_id: str, agent_slug: str) -> str:
    """
    Release a stale or abandoned claim.  Only the original claimant or
    principal-engineer may release.  After release the task is claimable by
    any other agent.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.release_claim(task_id, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_move_task(
    project: str, task_id: str, target_lane: str, agent_slug: str
) -> str:
    """
    Move a task between lanes.  Moving to in-progress requires a prior
    board_claim_task call and enforces WIP=1 per agent.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.move_task(task_id, target_lane, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_done_task(project: str, task_id: str, agent_slug: str) -> str:
    """
    Move a task from in-progress to done and strip its claim.  Validates
    current lane and optionally validates agent identity.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.done_task(task_id, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_block_task(project: str, task_id: str, req_id: str, reason: str) -> str:
    """
    Park a task that is waiting on something, and record what would free it.

    Use this straight after request_boss_approval_async: pass the req_id it
    gave you. The task moves to the `blocked` lane instead of squatting in
    in-progress, so board_available_tasks stops offering it and anything
    that depends on it. Call board_unblock_task once the answer comes back
    approved.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.block_task(task_id, req_id, reason), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_unblock_task(project: str, task_id: str) -> str:
    """
    Return a parked task to the queue once whatever held it is resolved.

    It goes back to `todo` rather than straight to in-progress: it re-enters
    through the normal scheduler and takes its turn, in case something more
    urgent arrived while it was parked.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.unblock_task(task_id), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_available_tasks(project: str) -> str:
    """
    List the tasks that can actually be started right now.

    A task is offered when it is queued in `todo` and every dependency it
    names is done. Anything waiting on a blocked or unfinished task is held
    back, so picking from this list can never start work that immediately
    runs into the same wall.

    Call this when you finish a task, not in the middle of one. If it comes
    back empty, say what the board is waiting on (`board_list_lane` with
    `blocked` shows each parked card and its reason) and end your turn --
    do not poll.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.available_tasks(), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_get_task(project: str, task_id: str) -> str:
    """
    Return the full content and parsed fields of a single task, including its
    current lane and claim state.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.get_task(task_id), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_list_lane(project: str, lane: str) -> str:
    """
    List all tasks in a single lane as structured summaries (id, title, status,
    assignee, milestone, depends_on, blocks, claim state).
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.list_lane(lane), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_summary(project: str) -> str:
    """
    Return a compact snapshot of all lanes: per-lane task counts plus
    structured summaries.  Also auto-releases stale claims older than 1800 s,
    enabling Antigravity to take over tasks abandoned by Claude (or vice versa).
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.summary(), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_orchestrate(project: str, task_ids: list[str]) -> str:
    """
    Read depends_on / blocks fields of the supplied tasks and return a
    dependency-resolved execution plan with tasks grouped into parallel waves
    in topological order.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.orchestrate(task_ids), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_agent_context(project: str, task_id: str) -> str:
    """
    Return a compact handoff envelope for a task (~100-150 tokens): id, title,
    objective, acceptance_criteria, technical_notes, relevant_files,
    depends_on, blocks.  Pass this to a sub-agent instead of the full markdown.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.agent_context(task_id), indent=2)


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def query_project_context(
    project: str, files: list[str], keywords: list[str]
) -> str:
    """
    Extract only the sections from project context files (PROJECT_SPEC.md,
    ARCHITECTURE.md, POLICY.md) that match the supplied keywords.  Short names
    are resolved against the project's .claude/ directory automatically.
    Returns section title + content (~60 lines max per section).  Use this
    instead of reading whole files to avoid context bloat.
    """
    manager, project_root = _get_manager(project)
    return json.dumps(
        manager.query_project_context(project_root, files, keywords), indent=2
    )


@mcp.tool()  # type: ignore[misc]
@as_tool_result
async def board_report(
    project: str,
    audience: Literal["exec", "staff", "dev"],
) -> str:
    """
    Return structured board data grouped by the milestone: field found in each
    card's Status block.  Includes per-milestone counts and completion
    percentage, plus lists of what is in-progress and what is blocked.
    audience is 'exec' | 'staff' | 'dev' and is echoed as metadata — the
    calling agent writes the prose narrative.  Cards without a Milestone field
    group under 'unassigned'.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.report(audience), indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the MCP server."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project",
        type=str,
        help=(
            "The one project this server may serve. Required unless "
            f"{ENV_BOARD_PROJECT} is set — see _authorize()."
        ),
    )
    args, unknown = parser.parse_known_args()

    # Published to the environment rather than kept in a module global: it is
    # then set the same way whether it arrived from a command line or from a
    # container's env, and there is one place to read it.
    if args.project:
        os.environ[ENV_BOARD_PROJECT] = args.project

    # Remove from sys.argv to prevent FastMCP from complaining about unknown args
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        sys.argv.pop(idx)
        if len(sys.argv) > idx:
            sys.argv.pop(idx)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
