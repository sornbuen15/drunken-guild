from unittest import mock

import pytest
from service.discord_runner import AgentRunner


@pytest.mark.anyio
async def test_is_busy():
    runner = AgentRunner()
    assert not runner.is_busy()

    runner.current_process = mock.MagicMock()
    runner.current_process.returncode = None
    assert runner.is_busy()

    runner.current_process.returncode = 0
    assert not runner.is_busy()


@pytest.mark.anyio
async def test_cancel_current_task():
    runner = AgentRunner()
    runner.current_process = mock.MagicMock()
    runner.current_process.returncode = None

    await runner.cancel_current_task()
    assert runner.is_cancelled
    runner.current_process.terminate.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
async def test_execute_command_success(mock_create_subprocess):
    runner = AgentRunner()

    mock_proc = mock.MagicMock()
    mock_proc.returncode = 0
    # Create an AsyncMock for wait()
    mock_proc.wait = mock.AsyncMock()
    # Provide a mock stdout that yields nothing
    mock_proc.stdout = None

    mock_create_subprocess.return_value = mock_proc

    ret, exc = await runner._execute_command(["cmd"], "test_agent", None)

    assert ret == 0
    assert exc is None
    mock_create_subprocess.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
async def test_execute_command_failure(mock_create_subprocess):
    runner = AgentRunner()
    mock_create_subprocess.side_effect = Exception("failed to spawn")

    ret, exc = await runner._execute_command(["cmd"], "test_agent", None)

    assert ret is None
    assert str(exc) == "failed to spawn"


@pytest.mark.anyio
async def test_run_command_async_early_return():
    runner = AgentRunner()
    # Should return early if command is not agy
    await runner.run_command_async(mock.AsyncMock(), "user", "cmd", ["ls"], "test")
    assert runner.current_process is None


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("shutil.which")
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
async def test_execute_command_uv(mock_create_subprocess, mock_which, mock_exists):
    mock_which.return_value = "/usr/bin/uv"
    runner = AgentRunner()

    mock_proc = mock.MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = mock.AsyncMock()

    mock_stdout = mock.AsyncMock()
    mock_stdout.readline.side_effect = [b"line1\n", b""]
    mock_proc.stdout = mock_stdout
    mock_create_subprocess.return_value = mock_proc

    mock_exists.return_value = True

    with mock.patch("builtins.open", new_callable=mock.mock_open) as mock_open:
        with mock.patch("service.discord_runner.os.remove"):
            ret, exc = await runner._execute_command(
                ["agy", "cmd"], "test_agent", {"VAR": "1"}
            )

    assert ret == 0
    assert exc is None
    # Called with uv run agy cmd
    assert "uv" in mock_create_subprocess.call_args[0]
    assert "run" in mock_create_subprocess.call_args[0]
    assert "agy" in mock_create_subprocess.call_args[0]
    assert mock_create_subprocess.call_args[1]["env"]["VAR"] == "1"


@pytest.mark.anyio
@mock.patch("service.discord_runner.log_activity")
async def test_handle_command_error(mock_log):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()

    with mock.patch("builtins.open", new_callable=mock.mock_open):
        await runner._handle_command_error(
            Exception("test_err"), "test_agent", mock_msg
        )

    mock_msg.edit.assert_called_once()
    assert "test_err" in mock_msg.edit.call_args[1]["content"]
    mock_msg.clear_reactions.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("service.discord_runner.extract_clean_response")
