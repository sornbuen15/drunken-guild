import json
import os
from typing import Dict, Optional


class ProjectRegistry:
    """Manages the central registry of projects for the Guild Master orchestrator."""

    def __init__(self, registry_path: Optional[str] = None) -> None:
        if registry_path:
            self.registry_path = registry_path
        else:
            self.registry_path = os.path.join(os.getcwd(), ".agents", "projects.json")

    def _load_registry(self) -> Dict[str, Dict[str, str]]:
        if not os.path.exists(self.registry_path):
            return {}
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {}
                return data
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_registry(self, data: Dict[str, Dict[str, str]]) -> None:
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def get_projects(self) -> Dict[str, Dict[str, str]]:
        """Return all registered projects."""
        return self._load_registry()

    def get_project(self, project_id: str) -> Optional[Dict[str, str]]:
        """Return details for a specific project."""
        projects = self._load_registry()
        return projects.get(project_id)

    def add_project(self, project_id: str, path: str, description: str = "") -> None:
        """Add or update a project in the registry."""
        if not os.path.isabs(path):
            raise ValueError(f"Project path must be absolute: {path}")

        projects = self._load_registry()
        projects[project_id] = {"path": path, "description": description}
        self._save_registry(projects)

    def remove_project(self, project_id: str) -> bool:
        """Remove a project from the registry. Returns True if removed, False if not found."""
        projects = self._load_registry()
        if project_id in projects:
            del projects[project_id]
            self._save_registry(projects)
            return True
        return False
