"""Resolving secret *references* into secret *values*.

The registry is meant to be committed to git. That only works if what it stores
is a reference — ``env://JIRA_TOKEN_ALPHA`` — and never the credential itself. The
value is fetched at startup from whatever backend the operator actually uses,
and lives only in this process's memory.

Two rules make that hold rather than merely encourage it:

* **A reference without a scheme is rejected.** If a bare string resolved to
  itself, the first person in a hurry would paste a real token into
  ``projects.json`` and it would work — right up until it was pushed. Writing
  ``literal://`` is the opt-out, and it is greppable.
* **Each reference is resolved once per process and cached.** Antigravity raised
  this in §8.2: a backend like 1Password prompts for biometrics on every read,
  so re-resolving per call makes the system unusable. The cache is also why a
  token cannot drift mid-process.

Backends are pluggable because the alternative is dictating everyone's secret
store. ``env://`` and ``file://`` cover Kubernetes without a Kubernetes-specific
scheme — a Secret mounted as an env var is the former, mounted as a volume is
the latter. Anything else registers itself, either in-process via
:func:`register_resolver` or from another package via the
``drunken.secret_resolvers`` entry-point group.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final

from .errors import SecretError
from .redact import Secret

#: 1Password and similar can involve a human touching a sensor.
BACKEND_TIMEOUT_SECONDS: Final = 60

ENTRY_POINT_GROUP: Final = "drunken.secret_resolvers"

_SCHEME_SEPARATOR: Final = "://"


@dataclass(frozen=True)
class SecretRef:
    """A parsed ``scheme://body[#fragment]`` reference."""

    raw: str
    scheme: str
    body: str
    fragment: str | None = None


def parse_ref(raw: str) -> SecretRef:
    """Parse *raw*, refusing anything that is not an explicit reference.

    Deliberately hand-rolled rather than :func:`urllib.parse.urlparse`: that
    would read the ``~`` in ``file://~/secrets.json`` as a network location.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise SecretError(
            "Secret reference is empty.",
            remediation=(
                "Set it to a reference such as 'env://JIRA_TOKEN' or "
                "'file://~/.drunken/secrets.json#jira.alpha'."
            ),
        )

    scheme, separator, rest = raw.partition(_SCHEME_SEPARATOR)
    if not separator or not scheme:
        raise SecretError(
            "Secret reference has no scheme, so it looks like a raw credential.",
            remediation=(
                "Registry files are meant to be committed, so they must hold a "
                "reference rather than a value. Use one of: "
                f"{', '.join(sorted(available_schemes()))}. "
                "If the value really is not sensitive, say so explicitly with "
                "'literal://<value>'."
            ),
            details={"reference_prefix": raw[:4] + "..."},
        )

    body, hash_sep, fragment = rest.partition("#")
    return SecretRef(
        raw=raw,
        scheme=scheme.lower(),
        body=body,
        fragment=fragment if hash_sep else None,
    )


class SecretResolver(ABC):
    """A backend that turns a :class:`SecretRef` into a value.

    Implement :meth:`resolve`, set :attr:`scheme`, register it. Raise
    :class:`~core.errors.SecretError` with a remediation on failure — the agent
    reads that message and it is often the only clue the operator gets.
    """

    scheme: ClassVar[str]

    @abstractmethod
    def resolve(self, ref: SecretRef) -> str:
        """Return the secret value for *ref*."""

    def describe(self) -> str:
        """One line about this backend, for :mod:`core.doctor`."""
        return f"{self.scheme}://"


class EnvResolver(SecretResolver):
    """``env://VAR_NAME`` — also how a Kubernetes Secret mounted as env arrives."""

    scheme = "env"

    def resolve(self, ref: SecretRef) -> str:
        name = ref.body.strip()
        if not name:
            raise SecretError(
                "env:// reference does not name a variable.",
                remediation="Write it as 'env://JIRA_TOKEN'.",
            )
        try:
            return os.environ[name]
        except KeyError:
            raise SecretError(
                f"Environment variable {name!r} is not set.",
                remediation=(
                    f"Export {name} in the environment that launches the server. "
                    "For an MCP stdio server that is the host's config, not your shell."
                ),
            ) from None


class FileResolver(SecretResolver):
    """``file://<path>[#dotted.path]`` — a volume-mounted Secret, or a local file.

    Without a fragment the whole file is the secret. With one, the file is JSON
    and the fragment is a dotted path into it, so a single file can hold every
    credential on the machine.
    """

    scheme = "file"

    def resolve(self, ref: SecretRef) -> str:
        path = Path(os.path.expandvars(os.path.expanduser(ref.body))).absolute()
        if not path.is_file():
            raise SecretError(
                f"Secret file not found: {path}",
                remediation=(
                    "Create the file, or point the reference somewhere else. "
                    "Keep it outside any git working tree."
                ),
            )
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SecretError(
                f"Could not read secret file {path}: {exc.strerror}",
                remediation="Check the file's ownership and permissions.",
            ) from None

        if ref.fragment is None:
            return text.strip()
        return self._extract(text, ref.fragment, path)

    @staticmethod
    def _extract(text: str, fragment: str, path: Path) -> str:
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SecretError(
                f"Secret file {path} is not valid JSON, but the reference "
                f"asks for key path {fragment!r}.",
                remediation=f"Fix the JSON (parser said: {exc.msg}), or drop the '#' part.",
            ) from None

        cursor = document
        for key in fragment.split("."):
            if not isinstance(cursor, dict) or key not in cursor:
                raise SecretError(
                    f"Key path {fragment!r} not found in {path}.",
                    remediation="Check the key path against the file's structure.",
                )
            cursor = cursor[key]

        if not isinstance(cursor, str):
            raise SecretError(
                f"Key path {fragment!r} in {path} is {type(cursor).__name__}, not a string.",
                remediation="Point the reference at a string value.",
            )
        return cursor


