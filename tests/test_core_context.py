# mypy: ignore-errors
"""Identity plus resolved credentials, and the liveness check that a search
can never be."""

import json
import urllib.error
from unittest import mock

import pytest

from core import secrets
from core.context import ProjectContext
from core.errors import ConfigError, SecretError, UpstreamError
from core.redact import forget_secrets, redact
from core.registry import ProjectRegistry

V2_DOCUMENT = {
    "version": 2,
    "projects": {
        "twa": {
            "path": "/abs/tff-web-app",
            "git_root": "twa",
            "jira": {
                "url": "https://example.atlassian.net",
                "email": "someone@example.com",
                "project_key": "TWA",
                "credential": "env://JIRA_TOKEN_TWA",
            },
            "discord": {"channel_id": "123456789012345678"},
        },
        "bare": {"path": "/abs/bare"},
        "incomplete": {
            "path": "/abs/incomplete",
            "jira": {"url": "https://example.atlassian.net", "project_key": "INC"},
        },
        "inline-secret": {
            "path": "/abs/inline",
            "jira": {
                "url": "https://example.atlassian.net",
                "email": "someone@example.com",
                "project_key": "INL",
                "credential": "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN-pasted",
            },
        },
    },
}


@pytest.fixture(autouse=True)  # type: ignore[misc]
def clean_state(monkeypatch):
    secrets.clear_cache()
    forget_secrets()
    monkeypatch.setenv("JIRA_TOKEN_TWA", "a-valid-looking-token-value")
    yield
    secrets.clear_cache()
    forget_secrets()


@pytest.fixture  # type: ignore[misc]
def registry(tmp_path) -> ProjectRegistry:
    target = tmp_path / "projects.json"
    target.write_text(json.dumps(V2_DOCUMENT), encoding="utf-8")
    return ProjectRegistry(str(target))


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example", code, "nope", {}, None)


class TestBuild:
    def test_resolves_the_credential_reference(self, registry) -> None:
        context = ProjectContext.build("twa", registry)
        assert context.jira.token.reveal() == "a-valid-looking-token-value"

    def test_carries_the_rest_of_the_identity(self, registry) -> None:
        context = ProjectContext.build("twa", registry)

        assert context.jira.project_key == "TWA"
        assert context.discord.channel_id == "123456789012345678"

    def test_a_project_without_jira_builds_fine(self, registry) -> None:
        """Board-only projects exist and must not be forced to configure Jira."""
        assert ProjectContext.build("bare", registry).jira is None

    def test_an_incomplete_jira_block_names_every_missing_field(self, registry) -> None:
        with pytest.raises(ConfigError, match="incomplete") as caught:
            ProjectContext.build("incomplete", registry)

        assert "email" in str(caught.value)
        assert "credential" in str(caught.value)

    def test_a_token_pasted_into_the_registry_is_refused(self, registry) -> None:
        """The registry is committed to git — this is the failure that matters."""
        with pytest.raises(SecretError, match="no scheme"):
            ProjectContext.build("inline-secret", registry)

    def test_backend_is_consulted_once_even_across_two_contexts(self, tmp_path) -> None:
        """Rebuilding a context must not re-prompt a biometric backend."""
        calls = []

        class CountingResolver(secrets.SecretResolver):
            scheme = "counting"

            def resolve(self, ref):
                calls.append(ref.raw)
                return "value"

        secrets.register_resolver(CountingResolver())

        target = tmp_path / "projects.json"
        target.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "twa": {
                            "jira": {
                                "url": "https://example.atlassian.net",
                                "email": "someone@example.com",
                                "project_key": "TWA",
                                "credential": "counting://jira",
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        counting_registry = ProjectRegistry(str(target))

        ProjectContext.build("twa", counting_registry)
        ProjectContext.build("twa", counting_registry)

        assert len(calls) == 1


class TestRequireAccessors:
    def test_require_jira_explains_what_to_add(self, registry) -> None:
        with pytest.raises(ConfigError, match="no Jira configured") as caught:
            ProjectContext.build("bare", registry).require_jira()

        assert "credential reference" in caught.value.remediation

    def test_require_discord_explains_what_to_add(self, registry) -> None:
        with pytest.raises(ConfigError, match="no Discord channel"):
            ProjectContext.build("bare", registry).require_discord()


class TestPaths:
    def test_git_root_points_into_the_subdirectory_when_declared(
        self, registry
    ) -> None:
        """§1.5: TWA's registered path is not the repository — the repo is
        inside it, so every git command from the root failed."""
        context = ProjectContext.build("twa", registry)
        assert str(context.git_root_path()) == "/abs/tff-web-app/twa"

    def test_git_root_defaults_to_the_project_root(self, registry) -> None:
        assert (
            str(ProjectContext.build("bare", registry).git_root_path()) == "/abs/bare"
        )

    def test_board_defaults_to_the_claude_convention(self, registry) -> None:
        assert ProjectContext.build("bare", registry).board_dir_path().name == "board"

    def test_board_honours_an_explicit_directory(self, tmp_path) -> None:
        target = tmp_path / "projects.json"
        target.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "p": {"path": "/abs/p", "board": {"dir": "docs/kanban"}}
                    },
                }
            ),
            encoding="utf-8",
        )
        context = ProjectContext.build("p", ProjectRegistry(str(target)))

        assert str(context.board_dir_path()) == "/abs/p/docs/kanban"


