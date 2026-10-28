from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from typing import Any, Iterator

import pytest

from core import dashboard


@pytest.fixture  # type: ignore[misc]
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(
        dashboard, "collect_snapshot", lambda _: dashboard.demo_snapshot()
    )
    instance = dashboard.create_server(registry_path=None, port=0)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def request(
    server: Any, path: str, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], bytes]:
    host, port = server.server_address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_snapshot_keeps_live_and_saved_records_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "projects.json"
    registry.write_text(
        json.dumps({"version": 2, "projects": {"alpha": {"path": str(tmp_path)}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "core.hub.load_sessions",
        lambda: [{"session_id": "saved-alpha", "agent": "Codex"}],
    )
    monkeypatch.setattr(
        "core.hub.discover_claude_sessions",
        lambda *_, **__: (
            [
                {
                    "session_id": "live-alpha",
                    "provider": "Claude Code",
                    "activity": "busy",
                }
            ],
            [{"provider": "Claude Code", "status": "available"}],
        ),
    )
    result = dashboard.collect_snapshot(str(registry))
    assert result["mode"] == "live"
    assert result["sessions"][0]["session_id"] == "live-alpha"
    assert result["saved_sessions"][0]["session_id"] == "saved-alpha"
    assert any(
        source["provider"] == "Codex" and source["status"] == "unsupported"
        for source in result["session_sources"]
    )


def test_demo_is_explicit_and_does_not_claim_live_evidence() -> None:
    result = dashboard.demo_snapshot()
    assert result["mode"] == "demo"
    assert result["sessions"]
    assert all(
        record["source"] == "Demonstration data" for record in result["sessions"]
    )


def test_page_and_snapshot_are_readable_only_on_loopback(server: Any) -> None:
    assert server.server_address[0] == "127.0.0.1"
    status, headers, content = request(server, "/")
    assert status == 200
    assert b"Agent workspace" in content
    assert headers["Cache-Control"] == "no-store"
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert request(server, "/api/snapshot")[0] == 200


@pytest.mark.parametrize(  # type: ignore[misc]
    "headers", [{"Host": "foreign.example"}, {"Origin": "https://foreign.example"}]
)
def test_foreign_hosts_and_origins_cannot_read_local_sessions(
    server: Any, headers: dict[str, str]
) -> None:
    assert request(server, "/api/snapshot", headers)[0] == 403


def test_unknown_assets_and_path_traversal_are_not_served(server: Any) -> None:
    assert request(server, "/../session_store.py")[0] == 404
    assert request(server, "/api/not-present")[0] == 404


def test_snapshot_failure_is_reported_without_exception_details(
    server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_: Any) -> Any:
        raise OSError("private internal details")

    monkeypatch.setattr(dashboard, "collect_snapshot", fail)
    status, _, payload = request(server, "/api/snapshot")
    assert status == 503
    assert b"private internal details" not in payload


def test_multiple_tabs_share_one_discovery_until_cache_expires(
    server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[None] = []
    clock = [0.0]

    def collect(_: Any) -> Any:
        calls.append(None)
        return dashboard.demo_snapshot()

    monkeypatch.setattr(dashboard, "collect_snapshot", collect)
    monkeypatch.setattr(dashboard, "monotonic", lambda: clock[0], raising=False)
    assert request(server, "/api/snapshot")[0] == 200
    assert request(server, "/api/snapshot")[0] == 200
    assert len(calls) == 1, (
        "Multiple dashboard tabs must not launch duplicate discovery calls"
    )
    clock[0] = 13.0
    assert request(server, "/api/snapshot")[0] == 200
    assert len(calls) == 2, (
        "Cached observations must expire instead of hiding source changes"
    )


def test_agent_inventory_separates_cli_presence_from_live_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.dashboard.shutil.which",
        lambda command: (
            f"/tools/{command}" if command in {"claude", "codex", "aider"} else None
        ),
    )
    records = dashboard.agent_inventory()
    assert {record["provider"] for record in records} == {
        "Claude Code",
        "Codex",
        "Aider",
        "Antigravity",
    }
    found = {
        record["provider"] for record in records if record["cli_status"] == "found"
    }
    assert found == {"Claude Code", "Codex", "Aider"}
    assert (
        next(record for record in records if record["provider"] == "Antigravity")[
            "cli_status"
        ]
        == "not_found"
    )
    assert all(
        "activity" not in record and "session_count" not in record for record in records
    )


def test_job_control_requires_same_origin_and_token(tmp_path: Path) -> None:
    from core.guild_jobs import JobManager

    manager = JobManager(tmp_path / "state", {"alpha": tmp_path}, start_worker=False)
    instance = dashboard.create_server(None, 0, jobs=manager)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    host, port = instance.server_address
    assert isinstance(host, str) and isinstance(port, int)
    origin = f"http://{host}:{port}"
    payload = json.dumps(
        {
            "project_id": "alpha",
            "provider": "Codex",
            "prompt": "Check tests",
            "request_id": "alpha",
        }
    )

    def post(headers: dict[str, str]) -> int:
        connection = http.client.HTTPConnection(host, port, timeout=3)
        try:
            connection.request("POST", "/api/jobs", body=payload, headers=headers)
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    try:
        status, _, body = request(instance, "/api/jobs")
        assert status == 200
        token = json.loads(body)["csrf_token"]
        assert post({"Content-Type": "application/json", "Origin": origin}) == 403
        assert (
            post(
                {
                    "Content-Type": "application/json",
                    "Origin": "https://foreign.example",
                    "X-Guild-Token": token,
                }
            )
            == 403
        )
        assert (
            post(
                {
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "X-Guild-Token": token,
                }
            )
            == 202
        )
        assert len(manager.snapshot()) == 1
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)
        manager.close()


def test_remote_origin_requires_configured_tailnet_identity() -> None:
    instance = dashboard.create_server(
        None, 0, web_origin="https://guild.example", web_user="owner@example.invalid"
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        headers = {"Host": "guild.example", "Origin": "https://guild.example"}
        assert request(instance, "/api/jobs", headers)[0] == 403
        assert (
            request(
                instance,
                "/api/jobs",
                {**headers, "Tailscale-User-Login": "other@example.invalid"},
            )[0]
            == 403
        )
        assert (
            request(
                instance,
                "/api/jobs",
                {**headers, "Tailscale-User-Login": "owner@example.invalid"},
            )[0]
            == 200
        )
        assert (
            request(
                instance,
                "/api/jobs",
                {
                    **headers,
                    "Tailscale-User-Login": "owner@example.invalid",
                    "Origin": "https://foreign.example",
                },
            )[0]
            == 403
        )
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)
