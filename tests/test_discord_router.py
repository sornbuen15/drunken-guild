# mypy: ignore-errors
import asyncio
import json
from unittest import mock

import discord
import pytest

from service.discord_router import (
    DiscordRouter,
    _build_agent_suffix,
    _build_refine_report,
    _dispatch_single_agent,
    _dispatch_swarm,
    _format_issue_list,
    _get_target_project,
    _handle_approve_command,
    _handle_conversational_response,
    _handle_detail_command,
    _handle_jira_list_command,
    _handle_next_command,
    _handle_pending_command,
    _handle_pr_list_command,
    _handle_project_command,
    _handle_qa_command,
    _handle_refine_command,
    _handle_reply_continuation,
    _handle_slash_command,
    _parse_router_response,
    _run_jira_bridge,
    _run_qa_gate_and_reply,
    _set_target_project,
    _target_project_cwd,
    _try_handle_workflow_command,
)
from service.discord_runner import AgentRunner


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


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
    assert "Agy, your system router, welcomes you" in msg.channel.send.call_args[0][0]

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

    # /stop while busy (runner.current_process still set from the BUSY case above)
    runner.cancel_current_task = mock.AsyncMock()
    with mock.patch(
        "service.discord_runner.kill_orphaned_agent_processes", return_value=[]
    ):
        await _handle_slash_command(runner, msg, "/stop")
    runner.cancel_current_task.assert_called_once()
    assert "Terminated" in msg.channel.send.call_args[0][0]

    # /stop while idle, no orphans either
    runner.current_process = None
    with mock.patch(
        "service.discord_runner.kill_orphaned_agent_processes", return_value=[]
    ):
        await _handle_slash_command(runner, msg, "/stop")
    assert "nothing to stop" in msg.channel.send.call_args[0][0]

    # /stop while idle, but an orphaned process is found and killed
    with mock.patch(
        "service.discord_runner.kill_orphaned_agent_processes", return_value=[1234]
    ):
        await _handle_slash_command(runner, msg, "/stop")
    assert "Terminated" in msg.channel.send.call_args[0][0]
    assert "orphaned" in msg.channel.send.call_args[0][0]

    # /list-cmd
    await _handle_slash_command(runner, msg, "/list-cmd")
    assert "menu of quick commands" in msg.channel.send.call_args[0][0]

    # unimplemented slash cmd falls back to the disabled message
    runner.run_command_async = mock.AsyncMock()
    await _handle_slash_command(runner, msg, "/nonexistent-command")
    runner.run_command_async.assert_not_called()
    assert "ถูกปิดใช้งาน" in msg.channel.send.call_args[0][0]


def test_parse_router_response():
    # Valid json in block
    res = _parse_router_response('Some text {"key": "val"} more', "")
    assert res == {"key": "val"}

    # Fallback to pure json
    res = _parse_router_response('{"key2": "val2"}', "")
    assert res == {"key2": "val2"}

    # Exceptions
    res = _parse_router_response("invalid json", "")
    assert res["is_task"] is False

    # Regex fallback task
    res = _parse_router_response('invalid json "target_agent":"devops"', "cmd")
    assert res["target_agent"] == "devops"

    # Regex fallback for the CLI's response key
    res = _parse_router_response('invalid json "agy_response":"hello"', "cmd")
    assert res["agy_response"] == "hello"


