"""Errors that reach the agent instead of killing the server.

The failure mode this exists to prevent is the one from MCP-ARCHITECTURE.md
§1.1: a missing dependency raised at import time, so the server never finished
starting, so the host showed no tools at all and no message anywhere explaining
why. Nothing here is raised while a module is being imported. Everything that
can fail is deferred to a tool call and converted, by :func:`as_tool_result`,
into a JSON payload the agent can read and act on.

Every error therefore carries a *remediation*: the concrete next step, not just
what went wrong. An agent that is told "Unknown project 'alpha'" can only give up;
one that is told to run ``drunken-init --project alpha --path <path>`` can proceed.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Final, TypeVar

from .redact import redact


class DrunkenError(Exception):
    """Base for every failure this system raises deliberately.

    Anything else escaping a tool is a bug, and :func:`as_tool_result` labels it
    as such rather than dressing it up as a handled condition.
    """

    code: str = "drunken_error"

    def __init__(
        self,
        message: str,
        *,
        remediation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.remediation = remediation
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialise for a tool result. Redacted — errors quote upstream bodies."""
        payload: dict[str, Any] = {
            "ok": False,
            "error": {"code": self.code, "message": redact(self.message)},
        }
        if self.remediation:
            payload["error"]["remediation"] = redact(self.remediation)
        if self.details:
            payload["error"]["details"] = {
                key: redact(value) for key, value in self.details.items()
            }
        return payload

    def __str__(self) -> str:
        return redact(self.message)


class ConfigError(DrunkenError):
    """Configuration is missing, malformed, or internally inconsistent."""

    code = "config_error"


class RegistryError(DrunkenError):
    """The project registry is unreadable, or the project is not in it."""

    code = "registry_error"


class SecretError(DrunkenError):
    """A secret reference could not be resolved, or is not a valid reference."""

    code = "secret_error"


class ValidationError(DrunkenError):
    """Caller-supplied input failed validation before anything was acted on."""

    code = "validation_error"


class UpstreamError(DrunkenError):
    """Jira, Discord or another external service rejected or failed the call."""

    code = "upstream_error"


class AuthError(DrunkenError):
    """The caller could not be authenticated. Reserved for HTTP mode (2.4.0)."""

    code = "auth_error"


class AuthzError(DrunkenError):
    """The caller is known but not permitted this project. Reserved for 2.3.0."""

    code = "authz_error"


_UNEXPECTED: Final = (
    "Unexpected internal error. This is a bug in drunken-team, not a "
    "configuration problem — please report it with the details below."
)

T = TypeVar("T")


def as_tool_result(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate an async MCP tool so no exception can escape as a crash.

    A :class:`DrunkenError` becomes its structured payload. Anything else is
    reported as an internal bug, still redacted, still as a readable result —
    the agent must never be left facing a server that simply vanished.
    """

    async def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return str(await func(*args, **kwargs))
        except DrunkenError as exc:
            return json.dumps(exc.to_dict(), indent=2)
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all boundary
            return json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "internal_error",
                        "message": _UNEXPECTED,
                        "details": {
                            "exception": type(exc).__name__,
                            "detail": redact(exc),
                        },
                    },
                },
                indent=2,
            )

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper
