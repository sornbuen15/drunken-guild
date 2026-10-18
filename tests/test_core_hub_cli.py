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
    monkeypatch.setattr(
        hub,
        "discover_claude_sessions",
        lambda _, **kwargs: ([], [{"provider": "Claude Code", "status": "available"}]),
    )

    assert hub.main(["--registry", str(registry_path)]) == 0

    output = capsys.readouterr().out
    assert "alpha" in output
    assert "/work/alpha" in output
    assert "Project resources:" in output
    assert "Agent access: unknown" in output
    assert "No live sessions were returned" in output
    assert "Saved session metadata:" in output


def test_empty_registry_has_clear_empty_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text('{"version": 2, "projects": {}}', encoding="utf-8")
    monkeypatch.setattr(hub, "discover_claude_sessions", lambda _, **kwargs: ([], []))

    assert hub.main(["--registry", str(registry_path)]) == 0

    output = capsys.readouterr().out
    assert "No registered projects" in output
    assert "No live sessions returned; source availability is shown above" in output


def test_json_output_identifies_hub_availability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
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
    monkeypatch.setattr(
        hub,
        "discover_claude_sessions",
        lambda _, **kwargs: (
            [{"session_id": "live-1"}],
            [{"provider": "Claude Code", "status": "available"}],
        ),
    )

    assert hub.main(["--registry", str(registry_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["projects"][0]["id"] == "alpha"
    assert payload["projects"][0]["path"] is None
    assert payload["projects"][0]["hub_enabled"] is False
    assert payload["projects"][0]["resources"]["agent_access"]["status"] == "unknown"
    assert payload["sessions"] == [{"session_id": "live-1"}]
    assert payload["session_sources"][0]["status"] == "available"
    assert payload["saved_sessions"] == []


def test_project_resource_catalog_lists_resources_and_unknown_agent_access(
    tmp_path: Path,
) -> None:
    (tmp_path / "skills" / "review").mkdir(parents=True)
    (tmp_path / "skills" / "review" / "SKILL.md").write_text(
        "---\nname: review\n---\n", encoding="utf-8"
    )

    catalog = hub.scan_project_resources(tmp_path, ["drunken-jira-mcp"])

    assert catalog["skills"] == [{"name": "review", "path": "skills/review/SKILL.md"}]
    assert catalog["mcp_integrations"] == [
        {"name": "drunken-jira-mcp", "source": "project profile"}
    ]
    assert catalog["agent_access"]["status"] == "unknown"


def test_json_catalog_uses_profile_mcp_names_without_emitting_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {
                    "alpha": {
                        "path": str(tmp_path),
                        "jira": {
                            "url": "https://jira.example.invalid",
                            "email": "alpha@example.invalid",
                            "project_key": "ALPHA",
                            "credential": "env://ALPHA_JIRA_TOKEN",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub, "discover_claude_sessions", lambda _, **kwargs: ([], []))

    assert hub.main(["--registry", str(registry_path), "--json"]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["projects"][0]["resources"]["mcp_integrations"] == [
        {"name": "drunken-jira-mcp", "source": "project profile"}
    ]
    assert "ALPHA_JIRA_TOKEN" not in output