def test_build_agent_suffix():
    meta = {"name": "test", "job": "job", "description": "desc"}
    res = _build_agent_suffix(meta)
    assert "test" in res
    assert "job" in res
    assert "request_boss_approval" in res
    assert "SILENT WAIT PROTOCOL" not in res


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
        assert res is True
        runner.run_command_async.assert_not_called()
        msg.channel.send.assert_called_once()
        assert "ถูกปิดใช้งาน" in msg.channel.send.call_args[0][0]


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

    # 8. Any free-form, non-slash message gets the same fixed redirect to
    # /help -- free-form task commanding is disabled pending DT-94, so there
    # is nothing left to branch on (no persona/project matching).
    mock_reply.return_value = False
    msg.content = "principal-engineer do something"
    await router.route(msg)
    mock_single.assert_not_called()
    msg.channel.send.assert_called_once()
    assert "/help" in msg.channel.send.call_args[0][0]

    # 9. Same fixed redirect regardless of content.
    msg.channel.send.reset_mock()
    msg.content = "do something without agent"
    await router.route(msg)
    msg.channel.send.assert_called_once()
    assert "/help" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_run_jira_bridge_success():
    issues = [{"key": "DT-1", "summary": "s", "priority": "High"}]
    fake = FakeProcess(json.dumps(issues).encode(), b"", 0)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        result, error = await _run_jira_bridge("get-todo")
    assert error is None
    assert result == issues


@pytest.mark.anyio
async def test_run_jira_bridge_nonzero_exit():
    fake = FakeProcess(b"", b"boom", 1)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        result, error = await _run_jira_bridge("get-todo")
    assert result == []
    assert error == "boom"


@pytest.mark.anyio
async def test_run_jira_bridge_bad_json():
    fake = FakeProcess(b"not json", b"", 0)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        result, error = await _run_jira_bridge("get-todo")
    assert result == []
    assert "parse" in error


def test_format_issue_list_empty():
    assert "no issues" in _format_issue_list([], "To Do")


def test_format_issue_list_truncates_to_max_items():
    issues = [
        {"key": f"DT-{i}", "summary": "x" * 100, "priority": "High"} for i in range(12)
    ]
    text = _format_issue_list(issues, "To Do")
    assert "(12)" in text
    assert "...and 4 more" in text
    assert len(text) <= 2000
    # Long summaries are shortened, not dumped raw.
    assert "x" * 100 not in text


@pytest.mark.anyio
async def test_handle_jira_list_command_error():
    msg = MockMessage()
    with mock.patch(
        "service.discord_router._run_jira_bridge",
        mock.AsyncMock(return_value=([], "boom")),
    ):
        await _handle_jira_list_command(msg, "get-todo", "To Do")
    assert "Couldn't fetch" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_jira_list_command_success():
    msg = MockMessage()
    issues = [{"key": "DT-1", "summary": "do a thing", "priority": "High"}]
    with mock.patch(
        "service.discord_router._run_jira_bridge",
        mock.AsyncMock(return_value=(issues, None)),
    ):
        await _handle_jira_list_command(msg, "get-todo", "To Do")
    sent = msg.channel.send.call_args[0][0]
    assert "DT-1" in sent
    assert "do a thing" in sent


@pytest.mark.anyio
async def test_handle_pr_list_command_success():
    msg = MockMessage()
    prs = [{"number": 12, "title": "fix bug", "url": "https://x/12", "isDraft": False}]
    fake = FakeProcess(json.dumps(prs).encode(), b"", 0)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        await _handle_pr_list_command(msg)
    sent = msg.channel.send.call_args[0][0]
    assert "#12" in sent
    assert "fix bug" in sent


@pytest.mark.anyio
async def test_handle_pr_list_command_none_open():
    msg = MockMessage()
    fake = FakeProcess(b"[]", b"", 0)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        await _handle_pr_list_command(msg)
    assert "none open" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_pr_list_command_gh_error():
    msg = MockMessage()
    fake = FakeProcess(b"", b"gh not authenticated", 1)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        await _handle_pr_list_command(msg)
    assert "Couldn't fetch open PRs" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_pending_command_no_manager():
    msg = MockMessage()
    await _handle_pending_command(None, msg)
    assert "isn't wired up" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_pending_command_empty():
    msg = MockMessage()
    mgr = mock.MagicMock()
    mgr.list_pending.return_value = []
    await _handle_pending_command(mgr, msg)
    assert "Nothing waiting" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_pending_command_with_items():
    msg = MockMessage()
    mgr = mock.MagicMock()
    mgr.list_pending.return_value = [
        {"ticket_key": "DT-1", "action": "delete stuff", "status": "pending"},
        {"ticket_key": "DT-2", "action": "run destroy", "status": "escalated"},
    ]
    await _handle_pending_command(mgr, msg)
    sent = msg.channel.send.call_args[0][0]
    assert "DT-1" in sent
    assert "DT-2" in sent
    assert "escalated" in sent


