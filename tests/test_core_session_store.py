from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import hub
from core.paths import (
    ENV_HOME,
    ENV_SESSION_METADATA,
    is_group_or_world_accessible,
    is_windows,
    session_metadata_path,
)
from core.session_store import (
    SESSION_FIELDS,
    SessionMetadataError,
    load_session_metadata,
    save_session_metadata,
)


def _session() -> dict[str, str]:
    return {
        "session_id": "session-alpha",
        "agent": "Codex",
        "project_id": "alpha",
        "project_path": "/work/alpha",
        "reported_task": "Review the local changes",
        "started_at": "2026-10-17T09:00:00Z",
        "updated_at": "2026-10-17T09:05:00Z",
    }


def test_default_metadata_path_is_outside_project_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_state = tmp_path / "machine-state"
    project = tmp_path / "checkout"
    project.mkdir()
    monkeypatch.setenv(ENV_HOME, str(machine_state))
    monkeypatch.delenv(ENV_SESSION_METADATA, raising=False)

    metadata_path = session_metadata_path().path

    assert metadata_path == machine_state / "sessions.json"
    assert project not in metadata_path.parents


def test_metadata_round_trips_offline_without_transcript_fields(tmp_path: Path) -> None:
    metadata_path = tmp_path / "machine-state" / "sessions.json"

    saved_path = save_session_metadata([_session()], metadata_path)

    document = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_path == metadata_path
    assert document["version"] == 1
    assert set(document["sessions"][0]) == set(SESSION_FIELDS)
    assert load_session_metadata(metadata_path) == [document["sessions"][0]]
    assert "transcript" not in saved_path.read_text(encoding="utf-8")
    if is_windows():
        assert is_group_or_world_accessible(saved_path) is False


def test_store_rejects_transcript_fields_instead_of_persisting_them(
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "sessions.json"
    session = _session() | {"transcript": "private conversation text"}

    with pytest.raises(SessionMetadataError, match="unsupported fields"):
        save_session_metadata([session], metadata_path)

    assert not metadata_path.exists()


def test_hub_reads_saved_metadata_from_local_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(
        json.dumps({"version": 2, "projects": {}}), encoding="utf-8"
    )
    metadata_path = tmp_path / "machine-state" / "sessions.json"
    save_session_metadata([_session()], metadata_path)
    monkeypatch.setenv(ENV_SESSION_METADATA, str(metadata_path))

    assert hub.main(["--registry", str(registry_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["sessions"][0]["session_id"] == "session-alpha"
    assert payload["sessions"][0]["agent"] == "Codex"


def test_hub_reports_invalid_local_metadata_without_exposing_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(
        json.dumps({"version": 2, "projects": {}}), encoding="utf-8"
    )
    metadata_path = tmp_path / "sessions.json"
    metadata_path.write_text(
        json.dumps(
            {
                "version": 1,
                "sessions": [{**_session(), "transcript": "private conversation text"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_SESSION_METADATA, str(metadata_path))

    assert hub.main(["--registry", str(registry_path), "--json"]) == 2

    captured = capsys.readouterr()
    assert "unsupported fields" in captured.err
    assert "private conversation text" not in captured.err
    assert captured.out == ""
