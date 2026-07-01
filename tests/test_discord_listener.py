from typing import Any
from unittest.mock import AsyncMock

import pytest
from service.discord_listener import extract_clean_response, on_message


def test_extract_clean_response() -> None:
    raw_log = """
<thinking>
This is an internal thought process.
It should be removed.
</thinking>
I will run a command.
[System] Running task...
[Warning] Something happened.
Executing command: ls
Actual message here.
Another line of the actual message.
"""

    cleaned = extract_clean_response(raw_log)

    assert "This is an internal thought process." not in cleaned
    assert "I will run a command." not in cleaned
    assert "[System]" not in cleaned
    assert "Actual message here." in cleaned
    assert "Another line of the actual message." in cleaned


@pytest.mark.anyio  # type: ignore[misc]
async def test_discord_project_routing_e2e(mocker: Any, monkeypatch: Any) -> None:
    """
    E2E Test: Verify that when a user mentions a project, Mina (the router)
    extracts the target_project and dispatches the agent with the correct CWD.
    """
    # 1. Mock the environment and registry
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")

    mock_registry = mocker.MagicMock()
    mock_registry.get_projects.return_value = {
        "beta": {"path": "/mock/path/to/beta", "description": "BETA Project"}
    }
    mock_registry.get_project.return_value = {"path": "/mock/path/to/beta"}
    mocker.patch("service.discord_listener.ProjectRegistry", return_value=mock_registry)

    # 2. (Removed Gemini Mock, now uses Deterministic Router)

    # 3. Mock the execution so we don't really run agy
    mock_execute = mocker.patch(
        "service.discord_listener.run_command_async", new_callable=AsyncMock
    )

    # 4. Mock the Discord Message
    class MockAuthor:
        def __init__(self) -> None:
            self.bot = False
            self.mention = "@boss"
            self.name = "boss"

    class MockChannel:
        def __init__(self) -> None:
            self.id = 12345

        async def send(self, msg: str) -> None:
            pass

    class MockMessage:
        def __init__(self) -> None:
            self.author = MockAuthor()
            self.channel = MockChannel()
            self.content = "fullstack-engineer project-beta Fix the bug in BETA"
            self.mentions = [mocker.MagicMock()]
            self.reference = None

    mock_client = mocker.MagicMock()
    mock_client.user = mocker.MagicMock()
    mock_client.user.id = 999

    mocker.patch("service.discord_listener.CHANNEL_ID", 12345)
    mocker.patch("service.discord_listener.client", mock_client)

    msg = MockMessage()
    msg.content = "fullstack-engineer project-beta Fix the bug in BETA"
    msg.mentions[0] = mock_client.user

    # 5. Execute the discord listener on_message flow
    await on_message(msg)

    import asyncio

    await asyncio.sleep(0.01)  # let create_task run

    # 6. Verify that the agent was spawned in the correct directory (/mock/path/to/beta)
    assert mock_execute.called
    kwargs = mock_execute.call_args.kwargs

    cwd_passed = kwargs.get("cwd")

    assert cwd_passed == "/mock/path/to/beta"
