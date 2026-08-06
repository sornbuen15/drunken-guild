# mypy: ignore-errors
"""urlopen honours file:// and ftp://, so a URL from configuration is not
merely a network destination."""

import urllib.request
from unittest import mock

import pytest

from core.errors import ValidationError
from core.http import ALLOWED_SCHEMES, open_url, validate_url


class TestValidateUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.atlassian.net",
            "http://localhost:8080/rest/api/3/myself",
            "HTTPS://EXAMPLE.ATLASSIAN.NET/x",
        ],
    )
    def test_accepts_plain_http_and_https(self, url: str) -> None:
        assert validate_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "file://localhost/etc/shadow",
            "ftp://example.com/secrets",
            "data:text/plain;base64,aGVsbG8=",
            "gopher://example.com",
        ],
    )
    def test_rejects_every_other_scheme(self, url: str) -> None:
        """A file:// URL here would read a local file through what looks to
        every layer above like an ordinary API response."""
        with pytest.raises(ValidationError, match="not allowed"):
            validate_url(url)

    def test_the_rejection_explains_the_risk(self) -> None:
        with pytest.raises(ValidationError) as caught:
            validate_url("file:///etc/passwd")
        assert "read local files" in caught.value.remediation

    def test_rejects_a_url_with_no_host(self) -> None:
        with pytest.raises(ValidationError, match="no host"):
            validate_url("https:///rest/api/3/myself")

    def test_rejects_a_bare_path(self) -> None:
        with pytest.raises(ValidationError):
            validate_url("/rest/api/3/myself")

    def test_allowed_set_is_exactly_http_and_https(self) -> None:
        assert ALLOWED_SCHEMES == {"http", "https"}


class TestOpenUrl:
    def test_opens_an_allowed_request(self) -> None:
        request = urllib.request.Request("https://example.atlassian.net", method="GET")

        with mock.patch("urllib.request.urlopen", return_value="response") as urlopen:
            assert open_url(request, timeout=5) == "response"

        assert urlopen.call_args[0][0] is request
        assert urlopen.call_args[1]["timeout"] == 5

    def test_refuses_before_opening_anything(self) -> None:
        """The check must happen first — validating after the call would defeat
        the entire point."""
        request = urllib.request.Request("file:///etc/passwd")

        with mock.patch("urllib.request.urlopen") as urlopen:
            with pytest.raises(ValidationError):
                open_url(request, timeout=5)

        urlopen.assert_not_called()


class TestCallSitesAreRouted:
    """Every outbound call goes through the guard, or the guard is decorative."""

    def test_jira_identity_check_is_guarded(self, tmp_path, monkeypatch) -> None:
        import json

        from core.context import ProjectContext
        from core.registry import ProjectRegistry

        monkeypatch.setenv("TOKEN_X", "a-token-value-long-enough")
        target = tmp_path / "projects.json"
        target.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "p": {
                            "jira": {
                                "url": "file:///etc",
                                "email": "a@b.c",
                                "project_key": "P",
                                "credential": "env://TOKEN_X",
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        context = ProjectContext.build("p", ProjectRegistry(str(target)))

        with mock.patch("urllib.request.urlopen") as urlopen:
            with pytest.raises(ValidationError):
                context.verify_jira_identity()

        urlopen.assert_not_called()

    def test_jira_client_requests_are_guarded(self) -> None:
        import asyncio

        from jira_mcp.jira_client import make_request

        with mock.patch("urllib.request.urlopen") as urlopen:
            with pytest.raises(ValidationError):
                asyncio.run(
                    make_request("file:///etc/passwd", email="a@b.c", token="tok")
                )

        urlopen.assert_not_called()