@mock.patch("service.discord_runner.log_activity")
async def test_handle_command_success(mock_log, mock_extract, mock_exists):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_channel = mock.AsyncMock()

    mock_exists.return_value = True
    mock_extract.return_value = "clean log"

    with mock.patch("builtins.open", new_callable=mock.mock_open, read_data="raw data"):
        await runner._handle_command_success(
            mock_channel, "@user", mock_msg, "agent", "proj"
        )

    mock_msg.edit.assert_called_once()
    mock_channel.send.assert_called_once()
    assert "clean log" in mock_channel.send.call_args[0][0]
    mock_msg.clear_reactions.assert_called_once()


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("service.discord_runner.query_gemini_direct")
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
@mock.patch("service.discord_runner.log_activity")
async def test_handle_quest_failure(
    mock_log, mock_subprocess, mock_gemini, mock_exists
):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_channel = mock.AsyncMock()

    mock_exists.return_value = True
    mock_gemini.return_value = "gemini analysis"

    mock_proc = mock.MagicMock()
    mock_proc.communicate = mock.AsyncMock(return_value=(b'{"key": "TEST-123"}', b""))
    mock_subprocess.return_value = mock_proc

    with mock.patch(
        "builtins.open", new_callable=mock.mock_open, read_data="raw error"
    ):
        await runner._handle_quest_failure(
            mock_channel, "@user", "cmd", "agent", mock_msg, "proj"
        )

    mock_msg.edit.assert_called_once()
    mock_channel.send.assert_called_once()
    assert (
        "gemini analysis" in mock_channel.send.call_args[1]["content"]
        or "gemini analysis" in mock_channel.send.call_args[0][0]
    )
    assert (
        "TEST-123" in mock_channel.send.call_args[1]["content"]
        or "TEST-123" in mock_channel.send.call_args[0][0]
    )


@pytest.mark.anyio
@mock.patch.object(AgentRunner, "_execute_command")
@mock.patch.object(AgentRunner, "_handle_command_success")
async def test_run_command_async_success(mock_success, mock_exec):
    runner = AgentRunner()
    mock_channel = mock.AsyncMock()
    mock_msg = mock.AsyncMock()
    mock_channel.send.return_value = mock_msg

    mock_exec.return_value = (0, None)

    await runner.run_command_async(
        mock_channel, "@user", "cmd", ["agy", "test"], "agent"
    )

    mock_exec.assert_called_once()
    mock_success.assert_called_once()


@pytest.mark.anyio
@mock.patch.object(AgentRunner, "_execute_command")
@mock.patch.object(AgentRunner, "_handle_quest_failure")
async def test_run_command_async_failure(mock_failure, mock_exec):
    runner = AgentRunner()
    mock_channel = mock.AsyncMock()
    mock_msg = mock.AsyncMock()
    mock_channel.send.return_value = mock_msg

    mock_exec.return_value = (1, Exception("test"))

    await runner.run_command_async(
        mock_channel, "@user", "cmd", ["agy", "test"], "agent"
    )

    mock_exec.assert_called_once()
    mock_failure.assert_called_once()


@pytest.mark.anyio
@mock.patch.object(AgentRunner, "_execute_command")
async def test_run_command_async_cancelled(mock_exec):
    runner = AgentRunner()
    mock_channel = mock.AsyncMock()
    mock_msg = mock.AsyncMock()
    mock_channel.send.return_value = mock_msg

    async def mock_exec_func(*args, **kwargs):
        runner.is_cancelled = True
        return (None, None)

    mock_exec.side_effect = mock_exec_func

    with mock.patch("service.discord_runner.log_activity"):
        await runner.run_command_async(
            mock_channel, "@user", "cmd", ["agy", "test"], "agent"
        )

    mock_exec.assert_called_once()
    mock_msg.edit.assert_called_once()


@pytest.mark.anyio
async def test_cancel_current_task_exception():
    runner = AgentRunner()
    runner.current_process = mock.MagicMock()
    runner.current_process.returncode = None
    runner.current_process.terminate.side_effect = Exception("test err")
    await runner.cancel_current_task()  # should pass


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.remove")
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("shutil.which")
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
async def test_execute_command_os_remove_exception(
    mock_create_subprocess, mock_which, mock_exists, mock_remove
):
    mock_which.return_value = "/usr/bin/uv"
    runner = AgentRunner()

    mock_proc = mock.MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = mock.AsyncMock()
    mock_proc.stdout = None
    mock_create_subprocess.return_value = mock_proc
    mock_exists.return_value = True
    mock_remove.side_effect = Exception("err")

    with mock.patch("builtins.open", new_callable=mock.mock_open):
        ret, exc = await runner._execute_command(
            ["agy", "cmd"], "test_agent", {"VAR": "1"}
        )
    assert ret == 0


