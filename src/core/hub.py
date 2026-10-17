"""Local, offline terminal view of registered projects and available sessions."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from .registry import ProjectRegistry


def load_sessions() -> list[dict[str, object]]:
    """Return session metadata known to this process.

    Agent adapters will provide session records as their evidence and storage
    contracts land. Until then, an empty result is explicit and never inferred
    from a network lookup.
    """
    return []


def render(
    projects: list[tuple[str, str, bool]], sessions: list[dict[str, object]]
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
    for project_id in registry.project_ids():
        config = registry.get_project_config(project_id)
        projects.append((project_id, config.path or "", config.hub_enabled))
    sessions = load_sessions()

    if args.json:
        print(
            json.dumps(
                {
                    "projects": [
                        {"id": project_id, "path": path or None, "hub_enabled": enabled}
                        for project_id, path, enabled in projects
                    ],
                    "sessions": sessions,
                },
                indent=2,
            )
        )
    else:
        print(render(projects, sessions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
