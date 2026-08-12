# mypy: ignore-errors
from unittest.mock import AsyncMock, patch

import pytest

from discord_mcp.server import (
    check_approvals,
    request_boss_approval,
    request_boss_approval_async,
)


@pytest.mark.asyncio
async def test_request_boss_approval_daemon_not_running() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=False):
        res = await request_boss_approval("Delete file", "cleanup", "DT-1")
    assert "unavailable" in res
    assert "not running" in res
    # Must degrade to "ask directly", not silently permit skipping approval.
    assert "ask the Boss directly" in res


@pytest.mark.asyncio
async def test_request_boss_approval_approved() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch(
            "discord_mcp.server.call_daemon",
            AsyncMock(return_value={"status": "approved"}),
        ):
            res = await request_boss_approval("Delete file", "cleanup", "DT-1")
    assert res == "Approved by Boss."


@pytest.mark.asyncio
async def test_request_boss_approval_rejected() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch(
            "discord_mcp.server.call_daemon",
            AsyncMock(return_value={"status": "rejected"}),
        ):
            res = await request_boss_approval("Delete file", "cleanup", "DT-1")
    assert res == "Rejected by Boss."


@pytest.mark.asyncio
async def test_request_boss_approval_escalated() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch(
            "discord_mcp.server.call_daemon",
            AsyncMock(return_value={"status": "escalated"}),
        ):
            res = await request_boss_approval("Delete file", "cleanup", "DT-1")
    assert "escalated" in res.lower() or "No response" in res
    assert "Do not" in res


@pytest.mark.asyncio
async def test_request_boss_approval_unexpected_status() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch(
            "discord_mcp.server.call_daemon",
            AsyncMock(return_value={"status": "???"}),
        ):
            res = await request_boss_approval("Delete file", "cleanup", "DT-1")
    assert "Unexpected daemon response" in res


@pytest.mark.asyncio
async def test_request_boss_approval_daemon_unreachable() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch(
            "discord_mcp.server.call_daemon",
            AsyncMock(side_effect=ConnectionError("boom")),
        ):
            res = await request_boss_approval("Delete file", "cleanup", "DT-1")
    assert "unavailable" in res
    assert "ask the Boss directly" in res


# --- DT-232: the asynchronous pair -----------------------------------------


@pytest.mark.asyncio
async def test_async_submit_returns_a_handle_not_an_answer() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch(
            "discord_mcp.server.call_daemon",
            AsyncMock(return_value={"status": "submitted", "req_id": "req_abc"}),
        ):
            res = await request_boss_approval_async("Delete file", "cleanup", "DT-1")
    assert "req_abc" in res
    # It must tell the agent to go and do something else, not to wait here.
    assert "Park this task" in res
    assert "check_approvals" in res


@pytest.mark.asyncio
async def test_async_submit_sends_the_current_commit() -> None:
    call = AsyncMock(return_value={"status": "submitted", "req_id": "req_abc"})
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch("discord_mcp.server._head_sha", return_value="deadbee"):
            with patch("discord_mcp.server.call_daemon", call):
                await request_boss_approval_async("Delete file", "cleanup", "DT-1")
    assert call.call_args[0][0]["commit_sha"] == "deadbee"


@pytest.mark.asyncio
async def test_async_submit_still_works_outside_a_checkout() -> None:
    """No git, no SHA to bind to -- but the question must still get asked."""
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch("discord_mcp.server._head_sha", return_value=None):
            with patch(
                "discord_mcp.server.call_daemon",
                AsyncMock(return_value={"status": "submitted", "req_id": "req_abc"}),
            ):
                res = await request_boss_approval_async("Delete file", "x", "DT-1")
    assert "req_abc" in res


@pytest.mark.asyncio
async def test_check_approvals_reports_each_request() -> None:
    payload = {
        "status": "ok",
        "results": {
            "req_1": {"status": "approved", "action": "ship it", "ticket_key": "DT-1"},
            "req_2": {"status": "pending", "action": "wait", "ticket_key": "DT-2"},
        },
    }
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch("discord_mcp.server.call_daemon", AsyncMock(return_value=payload)):
            res = await check_approvals(["req_1", "req_2"])
    assert "req_1: APPROVED" in res
    assert "req_2: PENDING" in res


@pytest.mark.asyncio
async def test_check_approvals_surfaces_a_stale_approval_loudly() -> None:
    payload = {
        "status": "ok",
        "results": {
            "req_1": {
                "status": "stale",
                "action": "rm -rf build/",
                "ticket_key": "DT-1",
                "detail": "Approved against commit aaa, but you are now on bbb.",
            }
        },
    }
    with patch("discord_mcp.server.os.path.exists", return_value=True):
        with patch("discord_mcp.server.call_daemon", AsyncMock(return_value=payload)):
            res = await check_approvals(["req_1"])
    assert "STALE" in res
    assert "now on bbb" in res


@pytest.mark.asyncio
async def test_check_approvals_when_daemon_is_down() -> None:
    with patch("discord_mcp.server.os.path.exists", return_value=False):
        res = await check_approvals(["req_1"])
    assert "unavailable" in res
    assert "ask the Boss directly" in res
