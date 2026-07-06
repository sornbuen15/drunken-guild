# mypy: ignore-errors
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from service.discord_listener import (
    main,
    on_message,
    on_reaction_add,
    on_ready,
    outbox_message_map,
    watch_outbox,
)


@pytest.mark.anyio
@mock.patch("service.discord_listener.client")  # type: ignore[misc]
async def test_on_ready(mock_client: Any) -> None:
    mock_client.user = "test_user"
    await on_ready()


@pytest.mark.anyio
@mock.patch("service.discord_listener.agent_runner")  # type: ignore[misc]
async def test_on_reaction_add(mock_runner: Any) -> None:
    user = mock.MagicMock()
    reaction = mock.MagicMock()

    # Bot user
    user.bot = True
    await on_reaction_add(reaction, user)

    # Reset map
    outbox_message_map.clear()

    # Outbox message 👍
    user.bot = False
    reaction.message.id = 999
    outbox_message_map[999] = "req_test"
    reaction.emoji = "👍"
    reaction.message.reply = AsyncMock()

    with patch("os.makedirs"):
        with patch("builtins.open", mock_open()):
            await on_reaction_add(reaction, user)

    reaction.message.reply.assert_called_once_with("Boss has **approved** the request.")
    assert 999 not in outbox_message_map

    # Not cross
    user.bot = False
    reaction.emoji = "✅"
    await on_reaction_add(reaction, user)

    # Cross, but no current_status_msg
    reaction.emoji = "❌"
    mock_runner.current_status_msg = None
    await on_reaction_add(reaction, user)

    # Cross, with current_status_msg, diff id
    mock_msg = mock.MagicMock()
    mock_msg.id = 1
    mock_runner.current_status_msg = mock_msg
    reaction.message.id = 2
    await on_reaction_add(reaction, user)

    # Cross, matching id, not busy
    reaction.message.id = 1
    mock_runner.is_busy.return_value = False
    await on_reaction_add(reaction, user)

    # Cross, matching id, busy
    mock_runner.is_busy.return_value = True
    mock_runner.cancel_current_task = mock.AsyncMock()
    await on_reaction_add(reaction, user)
    mock_runner.cancel_current_task.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_listener.DiscordRouter")  # type: ignore[misc]
async def test_on_message(mock_router: Any) -> None:
    import service.discord_listener as dl

    dl.router = None

    msg = mock.MagicMock()
    mock_inst = mock.MagicMock()
    mock_inst.route = mock.AsyncMock()
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
@patch("service.discord_listener.os.path.exists")
@patch("service.discord_listener.client")
async def test_watch_outbox(mock_client: Any, mock_exists: Any) -> None:
    # No file
    mock_exists.return_value = False
    await watch_outbox()

    # File exists, invalid json
    mock_exists.return_value = True
    with patch("builtins.open", mock_open(read_data="invalid json")):
        await watch_outbox()

    # File exists, valid json
    valid_data = '{"req_1": {"question": "Can I delete?"}}'
    mock_channel = AsyncMock()
    mock_client.get_channel.return_value = mock_channel

    mock_msg = MagicMock()
    mock_msg.id = 123
    mock_msg.add_reaction = AsyncMock()
    mock_channel.send.return_value = mock_msg

    with patch("builtins.open", mock_open(read_data=valid_data)):
        await watch_outbox()

    mock_channel.send.assert_called_once()
    mock_msg.add_reaction.assert_any_call("👍")
    assert outbox_message_map[123] == "req_1"

    # Run again, should not send again because req_1 is in map
    mock_channel.send.reset_mock()
    with patch("builtins.open", mock_open(read_data=valid_data)):
        await watch_outbox()
    mock_channel.send.assert_not_called()
    outbox_message_map.clear()
