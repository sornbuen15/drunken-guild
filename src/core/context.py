"""A project's identity with its credentials resolved: the one object a server
needs, and the only place the two halves meet.

Building a context does no I/O beyond reading the registry and asking the secret
backends once. Proving it works is a separate, explicit step —
:meth:`ProjectContext.verify_jira_identity`.

That separation matters because of the most expensive bug in this system
(MCP-ARCHITECTURE.md §1.2): **Jira answers a search with HTTP 200 and
``{"issues": []}`` when the credential is bad.** No exception, no 4xx. A board
with 39 issues on it read as empty, and every layer above believed it. Searching
is therefore useless as a health check. ``/rest/api/3/myself`` is not — it 401s
on a bad credential — so that is what gets asked, once, deliberately.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Optional

from . import secrets
from .errors import ConfigError, UpstreamError
from .http import open_url
from .redact import Secret, register_secret
from .registry import (
    DEFAULT_BOARD_DIRS,
    DiscordIdentity,
    ProjectConfig,
    ProjectRegistry,
)

IDENTITY_TIMEOUT_SECONDS: Final = 15

#: The endpoint that actually fails on a bad credential. See the module docstring.
IDENTITY_ENDPOINT: Final = "/rest/api/3/myself"


@dataclass(frozen=True)
class ResolvedJira:
    """Jira identity with the credential fetched from its backend."""

    url: str
    email: str
    project_key: str
    token: Secret

    def auth_header(self) -> str:
        """The ``Authorization`` value for Jira's basic-auth scheme.

        The encoded form is registered for redaction: an upstream error body can
        echo the header back, and masking only the raw token would miss it
        entirely.
        """
        raw = f"{self.email}:{self.token.reveal()}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        register_secret(encoded)
        return f"Basic {encoded}"


@dataclass(frozen=True)
class JiraIdentityResult:
    """Who Jira says we are."""

    account_id: str
    display_name: str
    email: str


@dataclass(frozen=True)
class ProjectContext:
    """Everything a server needs to act on one project."""

    project_id: str
    config: ProjectConfig
    jira: Optional[ResolvedJira] = None
    discord: Optional[DiscordIdentity] = None

    # -- construction -----------------------------------------------------

    @classmethod
    def build(
        cls,
        project_id: str,
        registry: Optional[ProjectRegistry] = None,
    ) -> "ProjectContext":
        """Load *project_id* and resolve its credentials.

        Each backend is consulted at most once per process — :mod:`core.secrets`
        caches — so a 1Password-backed setup prompts for biometrics once, not
        once per tool call.
        """
        config = (registry or ProjectRegistry()).get_project_config(project_id)
        return cls(
            project_id=project_id,
            config=config,
            jira=cls._resolve_jira(config),
            discord=config.discord,
        )

    @staticmethod
    def _resolve_jira(config: ProjectConfig) -> Optional[ResolvedJira]:
        identity = config.jira
        if identity is None:
            return None

        missing = [
            name
            for name, value in (
                ("url", identity.url),
                ("email", identity.email),
                ("project_key", identity.project_key),
                ("credential", identity.credential),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"Project {config.project_id!r} has an incomplete 'jira' block: "
                f"missing {', '.join(missing)}.",
                remediation=(
                    "Fill in the missing fields in the registry. 'credential' is a "
                    "reference such as 'env://JIRA_TOKEN', never the token itself."
                ),
            )

        return ResolvedJira(
            url=identity.url,
            email=identity.email,
            project_key=identity.project_key,
            token=secrets.resolve(identity.credential),
        )

    # -- accessors --------------------------------------------------------

    def require_jira(self) -> ResolvedJira:
        """Return the Jira identity, or say exactly what is missing."""
        if self.jira is None:
            raise ConfigError(
                f"Project {self.project_id!r} has no Jira configured.",
                remediation=(
                    f"Add a 'jira' block for {self.project_id} in the registry with "
                    "url, email, project_key and a credential reference."
                ),
            )
        return self.jira

    def require_discord(self) -> DiscordIdentity:
        """Return the Discord identity, or say exactly what is missing."""
        if self.discord is None:
            raise ConfigError(
                f"Project {self.project_id!r} has no Discord channel configured.",
                remediation=(
                    f"Add a 'discord' block with a channel_id for {self.project_id}."
                ),
            )
        return self.discord

    def root_path(self) -> Path:
        """The project checkout. Only meaningful for filesystem-backed work."""
        return Path(self.config.require_path("this operation"))

    def git_root_path(self) -> Path:
        """Where ``git`` actually works.

        §1.5: for ALPHA the registered path is not the repository — the repository
        is a subdirectory of it — so every git command issued from the project
        root failed. ``git_root`` records the offset.
        """
        root = self.root_path()
        return root / self.config.git_root if self.config.git_root else root

    def board_dir_path(self) -> Path:
        """The Kanban board directory for this project.

        An explicit ``board.dir`` wins; otherwise the conventional locations are
        tried in order, and the Claude Code one is where a new board is created.
        """
        root = self.root_path()
        if self.config.board_dir:
            return root / self.config.board_dir
        for candidate in DEFAULT_BOARD_DIRS:
            if (root / candidate).is_dir():
                return root / candidate
        return root / DEFAULT_BOARD_DIRS[0]

    # -- liveness ---------------------------------------------------------

    def verify_jira_identity(self) -> JiraIdentityResult:
        """Ask Jira who we are, and fail loudly if it will not say.

        This is the check that a search can never be: a bad credential returns
        an empty result set with a 200, but this endpoint returns 401.
        """
        jira = self.require_jira()
        request = urllib.request.Request(f"{jira.url}{IDENTITY_ENDPOINT}", method="GET")
        request.add_header("Authorization", jira.auth_header())
        request.add_header("Accept", "application/json")

        try:
            with open_url(request, timeout=IDENTITY_TIMEOUT_SECONDS) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._identity_http_error(exc, jira) from None
        except urllib.error.URLError as exc:
            raise UpstreamError(
                f"Could not reach Jira at {jira.url}: {exc.reason}",
                remediation="Check the 'url' in the registry, and network access from here.",
            ) from None

        return JiraIdentityResult(
            account_id=str(payload.get("accountId", "")),
            display_name=str(payload.get("displayName", "")),
            email=str(payload.get("emailAddress", "")),
        )

    @staticmethod
    def _identity_http_error(
        exc: urllib.error.HTTPError, jira: ResolvedJira
    ) -> UpstreamError:
        if exc.code in (401, 403):
            return UpstreamError(
                f"Jira rejected the credential for {jira.email} ({exc.code}).",
                remediation=(
                    "The token is wrong, expired, or belongs to a different account. "
                    "Update it in the backend the registry's 'credential' points at — "
                    "note that a bad token makes searches return an empty board "
                    "rather than an error, so this is the check that catches it."
                ),
                details={"status": str(exc.code), "url": jira.url},
            )
        return UpstreamError(
            f"Jira returned HTTP {exc.code} for {IDENTITY_ENDPOINT}.",
            remediation="Check the 'url' in the registry points at the right Jira site.",
            details={"status": str(exc.code), "url": jira.url},
        )