@pytest.mark.anyio
@mock.patch("service.discord_runner.log_activity")
async def test_handle_command_error_exception(mock_log):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_msg.clear_reactions.side_effect = Exception("err")

    with mock.patch("builtins.open", new_callable=mock.mock_open):
        await runner._handle_command_error(
            Exception("test_err"), "test_agent", mock_msg
        )


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("service.discord_runner.extract_clean_response")
@mock.patch("service.discord_runner.log_activity")
async def test_handle_command_success_exceptions_and_no_resp(
    mock_log, mock_extract, mock_exists
):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_channel = mock.AsyncMock()

    mock_exists.return_value = True
    mock_extract.return_value = ""  # Empty resp
    mock_msg.clear_reactions.side_effect = Exception("err")

    with mock.patch("builtins.open", new_callable=mock.mock_open) as m_open:
        m_open.side_effect = Exception("read err")  # Fail to read RAW_LOG_FILE
        await runner._handle_command_success(
            mock_channel, "@user", mock_msg, "agent", "proj"
        )

    mock_channel.send.assert_called_once()
    assert "Completed" in mock_channel.send.call_args[0][0]


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("service.discord_runner.extract_clean_response")
@mock.patch("service.discord_runner.log_activity")
async def test_handle_command_success_long_resp(mock_log, mock_extract, mock_exists):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_channel = mock.AsyncMock()

    mock_exists.return_value = True
    mock_extract.return_value = "A" * 2000

    with mock.patch("builtins.open", new_callable=mock.mock_open):
        await runner._handle_command_success(
            mock_channel, "@user", mock_msg, "agent", "proj"
        )

    assert "(Content too long" in mock_channel.send.call_args[0][0]


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("service.discord_runner.query_gemini_direct")
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
@mock.patch("service.discord_runner.log_activity")
async def test_handle_quest_failure_exceptions(
    mock_log, mock_subprocess, mock_gemini, mock_exists
):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_channel = mock.AsyncMock()

    mock_exists.return_value = True
    mock_gemini.side_effect = Exception("gemini err")
    mock_subprocess.side_effect = Exception("subprocess err")

    with mock.patch("builtins.open", new_callable=mock.mock_open) as m_open:
        # Side effect inside the lock for reading RAW_LOG_FILE
        # The first call is for reading, but since file_lock isn't real, it works normally. Let's just return normal content
        m_open.return_value.read.return_value = "log data"
        await runner._handle_quest_failure(
            mock_channel, "@user", "cmd", "agent", mock_msg, "proj"
        )

    assert (
        "Failed to analyze log" in mock_channel.send.call_args[1]["content"]
        or "Failed to analyze log" in mock_channel.send.call_args[0][0]
    )


@pytest.mark.anyio
@mock.patch.object(AgentRunner, "_execute_command")
@mock.patch.object(AgentRunner, "_handle_command_success")
async def test_run_command_async_reactions_exception(mock_success, mock_exec):
    runner = AgentRunner()
    mock_channel = mock.AsyncMock()
    mock_msg = mock.AsyncMock()
    mock_msg.add_reaction.side_effect = Exception("reaction err")
    mock_msg.clear_reactions.side_effect = Exception("clear err")
    mock_channel.send.return_value = mock_msg

    mock_exec.return_value = (0, None)

    await runner.run_command_async(
        mock_channel, "@user", "cmd", ["agy", "test"], "agent"
    )

    async def mock_exec_func(*args, **kwargs):
        runner.is_cancelled = True
        return (None, None)

    mock_exec.side_effect = mock_exec_func
    with mock.patch("service.discord_runner.log_activity"):
        await runner.run_command_async(
            mock_channel, "@user", "cmd", ["agy", "test"], "agent"
        )


@pytest.mark.anyio
@mock.patch("service.discord_runner.os.path.exists")
@mock.patch("service.discord_runner.query_gemini_direct")
@mock.patch("service.discord_runner.asyncio.create_subprocess_exec", autospec=True)
async def test_handle_quest_failure_read_exception(
    mock_subprocess, mock_gemini, mock_exists
):
    runner = AgentRunner()
    mock_msg = mock.AsyncMock()
    mock_channel = mock.AsyncMock()

    mock_exists.return_value = True

    with mock.patch("builtins.open", new_callable=mock.mock_open) as m_open:
        m_open.side_effect = Exception("read err 170")
        await runner._handle_quest_failure(
            mock_channel, "@user", "cmd", "agent", mock_msg, "proj"
        )

    assert (
        "Unknown failure" in mock_channel.send.call_args[1]["content"]
        or "Unknown failure" in mock_channel.send.call_args[0][0]
    )
