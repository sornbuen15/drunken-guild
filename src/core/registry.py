"""The central registry: which projects exist, and what each one *is*.

One file answers "which Jira, which repo, which Discord channel" for every
project. Nothing in it is secret — credentials appear only as references
(``env://…``, ``op://…``) resolved by :mod:`core.secrets` — so it can be
committed, reviewed and shared, which is precisely what stops five copies of a
token drifting apart in five ``.env`` files.

Schema v2 wraps the project map in ``{"version": 2, "projects": {...}}``. A v1
file — the bare map written by earlier releases — is upgraded in memory on read
and is never rewritten behind the operator's back, so downgrading is just
running the old code again.

``path`` is optional on purpose. Only the file-backed board needs a checkout on
disk; a Jira or Discord server running in a container has no host path to give,
and demanding one would make the container case impossible.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Final, Optional

from .errors import RegistryError, ValidationError
from .paths import registry_path as default_registry_path

SCHEMA_VERSION: Final = 2

#: Project ids arrive as agent-supplied tool arguments and end up in path joins
#: and JQL, so the accepted shape is deliberately narrow.
PROJECT_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

DEFAULT_BOARD_DIRS: Final = (".claude/board", ".agents/board")


def validate_project_id(project_id: str) -> str:
    """Return *project_id* if it is well-formed, else raise.

    Rejecting ``../`` and friends here means every downstream path join and
    query has already been made safe by construction.
    """
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.match(project_id):
        raise ValidationError(
            f"Invalid project id: {project_id!r}",
            remediation=(
                "Project ids are lowercase letters, digits, '-' and '_', "
                "start with a letter or digit, and are at most 64 characters."
            ),
        )
    return project_id


@dataclass(frozen=True)
class JiraIdentity:
    """Which Jira, as whom, for which project key."""

    url: str
    email: str
    project_key: str
    credential: str
    """A secret *reference*, resolved at startup — never a token."""


@dataclass(frozen=True)
class DiscordIdentity:
    """Which Discord channel this project's approvals belong to."""

    channel_id: str
    credential: str | None = None
    """Optional per-project bot token reference; the daemon's own is the default."""


@dataclass(frozen=True)
class ProjectConfig:
    """One project's complete identity, as recorded in the registry."""

    project_id: str
    path: Optional[str] = None
    git_root: Optional[str] = None
    description: str = ""
    jira: Optional[JiraIdentity] = None
    discord: Optional[DiscordIdentity] = None
    board_dir: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def require_path(self, reason: str) -> str:
        """Return the checkout path, or explain why this project needs one."""
        if not self.path:
            raise RegistryError(
                f"Project {self.project_id!r} has no 'path', which {reason} requires.",
                remediation=(
                    f"Add a 'path' for {self.project_id} in the registry. "
                    "Servers that only talk to Jira or Discord do not need one, "
                    "which is why it is optional."
                ),
            )
        return self.path


def _parse_jira(data: Any) -> Optional[JiraIdentity]:
    if not isinstance(data, dict):
        return None
    return JiraIdentity(
        url=str(data.get("url", "")).rstrip("/"),
        email=str(data.get("email", "")),
        project_key=str(data.get("project_key", "")),
        credential=str(data.get("credential", "")),
    )


def _parse_discord(data: Any) -> Optional[DiscordIdentity]:
    if not isinstance(data, dict):
        return None
    channel_id = data.get("channel_id")
    if channel_id is None:
        return None
    credential = data.get("credential")
    return DiscordIdentity(
        channel_id=str(channel_id),
        credential=str(credential) if credential else None,
    )