@pytest.mark.anyio
@mock.patch("glob.glob")
@mock.patch("os.path.getmtime")
async def test_handle_slash_command_new_query_commands(mock_mtime, mock_glob):
    runner = AgentRunner()
    msg = MockMessage()

    issues = [{"key": "DT-1", "summary": "do a thing", "priority": "High"}]
    with mock.patch(
        "service.discord_router._run_jira_bridge",
        mock.AsyncMock(return_value=(issues, None)),
    ):
        for cmd in ("/tasks", "/inprogress", "/review", "/backlog"):
            msg.channel.send.reset_mock()
            await _handle_slash_command(runner, msg, cmd)
            assert "DT-1" in msg.channel.send.call_args[0][0]

    msg.channel.send.reset_mock()
    with mock.patch(
        "service.discord_router._handle_pr_list_command", mock.AsyncMock()
    ) as mock_pr:
        await _handle_slash_command(runner, msg, "/pr")
    mock_pr.assert_called_once()

    msg.channel.send.reset_mock()
    approval_manager = mock.MagicMock()
    approval_manager.list_pending.return_value = []
    await _handle_slash_command(runner, msg, "/pending", approval_manager)
    assert "Nothing waiting" in msg.channel.send.call_args[0][0]

    # /pending with no approval_manager wired up (default None)
    msg.channel.send.reset_mock()
    await _handle_slash_command(runner, msg, "/pending")
    assert "isn't wired up" in msg.channel.send.call_args[0][0]

    # /help documents the new commands
    msg.channel.send.reset_mock()
    await _handle_slash_command(runner, msg, "/help")
    help_text = msg.channel.send.call_args[0][0]
    for cmd in ("/tasks", "/inprogress", "/review", "/backlog", "/pending", "/pr"):
        assert cmd in help_text

    # /list-cmd documents the new commands too
    msg.channel.send.reset_mock()
    await _handle_slash_command(runner, msg, "/list-cmd")
    list_text = msg.channel.send.call_args[0][0]
    assert "/tasks" in list_text
    assert "/pending" in list_text
    assert "/pr" in list_text


@pytest.mark.anyio
@mock.patch("service.discord_router._handle_slash_command")
async def test_router_route_passes_approval_manager(mock_slash):
    client = mock.MagicMock()
    client.user.id = 999
    runner = mock.MagicMock()
    approval_manager = mock.MagicMock()
    router = DiscordRouter(client, runner, 123, approval_manager)

    msg = MockMessage("/pending")
    msg.channel.id = 123

    await router.route(msg)
    mock_slash.assert_called_once_with(runner, msg, "/pending", approval_manager)


# --- round 2: /project, /next, /refine, /approve, /qa ---


@pytest.fixture()
def target_project_config(tmp_path, monkeypatch):
    """Isolates both pieces of state these tests touch.

    find_config() (and therefore the target-project state file) points at
    tmp_path, and so does the registry: since DT-241 the router resolves a
    project's cwd through the registry, and a test that reads the developer's
    real ``~/.drunken/projects.json`` passes or fails depending on whose
    machine it runs on.
    """
    config_file = tmp_path / ".agents" / "discord_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("{}")

    registry_file = tmp_path / "projects.json"
    registry_file.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {"drunken-team": {"path": "/fake/drunken-team"}},
            }
        )
    )
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry_file))

    with mock.patch(
        "service.discord_router.find_config", return_value=str(config_file)
    ):
        yield tmp_path


def test_get_set_target_project_default(target_project_config):
    assert _get_target_project() == "drunken-team"


