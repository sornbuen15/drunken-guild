"""Secret containment: a value wrapper that will not print itself, and a
redactor for text that may have picked one up along the way.

Two layers, because either one alone leaks:

* :class:`Secret` stops the accidental leak — the f-string, the ``repr()`` in a
  traceback, the debug ``print``. Getting the real value requires saying
  :meth:`Secret.reveal`, which is greppable in review.
* :func:`redact` stops the deliberate-looking one — an upstream error body
  echoing back the ``Authorization`` header we just sent it. Jira's client
  base64-encodes ``email:token`` into that header, so masking the raw token
  string alone would sail straight past it; the credential patterns below cover
  the encoded form generically.

Registered values are held in memory for the life of the process. That is the
same exposure the resolved credential already has, so it adds no new risk — but
it does mean :func:`register_secret` should be fed only real secrets.
"""

from __future__ import annotations

import re
from typing import Any, Final, Iterable

MASK: Final = "***REDACTED***"

# Below this length a "secret" is more likely to be a common substring, and
# registering it would redact unrelated text into uselessness.
_MIN_REGISTERABLE_LENGTH: Final = 8

# Header and token shapes worth masking even when the exact value was never
# registered — covers credentials that reached us from somewhere we don't own.
_CREDENTIAL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # `Authorization: Basic <base64>` — how JiraClient sends email:token.
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{16,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{16,}=*"),
    # Atlassian API tokens.
    re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}"),
    # Discord bot tokens: three dot-separated base64url segments.
    re.compile(r"\b[A-Za-z0-9_\-]{24,28}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}"),
    # Anything that named itself.
    re.compile(r"(?i)\b(api[_\-]?key|token|secret|password)\s*[=:]\s*\S{8,}"),
)

_registered: set[str] = set()


class Secret:
    """A string that refuses to render itself.

    ``str()``, ``repr()`` and f-string interpolation all yield the mask, so a
    secret cannot reach a log line by accident. Use :meth:`reveal` at the point
    of use — an HTTP header, a subprocess argument — and nowhere else.
    """

    __slots__ = ("_value", "ref")

    def __init__(self, value: str, ref: str | None = None) -> None:
        self._value = value
        #: The reference this was resolved from (e.g. ``env://JIRA_TOKEN``).
        #: Safe to display — that is the whole point of reference indirection.
        self.ref = ref
        register_secret(value)

    def reveal(self) -> str:
        """Return the real value. Every call site should be obvious in review."""
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        where = f" ref={self.ref}" if self.ref else ""
        return f"<Secret{where} len={len(self._value)} {MASK}>"

    __str__ = __repr__


def register_secret(value: str | None) -> None:
    """Mark *value* for masking by :func:`redact` wherever it later appears."""
    if value and len(value) >= _MIN_REGISTERABLE_LENGTH:
        _registered.add(value)


def forget_secrets() -> None:
    """Drop every registered value. For tests; not part of the runtime flow."""
    _registered.clear()


def redact(text: Any) -> str:
    """Mask known secrets and credential-shaped substrings in *text*.

    Accepts any object so it can wrap an exception directly. Applied to every
    message that leaves the process — logs, tool results, doctor output.
    """
    out = text if isinstance(text, str) else str(text)
    # Longest first: a short secret that is a substring of a longer one must not
    # partially mask it and leave the tail exposed.
    for value in sorted(_registered, key=len, reverse=True):
        out = out.replace(value, MASK)
    for pattern in _CREDENTIAL_PATTERNS:
        out = pattern.sub(MASK, out)
    return out


def redact_all(items: Iterable[Any]) -> list[str]:
    """:func:`redact` over an iterable."""
    return [redact(item) for item in items]
