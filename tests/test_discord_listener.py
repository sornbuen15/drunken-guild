# mypy: ignore-errors
import asyncio
import json
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock

import pytest

from service.discord_listener import (
    _handle_socket_client,
    main,
    on_message,
    on_reaction_add,
    on_ready,
)


@pytest.mark.anyio
@mock.patch("service.discord_listener.approval_manager")
@mock.patch("service.discord_listener._start_socket_server", new_callable=AsyncMock)
@mock.patch("service.discord_listener.client")
async def test_on_ready(
    mock_client: Any, mock_start_socket: Any, mock_approval_manager: Any
) -> None:
    mock_client.user = "test_user"
    mock_approval_manager.recover_from_snapshot = AsyncMock()

    import service.discord_listener as dl

    dl._socket_server = None
    dl._socket_server_started = False
    dl._recovery_complete = False
    await on_ready()
    await asyncio.sleep(0)  # let the scheduled socket-server task actually run

    mock_start_socket.assert_called_once()
    mock_approval_manager.recover_from_snapshot.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_listener.approval_manager")
@mock.patch("service.discord_listener._start_socket_server", new_callable=AsyncMock)
@mock.patch("service.discord_listener.client")
async def test_on_ready_refire_does_not_double_start(
    mock_client: Any, mock_start_socket: Any, mock_approval_manager: Any
) -> None:
    # Regression test: discord.py can refire on_ready after a
    # session-invalidating reconnect. A second firing must not start a
    # second socket server or re-run recover_from_snapshot (which would
    # re-escalate anything still pending, posting duplicate Jira
    # comments/Discord messages).
    mock_client.user = "test_user"
    mock_approval_manager.recover_from_snapshot = AsyncMock()

    import service.discord_listener as dl

    dl._socket_server = None
    dl._socket_server_started = False
    dl._recovery_complete = False

    await on_ready()
    await asyncio.sleep(0)
    await on_ready()
    await asyncio.sleep(0)

    mock_start_socket.assert_called_once()
    mock_approval_manager.recover_from_snapshot.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_listener.approval_manager")
@mock.patch("service.discord_listener._start_socket_server", new_callable=AsyncMock)
@mock.patch("service.discord_listener.client")
async def test_on_ready_retries_recovery_after_failure_without_double_starting_socket(
    mock_client: Any, mock_start_socket: Any, mock_approval_manager: Any
) -> None:
    # Regression test: a transient failure in recover_from_snapshot() (e.g.
    # Jira/Discord API hiccup) must not permanently give up on recovery, but
    # also must not cause the socket server to be started a second time on
    # the retry — these are two independent one-shot-vs-retryable concerns.
    mock_client.user = "test_user"
    mock_approval_manager.recover_from_snapshot = AsyncMock(
        side_effect=[RuntimeError("boom"), None]
    )

    import service.discord_listener as dl

    dl._socket_server = None
    dl._socket_server_started = False
    dl._recovery_complete = False

    await on_ready()  # recovery fails
    await asyncio.sleep(0)
    await on_ready()  # reconnect retries recovery, succeeds

    assert mock_start_socket.call_count == 1  # never double-started
    assert mock_approval_manager.recover_from_snapshot.call_count == 2  # retried
    assert dl._recovery_complete is True


