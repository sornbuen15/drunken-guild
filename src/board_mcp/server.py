"""Vendor-neutral file-based Kanban board MCP server.

Exposes 16 tools (the original 12 from kanban-server.js, ``board_report``, and
the DT-233 scheduling trio: ``board_block_task``, ``board_unblock_task``,
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
Set ``DRUNKEN_REGISTRY_PATH`` env var to override.  When unset the server
derives it relative to its own ``__file__`` so it always points to the
drunken-team repo's ``.agents/projects.json``, even when installed via
``uv tool install``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Literal

from mcp.server.fastmcp import FastMCP

from core.registry import ProjectRegistry

from .board import BoardManager

# ---------------------------------------------------------------------------
# Registry path resolution
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_REGISTRY = os.path.normpath(
    os.path.join(_HERE, "..", "..", ".agents", "projects.json")
)
_REGISTRY_PATH = os.environ.get("DRUNKEN_REGISTRY_PATH", _DEFAULT_REGISTRY)

mcp = FastMCP("drunken-board-mcp")


def _get_manager(project: str) -> tuple[BoardManager, str]:
    """Resolve *project* key to (BoardManager, project_root).

    Raises :exc:`ValueError` when the project is not registered.
    """
    registry = ProjectRegistry(registry_path=_REGISTRY_PATH)
    data = registry.get_project(project)
    if data is None:
        raise ValueError(
            f"Unknown project '{project}'. "
            "Run: drunken-register <id> <path> to register it."
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


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_next_id(project: str) -> str:
    """
    Returns the next available task ID (e.g. ALPHA-038). Informational only —
    the actual ID is computed atomically inside board_create_task.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.next_id(), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
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


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_claim_task(project: str, task_id: str, agent_slug: str) -> str:
    """
    Atomically claim a todo/ task for the requesting agent.  Validates
    assigned_to match and prevents concurrent double-claim.  Must succeed
    before board_move_task to in-progress.  Claims expire after 1800 s so a
    second agent can take over when the first goes offline.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.claim_task(task_id, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_release_claim(project: str, task_id: str, agent_slug: str) -> str:
    """
    Release a stale or abandoned claim.  Only the original claimant or
    principal-engineer may release.  After release the task is claimable by
    any other agent.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.release_claim(task_id, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_move_task(
    project: str, task_id: str, target_lane: str, agent_slug: str
) -> str:
    """
    Move a task between lanes.  Moving to in-progress requires a prior
    board_claim_task call and enforces WIP=1 per agent.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.move_task(task_id, target_lane, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_done_task(project: str, task_id: str, agent_slug: str) -> str:
    """
    Move a task from in-progress to done and strip its claim.  Validates
    current lane and optionally validates agent identity.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.done_task(task_id, agent_slug), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
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


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_unblock_task(project: str, task_id: str) -> str:
    """
    Return a parked task to the queue once whatever held it is resolved.

    It goes back to `todo` rather than straight to in-progress: it re-enters
    through the normal scheduler and takes its turn, in case something more
    urgent arrived while it was parked.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.unblock_task(task_id), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
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


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_get_task(project: str, task_id: str) -> str:
    """
    Return the full content and parsed fields of a single task, including its
    current lane and claim state.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.get_task(task_id), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_list_lane(project: str, lane: str) -> str:
    """
    List all tasks in a single lane as structured summaries (id, title, status,
    assignee, milestone, depends_on, blocks, claim state).
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.list_lane(lane), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_summary(project: str) -> str:
    """
    Return a compact snapshot of all lanes: per-lane task counts plus
    structured summaries.  Also auto-releases stale claims older than 1800 s,
    enabling Antigravity to take over tasks abandoned by Claude (or vice versa).
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.summary(), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_orchestrate(project: str, task_ids: list[str]) -> str:
    """
    Read depends_on / blocks fields of the supplied tasks and return a
    dependency-resolved execution plan with tasks grouped into parallel waves
    in topological order.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.orchestrate(task_ids), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
async def board_agent_context(project: str, task_id: str) -> str:
    """
    Return a compact handoff envelope for a task (~100-150 tokens): id, title,
    objective, acceptance_criteria, technical_notes, relevant_files,
    depends_on, blocks.  Pass this to a sub-agent instead of the full markdown.
    """
    manager, _ = _get_manager(project)
    return json.dumps(manager.agent_context(task_id), indent=2)


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
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


@mcp.tool()  # type: ignore[misc]  # Tech Debt: DT-65
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
        "--project", type=str, help="Project ID (ignored by board, kept for compat)"
    )
    args, unknown = parser.parse_known_args()

    # Remove from sys.argv to prevent FastMCP from complaining about unknown args
    if "--project" in sys.argv:
        idx = sys.argv.index("--project")
        sys.argv.pop(idx)
        if len(sys.argv) > idx:
            sys.argv.pop(idx)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
