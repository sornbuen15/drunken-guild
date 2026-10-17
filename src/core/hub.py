"""Local, offline terminal view of registered projects and available sessions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .config_gen import MCP_SERVERS
from .registry import ProjectRegistry
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


def render(
    projects: list[tuple[str, str, bool]],
    sessions: list[dict[str, object]],
    catalogs: dict[str, dict[str, Any]] | None = None,
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

    lines.extend(("", "Sessions:"))
    if sessions:
        for session in sessions:
            lines.append(f"  {session}")
    else:
        lines.append("  No session data is available on this machine yet.")
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
    args = parser.parse_args(argv)

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
        sessions = load_sessions()
    except SessionMetadataError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

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
                    "sessions": sessions,
                },
                indent=2,
            )
        )
    else:
        print(render(projects, sessions, catalogs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
