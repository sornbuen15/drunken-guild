from unittest import mock

import discord
import pytest
from service.discord_router import (
    DiscordRouter,
    _build_agent_suffix,
    _dispatch_single_agent,
    _dispatch_swarm,
    _handle_conversational_response,
    _handle_detail_command,
    _handle_reply_continuation,
    _handle_slash_command,
    _parse_router_response,
)
from service.discord_runner import AgentRunner


class MockMessage:
    def __init__(self, content=""):
        self.content = content
        self.channel = mock.AsyncMock()
        self.author = mock.MagicMock()
        self.author.bot = False
        self.author.mention = "@user"
        self.author.name = "user"
        self.mentions = []
        self.reference = None


@pytest.mark.anyio
@mock.patch("service.discord_router.os.path.exists")
@mock.patch("service.discord_router.os.path.getsize")
async def test_handle_detail_command(mock_getsize, mock_exists):
    msg = MockMessage()

    mock_exists.return_value = True
    mock_getsize.return_value = 100
    with mock.patch("service.discord_router.discord.File"):
        await _handle_detail_command(msg)
    msg.channel.send.assert_called_once()

    msg.channel.send.reset_mock()
    msg.channel.send.side_effect = [Exception("err"), None]
    with mock.patch("service.discord_router.discord.File"):
        await _handle_detail_command(msg)

    msg.channel.send.reset_mock()
    msg.channel.send.side_effect = None
    mock_exists.return_value = False
    await _handle_detail_command(msg)
    assert "No raw execution history" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
@mock.patch("glob.glob")
@mock.patch("os.path.getmtime")
async def test_handle_slash_command(mock_mtime, mock_glob):
    runner = AgentRunner()
    msg = MockMessage()

    # /help
    await _handle_slash_command(runner, msg, "/help")
    assert "How to order quests" in msg.channel.send.call_args[0][0]

    # /status IDLE
    await _handle_slash_command(runner, msg, "/status")
    assert "IDLE" in msg.channel.send.call_args[0][0]

    # /status BUSY with logs
    runner.current_process = mock.MagicMock()
    runner.current_process.returncode = None
    mock_glob.return_value = ["file1.log"]
    mock_mtime.return_value = 1
    with mock.patch(
        "builtins.open", new_callable=mock.mock_open, read_data="log line\n"
    ):
        await _handle_slash_command(runner, msg, "/status")
        assert "BUSY" in msg.channel.send.call_args[0][0]

    # /status BUSY read err
    with mock.patch("builtins.open", side_effect=Exception("err")):
        await _handle_slash_command(runner, msg, "/status")
        assert "couldn't read log" in msg.channel.send.call_args[0][0]

    # /status BUSY no logs
    mock_glob.return_value = []
    await _handle_slash_command(runner, msg, "/status")
    assert "waiting for first log entry" in msg.channel.send.call_args[0][0]

    # /stop
    with mock.patch("subprocess.run") as mock_run:
        await _handle_slash_command(runner, msg, "/stop")
        mock_run.assert_called_once()

    # /list-cmd
    await _handle_slash_command(runner, msg, "/list-cmd")
    assert "menu of quick commands" in msg.channel.send.call_args[0][0]

    # other slash cmd
    runner.run_command_async = mock.AsyncMock()
    await _handle_slash_command(runner, msg, "/refine")
    runner.run_command_async.assert_called_once()


def test_parse_router_response():
    # Valid json in block
    res = _parse_router_response('Some text {"key": "val"} more', "")
    assert res == {"key": "val"}

    # Fallback to pure json
    res = _parse_router_response('{"key2": "val2"}', "")
    assert res == {"key2": "val2"}

    # Exceptions
    res = _parse_router_response("invalid json", "")
    assert res["is_task"] == False

    # Regex fallback task
    res = _parse_router_response('invalid json "target_agent":"devops"', "cmd")
    assert res["target_agent"] == "devops"

    # Regex fallback agy
    res = _parse_router_response('invalid json "agy_response":"hello"', "cmd")
    assert res["agy_response"] == "hello"


def test_build_agent_suffix():
    meta = {"name": "test", "job": "job", "description": "desc"}
    res = _build_agent_suffix(meta)
    assert "test" in res
    assert "job" in res