class OnePasswordResolver(SecretResolver):
    """``op://vault/item/field`` via the 1Password CLI.

    Invoked as an argument vector with no shell, so nothing in the reference can
    become a command.
    """

    scheme = "op"

    def resolve(self, ref: SecretRef) -> str:
        if shutil.which("op") is None:
            raise SecretError(
                "The 1Password CLI ('op') is not installed or not on PATH.",
                remediation=(
                    "Install the 1Password CLI, or switch this reference to "
                    "'env://' or 'file://' — no backend is mandatory."
                ),
            )
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, shell=False
                ["op", "read", ref.raw],
                capture_output=True,
                text=True,
                timeout=BACKEND_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise SecretError(
                f"'op read' timed out after {BACKEND_TIMEOUT_SECONDS}s.",
                remediation=(
                    "It is probably waiting on an unlock prompt. Unlock 1Password, "
                    "or sign in with 'op signin', then retry."
                ),
            ) from None

        if completed.returncode != 0:
            raise SecretError(
                f"'op read' failed for {ref.raw}.",
                remediation="Check the vault, item and field names, and that you are signed in.",
                details={"stderr": completed.stderr.strip()[:500]},
            )
        return completed.stdout.strip()


class KeyringResolver(SecretResolver):
    """``keyring://service/username`` via the OS keychain."""

    scheme = "keyring"

    def resolve(self, ref: SecretRef) -> str:
        try:
            import keyring  # noqa: PLC0415 - optional dependency, imported on use
        except ImportError:
            raise SecretError(
                "The 'keyring' package is not installed.",
                remediation=(
                    "Install it with 'pip install keyring', or switch this "
                    "reference to 'env://' or 'file://'."
                ),
            ) from None

        service, _, username = ref.body.partition("/")
        if not service or not username:
            raise SecretError(
                f"Malformed keyring reference: {ref.raw}",
                remediation="Write it as 'keyring://service/username'.",
            )

        value = keyring.get_password(service, username)
        if value is None:
            raise SecretError(
                f"No keyring entry for service {service!r}, user {username!r}.",
                remediation=f"Store one with: keyring set {service} {username}",
            )
        return str(value)


class LiteralResolver(SecretResolver):
    """``literal://<value>`` — the deliberate, visible way to inline a value.

    Exists so that "no scheme" can stay a hard error. Anything genuinely secret
    belongs in a real backend; this is for values that merely travel alongside
    them.
    """

    scheme = "literal"

    def resolve(self, ref: SecretRef) -> str:
        return ref.body


_resolvers: dict[str, SecretResolver] = {}
_cache: dict[str, Secret] = {}
_entry_points_loaded = False


def register_resolver(resolver: SecretResolver) -> None:
    """Register *resolver*, replacing any existing one for its scheme."""
    _resolvers[resolver.scheme.lower()] = resolver


def _load_builtin_resolvers() -> None:
    for resolver in (
        EnvResolver(),
        FileResolver(),
        OnePasswordResolver(),
        KeyringResolver(),
        LiteralResolver(),
    ):
        _resolvers.setdefault(resolver.scheme, resolver)


def _load_entry_point_resolvers() -> None:
    """Discover resolvers published by other installed packages.

    A broken third-party plugin must not take the server down with it, so a
    failure here is skipped rather than raised — :func:`resolve` will report the
    unknown scheme later, in a tool call, where the agent can see it.
    """
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True

    from importlib.metadata import entry_points  # noqa: PLC0415 - startup only

    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        try:
            candidate = entry_point.load()
            resolver = candidate() if isinstance(candidate, type) else candidate
            if isinstance(resolver, SecretResolver):
                register_resolver(resolver)
        except Exception:  # noqa: BLE001 - a bad plugin must not be fatal
            continue


def _ensure_resolvers() -> dict[str, SecretResolver]:
    if not _resolvers:
        _load_builtin_resolvers()
    _load_entry_point_resolvers()
    return _resolvers


def available_schemes() -> list[str]:
    """Every registered scheme, as ``name://``."""
    return sorted(f"{scheme}://" for scheme in _ensure_resolvers())


def resolve(raw: str) -> Secret:
    """Resolve *raw* to a :class:`~core.redact.Secret`, once per process.

    Repeat calls return the cached value without touching the backend — that is
    what stops 1Password re-prompting, and what guarantees a credential cannot
    change underneath a running server.
    """
    cached = _cache.get(raw)
    if cached is not None:
        return cached

    ref = parse_ref(raw)
    resolvers = _ensure_resolvers()
    resolver = resolvers.get(ref.scheme)
    if resolver is None:
        raise SecretError(
            f"No resolver for scheme {ref.scheme!r}.",
            remediation=f"Use one of: {', '.join(available_schemes())}.",
        )

    value = resolver.resolve(ref)
    if not value:
        raise SecretError(
            f"{ref.scheme}:// resolved to an empty value.",
            remediation="An empty credential is never valid — check the backend entry.",
        )

    secret = Secret(value, ref=raw)
    _cache[raw] = secret
    return secret


def clear_cache() -> None:
    """Drop resolved values. For tests, and for an explicit credential reload."""
    _cache.clear()


def cached_refs() -> list[str]:
    """References resolved so far. Safe to display — references are not secrets."""
    return sorted(_cache)
