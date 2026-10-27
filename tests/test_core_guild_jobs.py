from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core import guild_jobs


def test_monitor_keeps_subagent_task_and_parent_without_transcript() -> None:
    job: dict[str, Any] = {
        "children": {},
        "session_id": None,
        "activity": "starting",
        "result": "",
    }
    guild_jobs.observe(
        job,
        "Claude Code",
        {
            "type": "assistant",
            "parent_tool_use_id": None,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "child-alpha",
                        "name": "Agent",
                        "input": {
                            "description": "Review tests",
                            "prompt": "PRIVATE TRANSCRIPT",
                            "subagent_type": "reviewer",
                        },
                    }
                ]
            },
        },
    )
    guild_jobs.observe(
        job,
        "Claude Code",
        {
            "type": "assistant",
            "parent_tool_use_id": "child-alpha",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "read-alpha",
                        "name": "Read",
                        "input": {"file_path": "PRIVATE PATH"},
                    }
                ]
            },
        },
    )
    child = job["children"]["child-alpha"]
    assert child["task"] == "Review tests"
    assert child["activity"] == "Read"
    assert "PRIVATE" not in str(job)
    guild_jobs.observe(
        job,
        "Claude Code",
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "child-alpha",
                        "content": "PRIVATE RESULT",
                    }
                ]
            },
        },
    )
    assert child["status"] == "completed"


def test_codex_events_do_not_call_started_work_completed() -> None:
    job: dict[str, Any] = {
        "children": {},
        "session_id": None,
        "activity": "starting",
        "result": "",
    }
    guild_jobs.observe(job, "Codex", {"type": "thread.started", "thread_id": "alpha"})
    guild_jobs.observe(
        job,
        "Codex",
        {
            "type": "item.started",
            "item": {"type": "command_execution", "command": "PRIVATE COMMAND"},
        },
    )
    assert job["session_id"] == "alpha"
    assert job["activity"] == "command_execution"
    assert "PRIVATE" not in str(job)
    guild_jobs.observe(
        job,
        "Codex",
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Checked the tests"},
        },
    )
    assert job["result"] == "Checked the tests"


def test_queue_validates_project_and_deduplicates_submission(tmp_path: Path) -> None:
    manager = guild_jobs.JobManager(
        tmp_path / "state", {"alpha": tmp_path}, start_worker=False
    )
    try:
        with pytest.raises(ValueError, match="project"):
            manager.submit(
                {
                    "project_id": "unknown",
                    "provider": "Codex",
                    "prompt": "Check tests",
                    "request_id": "alpha",
                }
            )
        command = {
            "project_id": "alpha",
            "provider": "Codex",
            "prompt": "Check tests",
            "request_id": "alpha",
        }
        first = manager.submit(command)
        assert manager.submit(command)["id"] == first["id"]
        assert len(manager.snapshot()) == 1
        with pytest.raises(ValueError, match="request"):
            manager.submit({**command, "prompt": "Different work"})
        assert manager.cancel(first["id"])["status"] == "cancelled"
    finally:
        manager.close()


def test_restart_marks_unfinished_work_interrupted_instead_of_replaying(
    tmp_path: Path,
) -> None:
    manager = guild_jobs.JobManager(
        tmp_path / "state", {"alpha": tmp_path}, start_worker=False
    )
    job = manager.submit(
        {
            "project_id": "alpha",
            "provider": "Codex",
            "prompt": "Check tests",
            "request_id": "alpha",
        }
    )
    manager.close()
    recovered = guild_jobs.JobManager(
        tmp_path / "state", {"alpha": tmp_path}, start_worker=False
    )
    try:
        assert recovered.snapshot()[0]["id"] == job["id"]
        assert recovered.snapshot()[0]["status"] == "interrupted"
    finally:
        recovered.close()


def test_followup_cannot_switch_agent_or_project(tmp_path: Path) -> None:
    manager = guild_jobs.JobManager(
        tmp_path / "state", {"alpha": tmp_path, "beta": tmp_path}, start_worker=False
    )
    try:
        parent = manager.submit(
            {
                "project_id": "alpha",
                "provider": "Codex",
                "prompt": "Check tests",
                "request_id": "alpha",
            }
        )
        manager.jobs[0].update(
            status="completed", session_id="session-alpha", workspace=str(tmp_path)
        )
        for changes in ({"project_id": "beta"}, {"provider": "Claude Code"}):
            with pytest.raises(ValueError, match="same project and agent"):
                manager.submit(
                    {
                        "project_id": "alpha",
                        "provider": "Codex",
                        "prompt": "Continue",
                        "parent_id": parent["id"],
                        "request_id": "beta",
                        **changes,
                    }
                )
    finally:
        manager.close()


def test_permission_denial_is_not_success() -> None:
    job: dict[str, Any] = {"children": {}}
    guild_jobs.observe(
        job,
        "Claude Code",
        {
            "type": "result",
            "result": "Cannot run command",
            "permission_denials": [{"tool_name": "Bash"}],
        },
    )
    assert job["needs_attention"] is True


def test_codex_subagent_state_comes_from_reported_agent_state() -> None:
    job: dict[str, Any] = {"children": {}}
    guild_jobs.observe(
        job,
        "Codex",
        {
            "type": "item.completed",
            "item": {
                "type": "collab_tool_call",
                "tool": "spawn_agent",
                "sender_thread_id": "parent-alpha",
                "receiver_thread_ids": ["child-beta"],
                "prompt": "Review the fixture",
                "agents_states": {"child-beta": {"status": "running"}},
            },
        },
    )
    assert job["children"]["child-beta"]["status"] == "running"
    assert job["children"]["child-beta"]["parent_id"] == "parent-alpha"
