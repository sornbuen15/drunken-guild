# mypy: ignore-errors
"""Secrets must not survive a round trip through a log line or an error."""

import json
import re

import pytest

from core.errors import ConfigError, DrunkenError, as_tool_result
from core.redact import MASK, Secret, forget_secrets, redact, register_secret


@pytest.fixture(autouse=True)  # type: ignore[misc]
def clean_registry():
    forget_secrets()
    yield
    forget_secrets()


class TestSecretWrapper:
    def test_repr_and_str_do_not_expose_the_value(self) -> None:
        secret = Secret("super-secret-token-value", ref="env://JIRA_TOKEN")

        assert "super-secret-token-value" not in repr(secret)
        assert "super-secret-token-value" not in str(secret)
        assert "super-secret-token-value" not in f"token is {secret}"
        assert MASK in repr(secret)

    def test_repr_keeps_the_reference_because_it_is_not_a_secret(self) -> None:
        secret = Secret("super-secret-token-value", ref="env://JIRA_TOKEN")
        assert "env://JIRA_TOKEN" in repr(secret)

    def test_reveal_returns_the_real_value(self) -> None:
        assert Secret("super-secret-token-value").reveal() == "super-secret-token-value"

    def test_constructing_a_secret_registers_it_for_redaction(self) -> None:
        Secret("super-secret-token-value")
        assert "super-secret-token-value" not in redact(
            "leaked super-secret-token-value here"
        )


class TestRedact:
    def test_registered_value_is_masked(self) -> None:
        register_secret("hunter2-hunter2-hunter2")
        assert redact("auth=hunter2-hunter2-hunter2") == f"auth={MASK}"

    def test_short_values_are_not_registered(self) -> None:
        """Registering 'abc' would redact every unrelated word containing it."""
        register_secret("abc")
        assert redact("abcdef") == "abcdef"

    def test_overlapping_secrets_mask_longest_first(self) -> None:
        register_secret("token-prefix-1234")
        register_secret("token-prefix-1234-and-more-tail")

        out = redact("value=token-prefix-1234-and-more-tail")

        assert "and-more-tail" not in out, "short secret masked first, tail exposed"

    def test_basic_auth_header_is_masked_even_when_never_registered(self) -> None:
        """JiraClient base64-encodes email:token, so the raw token never appears."""
        header = "Authorization: Basic dXNlckBleGFtcGxlLmNvbTpBVEFUVDNhYmNkZWY="

        assert "dXNlckBleGFtcGxl" not in redact(header)

    def test_bearer_token_is_masked(self) -> None:
        assert "abcdef" not in redact("Bearer abcdef1234567890abcdef1234567890")

    def test_atlassian_token_shape_is_masked(self) -> None:
        raw = "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN-abcdefghijklmnop"
        assert raw not in redact(f"token={raw}")

    def test_named_credential_assignment_is_masked(self) -> None:
        assert "swordfish123" not in redact("password=swordfish123")

    def test_accepts_non_string_input(self) -> None:
        register_secret("hunter2-hunter2-hunter2")
        assert MASK in redact(RuntimeError("failed with hunter2-hunter2-hunter2"))


class TestErrorsCarryRemediationAndStayRedacted:
    def test_error_dict_includes_remediation(self) -> None:
        err = ConfigError("no jira url", remediation="add jira.url to the registry")
        payload = err.to_dict()

        assert payload["ok"] is False
        assert payload["error"]["code"] == "config_error"
        assert payload["error"]["remediation"] == "add jira.url to the registry"

    def test_error_message_and_details_are_redacted(self) -> None:
        register_secret("hunter2-hunter2-hunter2")
        err = DrunkenError(
            "upstream said hunter2-hunter2-hunter2",
            details={"body": "echoed hunter2-hunter2-hunter2"},
        )

        payload = err.to_dict()

        assert "hunter2" not in json.dumps(payload)

    def test_str_of_error_is_redacted(self) -> None:
        register_secret("hunter2-hunter2-hunter2")
        assert "hunter2" not in str(DrunkenError("leak hunter2-hunter2-hunter2"))


class TestAsToolResultBoundary:
    @pytest.mark.asyncio
    async def test_passes_through_a_successful_result(self) -> None:
        @as_tool_result
        async def tool() -> str:
            return "fine"

        assert await tool() == "fine"

    @pytest.mark.asyncio
    async def test_drunken_error_becomes_a_readable_payload(self) -> None:
        @as_tool_result
        async def tool() -> str:
            raise ConfigError("bad config", remediation="run drunken-doctor")

        payload = json.loads(await tool())

        assert payload["error"]["code"] == "config_error"
        assert payload["error"]["remediation"] == "run drunken-doctor"

    @pytest.mark.asyncio
    async def test_unexpected_exception_is_reported_not_raised(self) -> None:
        """A crash must reach the agent as a message, never as a dead server."""

        @as_tool_result
        async def tool() -> str:
            raise ZeroDivisionError("boom")

        payload = json.loads(await tool())

        assert payload["error"]["code"] == "internal_error"
        assert payload["error"]["details"]["exception"] == "ZeroDivisionError"

    @pytest.mark.asyncio
    async def test_unexpected_exception_is_still_redacted(self) -> None:
        register_secret("hunter2-hunter2-hunter2")

        @as_tool_result
        async def tool() -> str:
            raise RuntimeError("crashed with hunter2-hunter2-hunter2")

        assert "hunter2" not in await tool()

    @pytest.mark.asyncio
    async def test_preserves_tool_name_and_docstring_for_mcp_schema(self) -> None:
        """FastMCP derives the tool name and description from these."""

        @as_tool_result
        async def jira_do_thing() -> str:
            """Does the thing."""
            return ""

        assert jira_do_thing.__name__ == "jira_do_thing"
        assert jira_do_thing.__doc__ is not None
        assert re.search(r"Does the thing", jira_do_thing.__doc__)
