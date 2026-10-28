"""Local, offline terminal view of registered projects and available sessions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .config_gen import MCP_SERVERS
from .registry import ProjectRegistry
from .session_discovery import discover_claude_sessions as discover_claude_sessions
from .session_store import SessionMetadataError, load_session_metadata

SKILL_ROOTS = ("skills", ".claude/skills", ".agents/skills", ".gemini/skills")


def scan_project_resources(
    project_path: str | Path | None, mcp_integrations: list[str] | None = None
) -> dict[str, Any]:
    """Catalog project-local skill files and profile-configured MCP names.

    MCP command and environment values live in host config files, which may
    contain credentials. The catalog therefore uses only names supplied by
    the project profile/config generator and never opens those files.
    """
    root = Path(project_path).expanduser() if project_path else None
    skills: list[dict[str, str]] = []
    root_available = root is not None and root.is_dir()

    if root_available and root is not None:
        for relative_root in SKILL_ROOTS:
            skill_root = root / relative_root
            if not skill_root.is_dir():
                continue
            for skill_file in sorted(skill_root.glob("**/SKILL.md")):
                skills.append(
                    {
                        "name": skill_file.parent.name,
                        "path": skill_file.relative_to(root).as_posix(),
                    }
                )

    configured_mcp = mcp_integrations or []
    return {
        "skills": skills,
        "skill_inventory_status": (
            "configured"
            if skills
            else "not_configured"
            if root_available
            else "unknown"
        ),
        "mcp_integrations": [
            {"name": name, "source": "project profile"}
            for name in sorted(set(configured_mcp))
        ],
        "mcp_config_status": "configured" if configured_mcp else "not_configured",
        "agent_access": {
            "status": "unknown",
            "agents": [],
            "reason": "No project-local agent access evidence is recorded.",
        },
    }


def load_sessions() -> list[dict[str, object]]:
    """Return session metadata saved on this machine, without network access."""
    return load_session_metadata()


def _registry_is_known(registry: ProjectRegistry) -> bool:
    """Return whether registration can be distinguished from an empty registry."""
    try:
        with (
            Path(registry.registry_path)
            .expanduser()
            .open("r", encoding="utf-8") as handle
        ):
            document = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict):
        return False
    projects = document.get("projects", document)
    return isinstance(projects, dict) and all(
        isinstance(value, dict) for value in projects.values()
    )


def _render_session_sections(
    sessions: list[dict[str, object]],
    sources: list[dict[str, object]] | None,
    saved_sessions: list[dict[str, object]] | None,
) -> list[str]:
    lines = ["", "Live sessions:"]
    if sources:
        for source in sources:
            lines.append(f"  {source['provider']}: {source['status']}")
    if sessions:
        for session in sessions:
            lines.append(
                "  "
                f"{session['provider']} {session['session_id'] or '(id unknown)'} "
                f"[{session['activity']}; {session['registration']}] "
                f"{session['project_path'] or '(path unknown)'}"
            )
    elif any(source.get("status") == "available" for source in sources or []):
        lines.append("  No live sessions were returned by available sources.")
    else:
        lines.append("  No live sessions returned; source availability is shown above.")

    lines.extend(("", "Saved session metadata:"))
    if saved_sessions:
        for session in saved_sessions:
            lines.append(f"  {session}")
    else:
        lines.append("  No saved session metadata.")
    return lines


def render(
    projects: list[tuple[str, str, bool]],
    sessions: list[dict[str, object]],
    catalogs: dict[str, dict[str, Any]] | None = None,
    sources: list[dict[str, object]] | None = None,
    saved_sessions: list[dict[str, object]] | None = None,
) -> str:
    """Render a stable, human-readable overview without contacting services."""
    lines = ["Drunken Guild Hub", "", "Projects:"]
    if projects:
        for project_id, path, enabled in projects:
            location = path or "path not registered"
            hub_status = "enabled" if enabled else "disabled"
            lines.append(f"  {project_id}  [{hub_status}]  {location}")
    else:
        lines.append("  No registered projects. Run drunken-init to add one.")

    lines.extend(("", "Project resources:"))
    if projects:
        catalogs = catalogs or {}
        for project_id, _, _ in projects:
            catalog = catalogs.get(project_id, {})
            skills = catalog.get("skills", [])
            integrations = catalog.get("mcp_integrations", [])
            skill_names = [item["name"] for item in skills if isinstance(item, dict)]
            integration_names = [
                item["name"] for item in integrations if isinstance(item, dict)
            ]
            lines.append(f"  {project_id}")
            lines.append(
                "    Skills: "
                + (", ".join(skill_names) if skill_names else "none found")
            )
            lines.append(
                "    MCP integrations: "
                + (
                    ", ".join(integration_names)
                    if integration_names
                    else "none configured"
                )
            )
            access = catalog.get("agent_access", {})
            status = (
                access.get("status", "unknown")
                if isinstance(access, dict)
                else "unknown"
            )
            lines.append(f"    Agent access: {status}")
    else:
        lines.append("  No registered projects.")

    lines.extend(_render_session_sections(sessions, sources, saved_sessions))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Show registered project profiles and locally available session data."""
    parser = argparse.ArgumentParser(
        prog="drunken-hub",
        description="Show registered projects and local Hub session information.",
    )
    parser.add_argument(
        "--registry", help="Registry file to use instead of the default."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text."
    )
    parser.add_argument(
        "--web", action="store_true", help="Open a local browser dashboard server."
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="Local dashboard port (default: 8765)."
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="Enable explicit Claude/Codex job submission in isolated worktrees",
    )
    parser.add_argument("--jobs-dir", help="Private managed-job state directory")
    parser.add_argument(
        "--web-origin",
        help="Exact HTTPS origin served by the trusted local Tailscale proxy",
    )
    parser.add_argument(
        "--web-user", help="Tailscale login permitted to access the remote web origin"
    )
    args = parser.parse_args(argv)
    if (
        args.control or args.jobs_dir or args.web_origin or args.web_user
    ) and not args.web:
        parser.error("Web control options require --web")

    if args.web:
        from .dashboard import serve

        if args.json:
            parser.error("--web and --json cannot be combined")
        if not 0 <= args.port <= 65535:
            parser.error("--port must be between 0 and 65535")
        try:
            return serve(
                args.registry,
                args.port,
                control=args.control,
                jobs_dir=args.jobs_dir,
                web_origin=args.web_origin,
                web_user=args.web_user,
            )
        except (OSError, ValueError) as exc:
            print(f"Could not start the local dashboard: {exc}", file=sys.stderr)
            return 2

    registry = ProjectRegistry(args.registry) if args.registry else ProjectRegistry()
    projects = []
    catalogs: dict[str, dict[str, Any]] = {}
    for project_id in registry.project_ids():
        config = registry.get_project_config(project_id)
        projects.append((project_id, config.path or "", config.hub_enabled))
        catalogs[project_id] = scan_project_resources(
            config.path, list(MCP_SERVERS) if config.jira is not None else []
        )
    try:
        saved_sessions = load_sessions()
    except SessionMetadataError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    live_sessions, sources = discover_claude_sessions(
        [(project_id, path) for project_id, path, _ in projects],
        registry_known=_registry_is_known(registry),
    )

    if args.json:
        print(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": project_id,
                            "path": path or None,
                            "hub_enabled": enabled,
                            "resources": catalogs[project_id],
                        }
                        for project_id, path, enabled in projects
                    ],
                    "sessions": live_sessions,
                    "session_sources": sources,
                    "saved_sessions": saved_sessions,
                },
                indent=2,
            )
        )
    else:
        print(render(projects, live_sessions, catalogs, sources, saved_sessions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