@pytest.mark.anyio
@mock.patch("service.discord_listener.agent_runner")
@mock.patch("service.discord_listener.approval_manager")
async def test_on_reaction_add(mock_approval_manager: Any, mock_runner: Any) -> None:
    user = mock.MagicMock()
    reaction = mock.MagicMock()

    # Bot user - ignored entirely
    user.bot = True
    await on_reaction_add(reaction, user)
    mock_approval_manager.resolve.assert_not_called()

    # Thumbs up, resolved by the manager -> reply posted
    user.bot = False
    reaction.message.id = 999
    reaction.emoji = "👍"
    reaction.message.reply = AsyncMock()
    mock_approval_manager.resolve = AsyncMock(return_value=True)

    await on_reaction_add(reaction, user)

    mock_approval_manager.resolve.assert_called_once_with(999, approved=True)
    reaction.message.reply.assert_called_once_with("Boss has **approved** the request.")

    # Thumbs down but the manager doesn't recognize the message -> no reply
    reaction.message.reply.reset_mock()
    reaction.emoji = "👎"
    mock_approval_manager.resolve = AsyncMock(return_value=False)
    await on_reaction_add(reaction, user)
    reaction.message.reply.assert_not_called()

    # Unrelated emoji
    reaction.emoji = "✅"
    await on_reaction_add(reaction, user)

    # Cross, but no current_status_msg tracked
    reaction.emoji = "❌"
    mock_runner.current_status_msg = None
    await on_reaction_add(reaction, user)

    # Cross, with current_status_msg, different id
    mock_msg = mock.MagicMock()
    mock_msg.id = 1
    mock_runner.current_status_msg = mock_msg
    reaction.message.id = 2
    await on_reaction_add(reaction, user)

    # Cross, matching id, not busy
    reaction.message.id = 1
    mock_runner.is_busy.return_value = False
    await on_reaction_add(reaction, user)

    # Cross, matching id, busy -> cancels
    mock_runner.is_busy.return_value = True
    mock_runner.cancel_current_task = AsyncMock()
    await on_reaction_add(reaction, user)
    mock_runner.cancel_current_task.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_listener.DiscordRouter")
async def test_on_message(mock_router: Any) -> None:
    import service.discord_listener as dl

    dl.router = None

    msg = mock.MagicMock()
    mock_inst = mock.MagicMock()
    mock_inst.route = AsyncMock()
    mock_router.return_value = mock_inst

    await on_message(msg)
    mock_inst.route.assert_called_once_with(msg)

    # Router already initialized
    await on_message(msg)
    assert mock_inst.route.call_count == 2


@mock.patch("service.discord_listener.client")
@mock.patch("service.discord_listener.BOT_TOKEN", "fake_token")
def test_main(mock_client: Any) -> None:
    assert main() == 0
    mock_client.run.assert_called_once_with("fake_token")


@pytest.mark.anyio
@mock.patch("service.discord_listener.approval_manager")
async def test_handle_socket_client_request_boss_approval(
    mock_approval_manager: Any,
) -> None:
    mock_approval_manager.request = AsyncMock(return_value={"status": "approved"})

    reader = AsyncMock()
    reader.readline = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "cmd": "request_boss_approval",
                    "action": "a",
                    "reason": "r",
                    "ticket_key": "DT-1",
                }
            )
            + "\n"
        ).encode("utf-8")
    )
    writer = mock.MagicMock()
    writer.drain = AsyncMock()

    await _handle_socket_client(reader, writer)

    mock_approval_manager.request.assert_called_once_with("a", "r", "DT-1")
    written = writer.write.call_args[0][0]
    assert json.loads(written.decode("utf-8").strip()) == {"status": "approved"}
    writer.close.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_listener.approval_manager")
async def test_handle_socket_client_check_ticket(mock_approval_manager: Any) -> None:
    mock_approval_manager.is_pending_or_escalated.return_value = "pending"

    reader = AsyncMock()
    reader.readline = AsyncMock(
        return_value=(
            json.dumps({"cmd": "check_ticket", "ticket_key": "DT-1"}) + "\n"
        ).encode("utf-8")
    )
    writer = mock.MagicMock()
    writer.drain = AsyncMock()

    await _handle_socket_client(reader, writer)

    written = writer.write.call_args[0][0]
    assert json.loads(written.decode("utf-8").strip()) == {"status": "pending"}


@pytest.mark.anyio
async def test_handle_socket_client_unknown_cmd() -> None:
    reader = AsyncMock()
    reader.readline = AsyncMock(
        return_value=(json.dumps({"cmd": "nonsense"}) + "\n").encode("utf-8")
    )
    writer = mock.MagicMock()
    writer.drain = AsyncMock()

    await _handle_socket_client(reader, writer)

    written = writer.write.call_args[0][0]
    payload = json.loads(written.decode("utf-8").strip())
    assert payload["status"] == "error"


@pytest.mark.anyio
async def test_handle_socket_client_empty_line() -> None:
    reader = AsyncMock()
    reader.readline = AsyncMock(return_value=b"")
    writer = mock.MagicMock()

    await _handle_socket_client(reader, writer)
    writer.write.assert_not_called()
