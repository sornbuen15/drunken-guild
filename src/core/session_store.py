"""Local storage for Hub session metadata; transcripts are never persisted here."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .paths import (
    ENV_SESSION_METADATA,
    ensure_home,
    secure_file,
    session_metadata_path,
)

SCHEMA_VERSION = 1
SESSION_FIELDS = (
    "session_id",
    "agent",
    "project_id",
    "project_path",
    "reported_task",
    "started_at",
    "updated_at",
)
SESSION_FIELD_SET = frozenset(SESSION_FIELDS)
REQUIRED_FIELDS = frozenset({"session_id", "agent"})


class SessionMetadataError(ValueError):
    """The local session metadata file does not match its supported schema."""


def _path(path: str | os.PathLike[str] | None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    return session_metadata_path().path


def _normalize_session(session: Mapping[str, Any]) -> dict[str, object]:
    """Validate and copy the allowlisted metadata fields only."""
    unknown = set(session) - SESSION_FIELD_SET
    if unknown:
        raise SessionMetadataError(
            "Session metadata contains unsupported fields: "
            + ", ".join(sorted(str(field) for field in unknown))
        )
    missing = REQUIRED_FIELDS - set(session)
    if missing:
        raise SessionMetadataError(
            "Session metadata is missing required fields: " + ", ".join(sorted(missing))
        )

    normalized: dict[str, object] = {}
    for field in SESSION_FIELDS:
        value = session.get(field)
        if value is not None and not isinstance(value, str):
            raise SessionMetadataError(
                f"Session metadata field {field!r} must be text or null."
            )
        normalized[field] = value
    if not normalized["session_id"] or not normalized["agent"]:
        raise SessionMetadataError(
            "Session metadata session_id and agent must not be empty."
        )
    return normalized


def load_session_metadata(
    path: str | os.PathLike[str] | None = None,
) -> list[dict[str, object]]:
    """Read metadata from local state without contacting an agent or network service."""
    metadata_path = _path(path)
    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionMetadataError(
            f"Could not read session metadata: {metadata_path}"
        ) from exc

    if not isinstance(document, dict) or document.get("version") != SCHEMA_VERSION:
        raise SessionMetadataError(
            "Session metadata file has an unsupported schema version."
        )
    if set(document) != {"version", "sessions"}:
        raise SessionMetadataError(
            "Session metadata file contains unsupported top-level fields."
        )
    sessions = document.get("sessions")
    if not isinstance(sessions, list):
        raise SessionMetadataError(
            "Session metadata file must contain a sessions list."
        )
    if not all(isinstance(session, dict) for session in sessions):
        raise SessionMetadataError("Each stored session must be an object.")
    normalized = [_normalize_session(session) for session in sessions]
    session_ids = [session["session_id"] for session in normalized]
    if len(session_ids) != len(set(session_ids)):
        raise SessionMetadataError(
            "Session metadata file contains duplicate session ids."
        )
    return normalized


def save_session_metadata(
    sessions: Sequence[Mapping[str, Any]],
    path: str | os.PathLike[str] | None = None,
) -> Path:
    """Atomically persist metadata fields only, outside project source control."""
    normalized = [_normalize_session(session) for session in sessions]
    session_ids = [session["session_id"] for session in normalized]
    if len(session_ids) != len(set(session_ids)):
        raise SessionMetadataError("Session metadata contains duplicate session ids.")
    metadata_path = _path(path)
    if path is None and not os.environ.get(ENV_SESSION_METADATA):
        ensure_home()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    document = {"version": SCHEMA_VERSION, "sessions": normalized}
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{metadata_path.name}.", suffix=".tmp", dir=metadata_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, metadata_path)
        secure_file(metadata_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return metadata_path