def _parse_board_dir(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        board = data.get("dir")
        return str(board) if board else None
    return None


def parse_project(project_id: str, data: Dict[str, Any]) -> ProjectConfig:
    """Build a :class:`ProjectConfig` from one registry entry.

    Unknown keys are preserved in ``raw`` rather than dropped, so a newer
    registry written by a newer release still round-trips through older code.
    """
    return ProjectConfig(
        project_id=project_id,
        path=str(data["path"]) if data.get("path") else None,
        git_root=str(data["git_root"]) if data.get("git_root") else None,
        description=str(data.get("description", "")),
        jira=_parse_jira(data.get("jira")),
        discord=_parse_discord(data.get("discord")),
        board_dir=_parse_board_dir(data.get("board")),
        raw=data,
    )


class ProjectRegistry:
    """Read/write access to the registry file.

    The dict-returning methods are the original API and keep their shapes;
    :meth:`get_project_config` is the typed view that new code should use.
    """

    def __init__(self, registry_path: Optional[str] = None) -> None:
        self.registry_path = registry_path or str(default_registry_path())

    # -- raw access -------------------------------------------------------

    def _read_document(self) -> Dict[str, Any]:
        if not os.path.exists(self.registry_path):
            return {}
        try:
            with open(self.registry_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, IOError):
            # A corrupt registry reads as empty rather than raising: this is
            # called during startup, and the resulting "unknown project" error
            # from a tool call is far more useful to an agent than a server
            # that never appears. core.doctor reports the real cause.
            return {}
        return data if isinstance(data, dict) else {}

    def _load_registry(self) -> Dict[str, Dict[str, Any]]:
        """Return the project map, upgrading a v1 document in memory."""
        document = self._read_document()
        if not document:
            return {}

        if "projects" in document and isinstance(document["projects"], dict):
            projects = document["projects"]
        else:
            # v1: the document *is* the project map.
            projects = document

        return {
            key: value for key, value in projects.items() if isinstance(value, dict)
        }

    def _save_registry(self, data: Dict[str, Dict[str, Any]]) -> None:
        """Write the project map, preserving whichever schema is already in use."""
        directory = os.path.dirname(self.registry_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        existing = self._read_document()
        is_v2 = "projects" in existing and isinstance(existing.get("projects"), dict)
        document: Dict[str, Any] = (
            {**existing, "version": SCHEMA_VERSION, "projects": data} if is_v2 else data
        )

        with open(self.registry_path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=4)

    # -- original API -----------------------------------------------------

    def get_projects(self) -> Dict[str, Dict[str, Any]]:
        """Return all registered projects."""
        return self._load_registry()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Return details for a specific project, or ``None``."""
        return self._load_registry().get(project_id)

    def add_project(self, project_id: str, path: str, description: str = "") -> None:
        """Add or update a project in the registry."""
        if not os.path.isabs(path):
            raise ValueError(f"Project path must be absolute: {path}")
        validate_project_id(project_id)

        projects = self._load_registry()
        existing = projects.get(project_id, {})
        projects[project_id] = {**existing, "path": path, "description": description}
        self._save_registry(projects)

    def remove_project(self, project_id: str) -> bool:
        """Remove a project. True if it was there, False otherwise."""
        projects = self._load_registry()
        if project_id in projects:
            del projects[project_id]
            self._save_registry(projects)
            return True
        return False

    # -- typed API --------------------------------------------------------

    def schema_version(self) -> int:
        """The version declared by the file; 1 when it predates the field."""
        document = self._read_document()
        version = document.get("version")
        return int(version) if isinstance(version, int) else 1

    def project_ids(self) -> list[str]:
        return sorted(self._load_registry())

    def get_project_config(self, project_id: str) -> ProjectConfig:
        """Return the typed identity for *project_id*, or explain how to add it."""
        validate_project_id(project_id)
        data = self._load_registry().get(project_id)
        if data is None:
            known = self.project_ids()
            raise RegistryError(
                f"Unknown project {project_id!r}.",
                remediation=(
                    f"Register it with: drunken-register {project_id} <absolute-path>. "
                    + (
                        f"Currently registered: {', '.join(known)}."
                        if known
                        else f"The registry at {self.registry_path} has no projects yet."
                    )
                ),
                details={"registry_path": self.registry_path},
            )
        return parse_project(project_id, data)