class TestVerifyJiraIdentity:
    """The S4 fix. A search returns 200 with an empty list on a bad credential,
    so only this endpoint can tell us the truth."""

    def _respond(self, payload: dict) -> mock.MagicMock:
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__.return_value = response
        return response

    def test_returns_who_jira_says_we_are(self, registry) -> None:
        context = ProjectContext.build("twa", registry)
        response = self._respond(
            {
                "accountId": "abc123",
                "displayName": "R. Jakkawan",
                "emailAddress": "someone@example.com",
            }
        )

        with mock.patch("urllib.request.urlopen", return_value=response):
            result = context.verify_jira_identity()

        assert result.account_id == "abc123"
        assert result.display_name == "R. Jakkawan"

    def test_it_asks_the_identity_endpoint_not_search(self, registry) -> None:
        context = ProjectContext.build("twa", registry)

        with mock.patch(
            "urllib.request.urlopen", return_value=self._respond({})
        ) as urlopen:
            context.verify_jira_identity()

        assert urlopen.call_args[0][0].full_url.endswith("/rest/api/3/myself")

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_rejected_credential_raises_instead_of_looking_empty(
        self, registry, status: int
    ) -> None:
        context = ProjectContext.build("twa", registry)

        with mock.patch("urllib.request.urlopen", side_effect=_http_error(status)):
            with pytest.raises(
                UpstreamError, match="rejected the credential"
            ) as caught:
                context.verify_jira_identity()

        assert "empty board" in caught.value.remediation

    def test_other_http_errors_point_at_the_configured_url(self, registry) -> None:
        context = ProjectContext.build("twa", registry)

        with mock.patch("urllib.request.urlopen", side_effect=_http_error(500)):
            with pytest.raises(UpstreamError, match="HTTP 500"):
                context.verify_jira_identity()

    def test_an_unreachable_host_is_reported_as_such(self, registry) -> None:
        context = ProjectContext.build("twa", registry)

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("name resolution failed"),
        ):
            with pytest.raises(UpstreamError, match="Could not reach Jira"):
                context.verify_jira_identity()

    def test_verifying_without_jira_configured_is_a_config_error(
        self, registry
    ) -> None:
        with pytest.raises(ConfigError):
            ProjectContext.build("bare", registry).verify_jira_identity()


class TestCredentialContainment:
    def test_the_encoded_auth_header_is_registered_for_redaction(
        self, registry
    ) -> None:
        """An upstream error body can echo the header back; masking only the raw
        token would sail straight past the base64 form."""
        context = ProjectContext.build("twa", registry)

        header = context.jira.auth_header()
        encoded = header.removeprefix("Basic ")

        assert encoded not in redact(f"upstream said: Authorization {encoded}")

    def test_the_token_is_not_printable(self, registry) -> None:
        context = ProjectContext.build("twa", registry)
        assert "a-valid-looking-token-value" not in repr(context.jira.token)

    def test_an_error_from_verification_never_contains_the_token(
        self, registry
    ) -> None:
        context = ProjectContext.build("twa", registry)

        with mock.patch("urllib.request.urlopen", side_effect=_http_error(401)):
            try:
                context.verify_jira_identity()
            except UpstreamError as exc:
                assert "a-valid-looking-token-value" not in json.dumps(exc.to_dict())
