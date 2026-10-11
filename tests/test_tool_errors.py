# mypy: ignore-errors
"""A failing tool must answer the agent, not raise at it.

`core/errors.py` states the rule the whole design rests on: anything that can
fail is deferred to a tool call and converted into a payload the caller can
read, because "unknown project 'alpha'" only tells an agent to give up while
"register it with drunken-init --project alpha" tells it what to do.

`as_tool_result` was written for exactly that in 2.1.0 and then called zero
times outside its own definition. DG-235 is what that gap costs: the server
exited before the MCP handshake and the host saw a process vanish with nothing
to read. That fix raised a ConfigError by hand; it did not wire the decorator,
so the principle held at one call site and nowhere else.
"""

import json

import pytest

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
            (jira_server.jira_search_issues, {"project", "jql", "detail"}),
            (
                jira_server.jira_transition_issue,
                {"project", "issue_key", "target_status"},
            ),
            # DG-255 added five optional fields here. They are the whole point
            # of the ticket -- an Epic with no children leaves Timeline empty --
            # so if the wrapper eats them the feature is gone while every unit
            # test still passes, which is the failure this class exists for.
            (
                jira_server.jira_create_issue,
                {
                    "project",
                    "summary",
                    "description",
                    "issue_type",
                    "parent",
                    "duedate",
                    "start_date",
                    "labels",
                },
            ),
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
    async def test_a_tool_called_with_no_project_explains_the_fix(self) -> None:
        """The DG-235 scenario, moved to where the project now comes from.

        It used to be "the server was started without a project"; since DG-341
        there is nothing to start it with, so the same failure is a call that
        named no project. The requirement is unchanged: the answer has to carry
        the fix, not just the complaint.
        """
        result = _payload(await jira_server.jira_search_issues("", "project = DG"))

        assert result["ok"] is False
        assert "AGENTS.md" in json.dumps(result), (
            "The error reached the agent but without where to find the project "
            "id, which is the half that makes it actionable."
        )

    @pytest.mark.asyncio
    async def test_an_unknown_project_names_the_registered_ones(
        self, monkeypatch, tmp_path
    ) -> None:
        """A typo must not resolve to somebody else's board."""
        from core import paths, secrets

        registry = tmp_path / "projects.json"
        registry.write_text('{"version": 2, "projects": {"alpha": {}}}')
        monkeypatch.setenv(paths.ENV_REGISTRY, str(registry))
        secrets.clear_cache()
        jira_server.forget_clients()

        result = _payload(await jira_server.jira_search_issues("alfa", "ORDER BY key"))

        assert result["ok"] is False
        assert "alpha" in json.dumps(result)


class TestAnUnexpectedFailureIsStillAnAnswer:
    @pytest.mark.asyncio
    async def test_an_unhandled_exception_does_not_escape_the_tool(
        self, monkeypatch
    ) -> None:
        """Not defensive decoration: an exception escaping here reaches the
        agent as a framework traceback, or as a dead server, and neither tells
        it anything it can use."""

        def boom(project) -> None:
            raise RuntimeError("upstream fell over")

        monkeypatch.setattr(jira_server, "get_client", boom)

        result = _payload(await jira_server.jira_search_issues("dg", "project = DG"))

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

        def boom(project) -> None:
            raise RuntimeError("401 from Basic s3cr3t-token-value")

        monkeypatch.setattr(jira_server, "get_client", boom)

        raw = await jira_server.jira_search_issues("dg", "project = DG")

        assert "s3cr3t-token-value" not in raw
