# mypy: ignore-errors
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from service.daemon_client import call_daemon


@pytest.mark.asyncio
async def test_call_daemon_round_trip() -> None:
    mock_reader = AsyncMock()
    mock_reader.readline = AsyncMock(return_value=b'{"status": "approved"}\n')
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.wait_closed = AsyncMock()

    with patch(
        "service.daemon_client.asyncio.open_unix_connection",
        AsyncMock(return_value=(mock_reader, mock_writer)),
    ):
        result = await call_daemon({"cmd": "request_boss_approval"}, "/tmp/x.sock", 5)

    assert result == {"status": "approved"}
    mock_writer.write.assert_called_once()
    mock_writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_call_daemon_empty_response_raises() -> None:
    mock_reader = AsyncMock()
    mock_reader.readline = AsyncMock(return_value=b"")
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.wait_closed = AsyncMock()

    with patch(
        "service.daemon_client.asyncio.open_unix_connection",
        AsyncMock(return_value=(mock_reader, mock_writer)),
    ):
        with pytest.raises(ConnectionError):
            await call_daemon({"cmd": "request_boss_approval"}, "/tmp/x.sock", 5)
