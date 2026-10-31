"""Codex app-server reports child activity omitted by the CLI JSON stream."""

from __future__ import annotations

from typing import Any

from core.codex_threads import CodexThreadObserver


def test_child_thread_metadata_is_reported_without_copying_transcript(
    monkeypatch: Any,
) -> None:
    observer = object.__new__(CodexThreadObserver)
    calls: list[str] = []

    def reply(method: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append(method)
        if method == "thread/list":
            assert params["ancestorThreadId"] == "parent-alpha"
            return {
                "data": [
                    {
                        "id": "child-beta",
                        "parentThreadId": "parent-alpha",
                        "preview": "PRIVATE PROMPT",
                        "status": {"type": "notLoaded"},
                    }
                ],
                "nextCursor": None,
            }
        raise AssertionError(f"unexpected transcript request: {method}")

    monkeypatch.setattr(observer, "_request", reply)
    children = observer.children("parent-alpha")
    assert calls == ["thread/list"]
    assert children == [
        {
            "id": "child-beta",
            "parent_id": "parent-alpha",
            "task": "Task not reported",
            "status": "unknown",
            "activity": "Child thread reported",
        }
    ]
    assert "PRIVATE PROMPT" not in str(children)


def test_only_runtime_activity_states_are_reported() -> None:
    assert CodexThreadObserver._status({"type": "running"}) == "running"
    assert CodexThreadObserver._status("completed") == "completed"
    assert CodexThreadObserver._status({"type": "failed"}) == "failed"
    assert CodexThreadObserver._status({"type": "notLoaded"}) == "unknown"
    assert CodexThreadObserver._status({"type": "future-state"}) == "unknown"
