"""Codex app-server reports child activity omitted by the CLI JSON stream."""

from __future__ import annotations

from typing import Any

from core.codex_threads import CodexThreadObserver


def test_child_thread_and_activity_are_joined_without_copying_transcript(
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
                        "preview": "",
                        "status": {"type": "notLoaded"},
                    }
                ],
                "nextCursor": None,
            }
        assert method == "thread/turns/list"
        return {
            "data": [
                {
                    "items": [
                        {"type": "userMessage", "content": "PRIVATE TRANSCRIPT"},
                        {
                            "type": "subAgentActivity",
                            "agentThreadId": "child-beta",
                            "agentPath": "/root/review_tests",
                            "kind": "started",
                        },
                        {
                            "type": "subAgentActivity",
                            "agentThreadId": "child-beta",
                            "agentPath": "/root/review_tests",
                            "kind": "completed",
                        },
                    ]
                }
            ]
        }

    monkeypatch.setattr(observer, "_request", reply)
    children = observer.children("parent-alpha")
    assert calls == ["thread/list", "thread/turns/list"]
    assert children == [
        {
            "id": "child-beta",
            "parent_id": "parent-alpha",
            "task": "review tests",
            "status": "completed",
            "activity": "completed",
        }
    ]
    assert "PRIVATE TRANSCRIPT" not in str(children)