@pytest.mark.anyio
@mock.patch("service.discord_router.ProjectRegistry")
async def test_dispatch_swarm(mock_registry):
    runner = mock.MagicMock()
    runner.run_command_async = mock.AsyncMock()
    msg = MockMessage()

    mock_proj = mock.MagicMock()
    mock_proj.get_project.return_value = {"path": "/fake/path"}
    mock_registry.return_value = mock_proj

    router_data = {
        "sub_tasks": [{"target_agent": "devops", "prompt": "do something"}],
        "target_project": "proj",
    }

    with mock.patch("service.discord_router.log_activity"):
        await _dispatch_swarm(runner, router_data, "content", msg)

    msg.channel.send.assert_called_once()
    runner.run_command_async.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_router.ProjectRegistry")
async def test_dispatch_single_agent(mock_registry):
    runner = mock.MagicMock()
    runner.run_command_async = mock.AsyncMock()
    msg = MockMessage()

    mock_proj = mock.MagicMock()
    mock_proj.get_project.return_value = {"path": "/fake/path"}
    mock_registry.return_value = mock_proj

    router_data = {
        "target_agent": "qa",
        "refined_prompt": "do tests",
        "target_project": "proj",
    }

    with mock.patch("service.discord_router.log_activity"):
        await _dispatch_single_agent(runner, router_data, "do tests", msg)

    runner.run_command_async.assert_called_once()


@pytest.mark.anyio
async def test_handle_conversational_response():
    msg = MockMessage()
    with mock.patch("service.discord_router.log_activity"):
        await _handle_conversational_response(
            {"agy_response": "hi"}, "direct_response", msg
        )
    msg.channel.send.assert_called_once()


@pytest.mark.anyio
async def test_handle_reply_continuation():
    runner = mock.MagicMock()
    runner.run_command_async = mock.AsyncMock()
    client = mock.MagicMock()
    client.user.id = 999

    msg = MockMessage("continue please")
    ref = mock.MagicMock()
    ref.message_id = 42
    msg.reference = ref

    orig_msg = mock.MagicMock()
    orig_msg.author = client.user
    orig_msg.content = (
        "*Reply to this message to continue working with **devops-engineer** in `proj`*"
    )
    msg.channel.fetch_message = mock.AsyncMock(return_value=orig_msg)

    with mock.patch("service.discord_router.ProjectRegistry") as mock_reg:
        mock_proj = mock.MagicMock()
        mock_proj.get_project.return_value = {"path": "/fake/path"}
        mock_reg.return_value = mock_proj

        res = await _handle_reply_continuation(client, runner, msg)
        assert res == True
        runner.run_command_async.assert_called_once()
        assert "devops-engineer" in runner.run_command_async.call_args[0][4]


@pytest.mark.anyio
@mock.patch("service.discord_router._handle_slash_command")
@mock.patch("service.discord_router._handle_reply_continuation")
@mock.patch("service.discord_router._handle_detail_command")
@mock.patch("service.discord_router._dispatch_single_agent")
async def test_router_route(mock_single, mock_detail, mock_reply, mock_slash):
    client = mock.MagicMock()
    client.user.id = 999
    runner = mock.MagicMock()
    router = DiscordRouter(client, runner, 123)

    msg = MockMessage()
    msg.channel.id = 123
    msg.mentions = [client.user]

    # 1. Bot author
    msg.author.bot = True
    await router.route(msg)
    assert not mock_slash.called
    msg.author.bot = False

    # 2. Wrong channel
    msg.channel.id = 456
    await router.route(msg)
    assert not mock_slash.called
    msg.channel.id = 123

    # 3. Not mentioned, no reference, not Dm
    msg.mentions = []
    msg.reference = None
    msg.channel.type = discord.ChannelType.text
    await router.route(msg)

    # 4. DM
    msg.channel.type = discord.ChannelType.private

    # 5. Slash command
    msg.content = "/help"
    await router.route(msg)
    mock_slash.assert_called_once()

    # 6. Detail command
    msg.content = "!detail"
    await router.route(msg)
    mock_detail.assert_called_once()

    # 7. Reply continuation
    msg.content = "continue"
    mock_reply.return_value = True
    await router.route(msg)
    mock_reply.assert_called_once()

    # 8. Deterministic single agent task
    mock_reply.return_value = False
    msg.content = "principal-engineer do something"
    with mock.patch("service.discord_router.ProjectRegistry") as mock_reg:
        mock_proj = mock.MagicMock()
        mock_proj.get_projects.return_value = {"drunken-team": {}}
        mock_reg.return_value = mock_proj

        await router.route(msg)
        mock_single.assert_called_once()

    # 9. No target agent
    msg.content = "do something without agent"
    await router.route(msg)
    # should send system message
    msg.channel.send.assert_called_once()
    assert "start your message with an agent's name" in msg.channel.send.call_args[0][0]