def test_set_then_get_target_project_roundtrips(target_project_config):
    _set_target_project("isac")
    assert _get_target_project() == "isac"


def test_target_project_cwd_default_comes_from_the_registry(target_project_config):
    """The default project is resolved like any other, rather than being left
    to whatever directory the daemon happened to be started in."""
    assert _target_project_cwd() == "/fake/drunken-team"


def test_target_project_cwd_is_none_when_the_default_has_no_path(
    target_project_config, tmp_path
):
    """Falling back to the daemon's own cwd is the right answer here, not an
    error: a project that only talks to Jira has no checkout to name."""
    (tmp_path / "projects.json").write_text(
        json.dumps({"version": 2, "projects": {"drunken-team": {}}})
    )
    assert _target_project_cwd() is None


def test_target_project_cwd_resolves_registered_path(target_project_config):
    _set_target_project("isac")
    with mock.patch("service.discord_router.ProjectRegistry") as mock_reg:
        mock_proj = mock.MagicMock()
        mock_proj.get_project.return_value = {"path": "/fake/isac"}
        mock_reg.return_value = mock_proj
        assert _target_project_cwd() == "/fake/isac"


def test_target_project_cwd_unregistered_project_is_none(target_project_config):
    _set_target_project("ghost-project")
    with mock.patch("service.discord_router.ProjectRegistry") as mock_reg:
        mock_proj = mock.MagicMock()
        mock_proj.get_project.return_value = None
        mock_reg.return_value = mock_proj
        assert _target_project_cwd() is None


@pytest.mark.anyio
async def test_handle_project_command_shows_current(target_project_config):
    msg = MockMessage()
    await _handle_project_command(msg, "/project")
    assert "drunken-team" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_project_command_switches_to_known_project(
    target_project_config,
):
    msg = MockMessage()
    with mock.patch("service.discord_router.ProjectRegistry") as mock_reg:
        mock_proj = mock.MagicMock()
        mock_proj.get_project.return_value = {"path": "/fake/isac"}
        mock_reg.return_value = mock_proj
        await _handle_project_command(msg, "/project isac")
    assert "isac" in msg.channel.send.call_args[0][0]
    assert _get_target_project() == "isac"


@pytest.mark.anyio
async def test_handle_project_command_rejects_unknown_project(
    target_project_config,
):
    msg = MockMessage()
    with mock.patch("service.discord_router.ProjectRegistry") as mock_reg:
        mock_proj = mock.MagicMock()
        mock_proj.get_project.return_value = None
        mock_proj.get_projects.return_value = {"drunken-team": {}, "isac": {}}
        mock_reg.return_value = mock_proj
        await _handle_project_command(msg, "/project nope")
    assert "ไม่พบโปรเจกต์" in msg.channel.send.call_args[0][0]
    # Unchanged -- still the default.
    assert _get_target_project() == "drunken-team"


@pytest.mark.anyio
async def test_handle_next_command_refuses_when_in_progress_busy():
    msg = MockMessage()
    with mock.patch(
        "service.discord_router._run_jira_bridge",
        mock.AsyncMock(return_value=([{"key": "DT-1"}], None)),
    ):
        await _handle_next_command(msg)
    assert "In Progress ค้างอยู่แล้ว" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_next_command_no_todo_left():
    msg = MockMessage()

    async def fake_bridge(action, cwd=None):
        if action == "get-in-progress":
            return [], None
        return [], None

    with mock.patch("service.discord_router._run_jira_bridge", side_effect=fake_bridge):
        await _handle_next_command(msg)
    assert "ไม่มีงานเหลือใน To Do" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_next_command_picks_top_todo_and_transitions(
    target_project_config,
):
    msg = MockMessage()

    async def fake_bridge(action, cwd=None):
        if action == "get-in-progress":
            return [], None
        return [{"key": "DT-42", "summary": "Do the thing"}], None

    with (
        mock.patch("service.discord_router._run_jira_bridge", side_effect=fake_bridge),
        mock.patch(
            "service.discord_router._transition_issue",
            mock.AsyncMock(return_value=(True, "ok")),
        ) as mock_transition,
    ):
        await _handle_next_command(msg)

    mock_transition.assert_called_once_with(
        "DT-42", "In Progress", "/fake/drunken-team"
    )
    sent = msg.channel.send.call_args[0][0]
    assert "DT-42" in sent
    assert "Do the thing" in sent


