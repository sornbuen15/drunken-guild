"""Read live Claude Code sessions without storing conversation content."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 5


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registration(
    cwd: Any, projects: list[tuple[str, str]], registry_known: bool
) -> tuple[str, str | None]:
    if not isinstance(cwd, str) or not cwd.strip():
        return "unknown", None
    try:
        candidate = Path(cwd).expanduser().resolve()
        roots = sorted(
            (
                (project_id, Path(path).expanduser().resolve())
                for project_id, path in projects
                if path
            ),
            key=lambda item: len(item[1].parts),
            reverse=True,
        )
        for project_id, root in roots:
            try:
                candidate.relative_to(root)
                return "registered", project_id
            except ValueError:
                continue
    except (OSError, RuntimeError, ValueError):
        return "unknown", None
    return ("unregistered", None) if registry_known else ("unknown", None)


def discover_claude_sessions(
    projects: list[tuple[str, str]],
    registry_known: bool = True,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Query Claude's active-session interface and normalize safe fields only."""
    observed_at = _observed_at()
    executable = shutil.which("claude")
    if executable is None:
        return [], [
            {
                "provider": "Claude Code",
                "status": "unavailable",
                "observed_at": observed_at,
                "session_count": None,
            }
        ]

    try:
        result = subprocess.run(
            [executable, "agents", "--json"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired):
        return [], [
            {
                "provider": "Claude Code",
                "status": "error",
                "observed_at": observed_at,
                "session_count": None,
            }
        ]

    if result.returncode != 0:
        status = "error"
        records: list[Any] = []
    else:
        try:
            payload = json.loads(result.stdout)
            if not isinstance(payload, list) or not all(
                isinstance(record, dict) for record in payload
            ):
                raise ValueError("Expected a JSON array of session objects")
            records = payload
            status = "available"
        except (json.JSONDecodeError, ValueError):
            records = []
            status = "error"

    sessions: list[dict[str, object]] = []
    for record in records:
        registration, project_id = _registration(
            record.get("cwd"), projects, registry_known
        )
        raw_activity = record.get("status")
        activity = raw_activity if raw_activity in ("idle", "busy") else "unknown"
        session_id = record.get("sessionId")
        started_at = record.get("startedAt")
        sessions.append(
            {
                "session_id": session_id if isinstance(session_id, str) else None,
                "provider": "Claude Code",
                "kind": record.get("kind")
                if isinstance(record.get("kind"), str)
                else None,
                "project_path": (
                    record.get("cwd") if isinstance(record.get("cwd"), str) else None
                ),
                "project_id": project_id,
                "registration": registration,
                "activity": activity,
                "started_at": started_at if isinstance(started_at, str) else None,
                "source": "claude agents --json",
                "observed_at": observed_at,
            }
        )
    return sessions, [
        {
            "provider": "Claude Code",
            "status": status,
            "observed_at": observed_at,
            "session_count": len(sessions) if status == "available" else None,
        }
    ]
