# mypy: ignore-errors
from unittest.mock import AsyncMock, patch

import pytest
from discord_mcp.server import request_boss_approval


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