@pytest.mark.anyio
async def test_handle_next_command_transition_failure():
    msg = MockMessage()

    async def fake_bridge(action, cwd=None):
        if action == "get-in-progress":
            return [], None
        return [{"key": "DT-42", "summary": "Do the thing"}], None

    with (
        mock.patch("service.discord_router._run_jira_bridge", side_effect=fake_bridge),
        mock.patch(
            "service.discord_router._transition_issue",
            mock.AsyncMock(return_value=(False, "no such transition")),
        ),
    ):
        await _handle_next_command(msg)
    assert "ไม่สำเร็จ" in msg.channel.send.call_args[0][0]


def test_build_refine_report_promotes_and_groups():
    backlog = [
        {"key": "DT-1", "priority": "Critical"},
        {"key": "DT-2", "priority": "High"},
        {"key": "DT-3", "priority": "High"},
        {"key": "DT-4", "priority": "Low"},
    ]
    critical = [backlog[0]]
    report = _build_refine_report(backlog, critical, promoted=["DT-1"], failed=[])
    assert "DT-1" in report
    assert "High" in report and "DT-2" in report and "DT-3" in report
    assert "Low" in report and "DT-4" in report
    assert len(report) <= 2000


@pytest.mark.anyio
async def test_handle_refine_command_empty_backlog():
    msg = MockMessage()
    with mock.patch(
        "service.discord_router._run_jira_bridge",
        mock.AsyncMock(return_value=([], None)),
    ):
        await _handle_refine_command(msg)
    assert "ว่างค่ะ" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_refine_command_promotes_critical(target_project_config):
    msg = MockMessage()
    backlog = [{"key": "DT-1", "priority": "Critical"}]
    with (
        mock.patch(
            "service.discord_router._run_jira_bridge",
            mock.AsyncMock(return_value=(backlog, None)),
        ),
        mock.patch(
            "service.discord_router._transition_issue",
            mock.AsyncMock(return_value=(True, "ok")),
        ) as mock_transition,
    ):
        await _handle_refine_command(msg)
    mock_transition.assert_called_once_with("DT-1", "To Do", "/fake/drunken-team")
    assert "Auto-promoted" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_approve_command_missing_ticket_arg():
    msg = MockMessage()
    await _handle_approve_command(mock.MagicMock(), mock.MagicMock(), msg, "/approve")
    assert "ใช้แบบนี้" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_approve_command_no_manager():
    msg = MockMessage()
    await _handle_approve_command(mock.MagicMock(), None, msg, "/approve DT-1")
    assert "isn't wired up" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_approve_command_ticket_not_escalated():
    msg = MockMessage()
    approval_manager = mock.MagicMock()
    approval_manager.clear_escalated.return_value = None
    await _handle_approve_command(
        mock.MagicMock(), approval_manager, msg, "/approve DT-1"
    )
    assert "ไม่พบ escalated request" in msg.channel.send.call_args[0][0]


@pytest.mark.anyio
async def test_handle_approve_command_clears_and_redispatches():
    msg = MockMessage()
    approval_manager = mock.MagicMock()
    cleared_req = mock.MagicMock()
    cleared_req.action = "run destroy"
    cleared_req.reason = "cleanup"
    approval_manager.clear_escalated.return_value = cleared_req
    runner = mock.MagicMock()
    runner.run_command_async = mock.AsyncMock()

    await _handle_approve_command(runner, approval_manager, msg, "/approve DT-1")

    approval_manager.clear_escalated.assert_called_once_with("DT-1")
    assert "เคลียร์ block" in msg.channel.send.call_args_list[0][0][0]
    runner.run_command_async.assert_called_once()
    call_kwargs = runner.run_command_async.call_args
    assert "DT-1" in call_kwargs[0][2]  # refined_prompt/content_str arg


