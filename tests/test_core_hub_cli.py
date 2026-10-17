from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import hub
from core.registry import ProjectRegistry


def test_lists_registered_projects_without_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {
                    "alpha": {"path": "/work/alpha", "hub": {"enabled": True}},
                    "beta": {"path": "/work/beta"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hub, "ProjectRegistry", lambda *_: ProjectRegistry(str(registry_path))
    )
    monkeypatch.setattr(hub, "load_sessions", lambda: [])

    assert hub.main(["--registry", str(registry_path)]) == 0

    output = capsys.readouterr().out
    assert "alpha" in output
    assert "/work/alpha" in output
    assert "No session data is available" in output


def test_empty_registry_has_clear_empty_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text('{"version": 2, "projects": {}}', encoding="utf-8")

    assert hub.main(["--registry", str(registry_path)]) == 0

    output = capsys.readouterr().out
    assert "No registered projects" in output
    assert "No session data is available" in output


def test_json_output_identifies_hub_availability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {"alpha": {"hub": {"enabled": False}}},
            }
        ),
        encoding="utf-8",
    )

    assert hub.main(["--registry", str(registry_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["projects"] == [{"id": "alpha", "path": None, "hub_enabled": False}]
    assert payload["sessions"] == []
