# mypy: ignore-errors
"""A failing tool must answer the agent, not raise at it.

`core/errors.py` states the rule the whole design rests on: anything that can
fail is deferred to a tool call and converted into a payload the caller can
read, because "unknown project 'twa'" only tells an agent to give up while
"register it with drunken-init --project twa" tells it what to do.

`as_tool_result` was written for exactly that in 2.1.0 and then called zero
times outside its own definition. DT-235 is what that gap costs: the server
exited before the MCP handshake and the host saw a process vanish with nothing
to read. That fix raised a ConfigError by hand; it did not wire the decorator,
so the principle held at one call site and nowhere else.
"""

import json

import pytest

from board_mcp import server as board_server
from jira_mcp import server as jira_server


def _payload(raw: str) -> dict:
    """A tool result the agent can act on is, at minimum, parseable."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - the failure is the message
        pytest.fail(f"Tool returned something an agent cannot parse: {raw[:200]!r}")


class TestTheWrapperDoesNotEatTheSignature:
    """Caught by an MCP probe, not by the unit tests, on the first attempt at
    this ticket — which is why it is asserted here now.

    FastMCP builds each tool's JSON schema from the signature. A bare
    ``(*args, **kwargs)`` wrapper advertised
    ``jira_search_issues(args, kwargs)`` to the host, and every call came back
    as a pydantic validation error. Every one of the 465 tests still passed:
    they call the functions directly, where ``*args`` accepts anything.
    """

    @pytest.mark.parametrize(  # type: ignore[misc]
        "tool, expected",
        [
            (jira_server.jira_search_issues, {"jql", "detail"}),
            (jira_server.jira_transition_issue, {"issue_key", "target_status"}),
            # DT-255 added five optional fields here. They are the whole point
            # of the ticket -- an Epic with no children leaves Timeline empty --
            # so if the wrapper eats them the feature is gone while every unit
            # test still passes, which is the failure this class exists for.
            (
                jira_server.jira_create_issue,
                {
                    "summary",
                    "description",
                    "issue_type",
                    "parent",
                    "duedate",
                    "start_date",
                    "labels",
                },
            ),
            (board_server.board_summary, {"project"}),
            (board_server.board_block_task, {"project", "task_id", "req_id", "reason"}),
        ],
    )
    def test_the_real_parameters_are_still_visible(self, tool, expected) -> None:
        import inspect

        assert set(inspect.signature(tool).parameters) == expected, (
            "The decorator hid the real parameters. FastMCP will publish a "
            "schema of (args, kwargs) and reject every call to this tool."
        )


class TestAKnownFailureCarriesItsRemediation:
    @pytest.mark.asyncio
    async def test_jira_tool_without_a_project_explains_the_fix(
        self, monkeypatch
    ) -> None:
        """The DT-235 scenario, one layer up: started with no project, every
        tool call has to say so and say what to do about it."""
        monkeypatch.setattr(jira_server, "ctx", None)
        monkeypatch.setattr(jira_server, "jira", None)

        result = _payload(await jira_server.jira_search_issues("project = DT"))

        assert result["ok"] is False
        assert "drunken-init" in json.dumps(result), (
            "The error reached the agent but without the command that fixes "
            "it, which is the half that makes it actionable."
        )

    @pytest.mark.asyncio
    async def test_board_tool_names_the_unknown_project(self, monkeypatch) -> None:
        monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", "/nonexistent/projects.json")

        result = _payload(await board_server.board_summary("no-such-project"))

        assert result["ok"] is False
        assert "no-such-project" in json.dumps(result)


class TestAnUnexpectedFailureIsStillAnAnswer:
    @pytest.mark.asyncio
    async def test_an_unhandled_exception_does_not_escape_the_tool(
        self, monkeypatch
    ) -> None:
        """Not defensive decoration: an exception escaping here reaches the
        agent as a framework traceback, or as a dead server, and neither tells
        it anything it can use."""

        def boom() -> None:
            raise RuntimeError("upstream fell over")

        monkeypatch.setattr(jira_server, "get_client", boom)

        result = _payload(await jira_server.jira_search_issues("project = DT"))

        assert result["ok"] is False
        assert result["error"]["code"] == "internal_error"

    @pytest.mark.asyncio
    async def test_a_secret_in_an_exception_is_not_echoed_back(
        self, monkeypatch
    ) -> None:
        """The redactor exists because upstream error bodies quote the request
        that caused them, headers included."""
        from core.redact import register_secret

        register_secret("s3cr3t-token-value")

        def boom() -> None:
            raise RuntimeError("401 from Basic s3cr3t-token-value")

        monkeypatch.setattr(jira_server, "get_client", boom)

        raw = await jira_server.jira_search_issues("project = DT")

        assert "s3cr3t-token-value" not in raw