@pytest.mark.anyio
async def test_run_qa_gate_and_reply_success():
    msg = MockMessage()
    ack = mock.AsyncMock()
    ack.reply = mock.AsyncMock()
    fake = FakeProcess(b"All good.\n", b"", 0)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        await _run_qa_gate_and_reply(msg, ack)
    ack.reply.assert_called_once()
    assert "All good" in ack.reply.call_args[0][0]


@pytest.mark.anyio
async def test_run_qa_gate_and_reply_error():
    msg = MockMessage()
    ack = mock.AsyncMock()
    ack.reply = mock.AsyncMock()
    fake = FakeProcess(b"", b"boom", 1)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        await _run_qa_gate_and_reply(msg, ack)
    assert "errored" in ack.reply.call_args[0][0]


@pytest.mark.anyio
async def test_run_qa_gate_and_reply_falls_back_to_channel_send():
    msg = MockMessage()
    ack = mock.AsyncMock()
    ack.reply = mock.AsyncMock(side_effect=Exception("message gone"))
    fake = FakeProcess(b"ok", b"", 0)
    with mock.patch(
        "service.discord_router.asyncio.create_subprocess_exec",
        new=mock.AsyncMock(return_value=fake),
    ):
        await _run_qa_gate_and_reply(msg, ack)
    msg.channel.send.assert_called_once()


@pytest.mark.anyio
async def test_handle_qa_command_sends_ack_and_schedules_background_task():
    msg = MockMessage()
    with mock.patch(
        "service.discord_router._run_qa_gate_and_reply", mock.AsyncMock()
    ) as mock_run:
        await _handle_qa_command(msg)
        # Let the scheduled background task actually run.
        await asyncio.sleep(0)
    msg.channel.send.assert_called_once()
    assert "Running the QA" in msg.channel.send.call_args[0][0]
    mock_run.assert_called_once()


@pytest.mark.anyio
async def test_try_handle_workflow_command_dispatches_each_command():
    msg = MockMessage()
    runner = mock.MagicMock()
    approval_manager = mock.MagicMock()

    with mock.patch(
        "service.discord_router._handle_project_command", mock.AsyncMock()
    ) as m:
        assert await _try_handle_workflow_command(
            "/project", "/project isac", runner, approval_manager, msg
        )
        m.assert_called_once()

    with mock.patch(
        "service.discord_router._handle_next_command", mock.AsyncMock()
    ) as m:
        assert await _try_handle_workflow_command(
            "/next", "/next", runner, approval_manager, msg
        )
        m.assert_called_once()

    with mock.patch(
        "service.discord_router._handle_refine_command", mock.AsyncMock()
    ) as m:
        assert await _try_handle_workflow_command(
            "/refine", "/refine", runner, approval_manager, msg
        )
        m.assert_called_once()

    with mock.patch(
        "service.discord_router._handle_approve_command", mock.AsyncMock()
    ) as m:
        assert await _try_handle_workflow_command(
            "/approve", "/approve DT-1", runner, approval_manager, msg
        )
        m.assert_called_once()

    with mock.patch("service.discord_router._handle_qa_command", mock.AsyncMock()) as m:
        assert await _try_handle_workflow_command(
            "/qa", "/qa", runner, approval_manager, msg
        )
        m.assert_called_once()

    assert (
        await _try_handle_workflow_command(
            "/nonexistent", "/nonexistent", runner, approval_manager, msg
        )
        is False
    )


@pytest.mark.anyio
async def test_handle_slash_command_help_documents_round_2_commands():
    runner = AgentRunner()
    msg = MockMessage()
    await _handle_slash_command(runner, msg, "/help")
    help_text = msg.channel.send.call_args[0][0]
    for cmd in ("/project", "/next", "/refine", "/approve", "/qa"):
        assert cmd in help_text
