from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.session_discovery import discover_claude_sessions


def test_discovers_claude_sessions_and_classifies_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered = tmp_path / "registered"
    child = registered / "nested"
    outside = tmp_path / "other"
    monkeypatch.setattr("core.session_discovery.shutil.which", lambda _: "claude-bin")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args == ["claude-bin", "agents", "--json"]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 5
        return subprocess.CompletedProcess(
            args[0],
            0,
            json.dumps(
                [
                    {
                        "sessionId": "s1",
                        "cwd": str(child),
                        "status": "busy",
                        "startedAt": "now",
                        "name": "private title",
                    },
                    {"sessionId": "s2", "cwd": str(outside), "status": "idle"},
                    {"sessionId": "s3", "status": "other"},
                ]
            ),
            "",
        )

    monkeypatch.setattr("core.session_discovery.subprocess.run", fake_run)

    sessions, sources = discover_claude_sessions([("alpha", str(registered))])

    assert [session["session_id"] for session in sessions] == ["s1", "s2", "s3"]
    assert sessions[0]["project_id"] == "alpha"
    assert sessions[0]["registration"] == "registered"
    assert sessions[0]["activity"] == "busy"
    assert sessions[1]["registration"] == "unregistered"
    assert sessions[2]["registration"] == "unknown"
    assert sessions[2]["activity"] == "unknown"
    assert all("private title" not in json.dumps(item) for item in sessions)
    assert sources[0]["status"] == "available"
    assert sources[0]["session_count"] == 3


def test_empty_success_is_distinct_from_missing_or_failed_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.session_discovery.shutil.which", lambda _: "claude-bin")
    monkeypatch.setattr(
        "core.session_discovery.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "[]", ""),
    )
    sessions, sources = discover_claude_sessions([])
    assert sessions == []
    assert sources[0]["status"] == "available"
    assert sources[0]["session_count"] == 0

    monkeypatch.setattr("core.session_discovery.shutil.which", lambda _: None)
    _, missing = discover_claude_sessions([])
    assert missing[0]["status"] == "unavailable"


def test_source_errors_are_reported_without_leaking_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.session_discovery.shutil.which", lambda _: "claude-bin")
    monkeypatch.setattr(
        "core.session_discovery.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, "secret prompt", "private error"
        ),
    )
    sessions, sources = discover_claude_sessions([])
    assert sessions == []
    assert sources[0]["status"] == "error"
    assert "secret" not in json.dumps(sources)
    assert "private" not in json.dumps(sources)


def test_registry_unavailable_keeps_registration_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.session_discovery.shutil.which", lambda _: "claude-bin")
    monkeypatch.setattr(
        "core.session_discovery.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, '[{"sessionId":"s1","cwd":"/work/project"}]', ""
        ),
    )

    sessions, _ = discover_claude_sessions([], registry_known=False)

    assert sessions[0]["registration"] == "unknown"


def test_timeout_and_malformed_json_are_source_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.session_discovery.shutil.which", lambda _: "claude-bin")

    def timeout(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args[0], timeout=5)

    monkeypatch.setattr("core.session_discovery.subprocess.run", timeout)
    sessions, sources = discover_claude_sessions([])
    assert sessions == []
    assert sources[0]["status"] == "error"

    monkeypatch.setattr(
        "core.session_discovery.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "not-json", ""),
    )
    sessions, sources = discover_claude_sessions([])
    assert sessions == []
    assert sources[0]["status"] == "error"
