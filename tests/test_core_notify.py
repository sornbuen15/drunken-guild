# mypy: ignore-errors
"""Discord is a notice board now, not a door.

The approval machinery could refuse to answer and the work simply waited. A
one-way notification has no such backstop: nobody is blocked on it, so nothing
reports that it never arrived. That inverts what these tests have to pin down —
not "does the right answer come back", but "does a failure stay visible, and
does the credential stay invisible".
"""

import json
import urllib.error
from unittest import mock

import pytest

from core import notify
from core.redact import forget_secrets, redact

WEBHOOK = "https://discord.com/api/webhooks/123456789/s3cr3t-token-value"


@pytest.fixture(autouse=True)
def _clean_secret_state(monkeypatch: pytest.MonkeyPatch):
    """Each test starts with nothing resolved and nothing registered."""
    from core import secrets

    secrets.clear_cache()
    forget_secrets()
    monkeypatch.delenv(notify.ENV_WEBHOOK, raising=False)
    yield
    secrets.clear_cache()
    forget_secrets()


class _Response:
    status = 204

    def read(self) -> bytes:
        return b""

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class TestTheMessage:
    def test_a_notification_carries_its_link(self, monkeypatch) -> None:
        """Every event in the 2.0.0 target — PR ready, daily MVP, audit gaps,
        a decision needed — is only actionable because it links somewhere."""
        monkeypatch.setenv("HOOK", WEBHOOK)
        with mock.patch("core.notify.open_url", return_value=_Response()) as opened:
            result = notify.notify(
                "PR #80 is ready for review",
                link="https://github.com/sornbuen15/drunken-guild/pull/80",
                webhook_ref="env://HOOK",
            )

        assert result.sent is True
        request = opened.call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        assert "PR #80 is ready for review" in body["content"]
        assert "https://github.com/sornbuen15/drunken-guild/pull/80" in body["content"]
        assert request.get_method() == "POST"

    def test_a_notification_with_no_link_is_refused(self, monkeypatch) -> None:
        """Not a failure to report — a message nobody can act on should never
        have been sent, and saying so at the call site is cheaper than a
        Discord room full of dead ends."""
        monkeypatch.setenv("HOOK", WEBHOOK)
        with mock.patch("core.notify.open_url") as opened:
            result = notify.notify(
                "something happened", link="", webhook_ref="env://HOOK"
            )

        assert result.sent is False
        assert "link" in result.reason
        opened.assert_not_called()


class TestTheCredential:
    def test_the_webhook_url_is_registered_for_redaction(self, monkeypatch) -> None:
        """A webhook URL is a credential: anyone holding it can post as the
        bot. It reaches this process from a reference precisely so it never
        appears anywhere, and `redact` is what enforces that everywhere else."""
        monkeypatch.setenv("HOOK", WEBHOOK)
        with mock.patch("core.notify.open_url", return_value=_Response()):
            notify.notify("x", link="https://example.test/1", webhook_ref="env://HOOK")

        assert WEBHOOK not in redact(f"posting to {WEBHOOK}")

    def test_a_failure_does_not_echo_the_url(self, monkeypatch) -> None:
        """urllib puts the full URL into HTTPError's own string form, so the
        obvious `str(exc)` reason leaks the token the moment Discord 404s."""
        monkeypatch.setenv("HOOK", WEBHOOK)
        error = urllib.error.HTTPError(WEBHOOK, 404, "Not Found", {}, None)
        with mock.patch("core.notify.open_url", side_effect=error):
            result = notify.notify(
                "x", link="https://example.test/1", webhook_ref="env://HOOK"
            )

        assert result.sent is False
        assert "s3cr3t-token-value" not in result.reason

    def test_a_bare_url_is_not_a_reference(self) -> None:
        """The registry is committed. A literal webhook pasted into it is the
        failure `core.secrets` exists to make impossible, so it must not work
        here either — and the refusal names the schemes that would."""
        result = notify.notify("x", link="https://example.test/1", webhook_ref=WEBHOOK)

        assert result.sent is False
        assert "env://" in result.reason
        assert "s3cr3t-token-value" not in result.reason


class TestWhenItCannotSend:
    def test_an_unreachable_webhook_never_raises(self, monkeypatch) -> None:
        """A notification is the last thing that should be allowed to fail a
        build or take a hook down with it."""
        monkeypatch.setenv("HOOK", WEBHOOK)
        with mock.patch("core.notify.open_url", side_effect=OSError("network down")):
            result = notify.notify(
                "x", link="https://example.test/1", webhook_ref="env://HOOK"
            )

        assert result.sent is False
        assert result.reason

    def test_no_webhook_configured_says_how_to_configure_one(self) -> None:
        """`sent=False` with an empty reason is the state that made the old
        board readable as empty for months: "could not ask" and "nothing to
        say" have to be different answers."""
        result = notify.notify("x", link="https://example.test/1")

        assert result.sent is False
        assert notify.ENV_WEBHOOK in result.reason

    def test_a_file_url_is_refused_by_the_http_guard(self, monkeypatch) -> None:
        """Every outbound call goes through core.http, which is what stops a
        reference resolving to file:///etc/passwd."""
        monkeypatch.setenv("HOOK", "file:///etc/passwd")
        result = notify.notify(
            "x", link="https://example.test/1", webhook_ref="env://HOOK"
        )

        assert result.sent is False
        assert "scheme" in result.reason


class TestWhereTheWebhookComesFrom:
    def test_the_environment_wins_over_the_registry(self, monkeypatch) -> None:
        """Config precedence is fixed: an env var is explicit and named, which
        is how a container passes a different room in."""
        monkeypatch.setenv(notify.ENV_WEBHOOK, "env://HOOK")
        monkeypatch.setenv("HOOK", WEBHOOK)

        assert (
            notify.webhook_reference(registry_ref="env://FROM_REGISTRY") == "env://HOOK"
        )

    def test_the_registry_is_used_when_the_environment_is_silent(self) -> None:
        assert (
            notify.webhook_reference(registry_ref="env://FROM_REGISTRY")
            == "env://FROM_REGISTRY"
        )

    def test_neither_is_not_an_error(self) -> None:
        """Notifications are optional. A project that configured none is not
        misconfigured, and must not be reported as if it were."""
        assert notify.webhook_reference(registry_ref=None) is None
