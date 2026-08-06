# mypy: ignore-errors
"""The registry is committed to git, so a value must never be able to sit in it,
and a backend must never be asked twice."""

import json
import subprocess
from unittest import mock

import pytest

from core import secrets
from core.errors import SecretError
from core.redact import Secret, forget_secrets


@pytest.fixture(autouse=True)  # type: ignore[misc]
def clean_state():
    secrets.clear_cache()
    forget_secrets()
    yield
    secrets.clear_cache()
    forget_secrets()


class TestBareValuesAreRejected:
    """The single rule that keeps credentials out of a committable file."""

    @pytest.mark.parametrize(
        "raw",
        [
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
            "hunter2",
            "not a reference at all",
        ],
    )
    def test_a_value_without_a_scheme_is_an_error(self, raw: str) -> None:
        with pytest.raises(SecretError, match="no scheme"):
            secrets.resolve(raw)

    def test_the_error_does_not_echo_the_credential_back(self) -> None:
        token = "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN"
        try:
            secrets.resolve(token)
        except SecretError as exc:
            assert token not in str(exc)
            assert token not in json.dumps(exc.to_dict())

    def test_the_error_names_the_available_schemes(self) -> None:
        with pytest.raises(SecretError) as caught:
            secrets.resolve("hunter2")
        assert "env://" in caught.value.remediation

    def test_empty_reference_is_an_error(self) -> None:
        with pytest.raises(SecretError, match="empty"):
            secrets.resolve("   ")

    def test_literal_is_the_explicit_opt_out(self) -> None:
        assert secrets.resolve("literal://plain-value").reveal() == "plain-value"


class TestEnvResolver:
    def test_reads_the_named_variable(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")
        assert secrets.resolve("env://SOME_TOKEN").reveal() == "value-from-env"

    def test_missing_variable_is_a_clear_error(self, monkeypatch) -> None:
        monkeypatch.delenv("ABSENT_TOKEN", raising=False)
        with pytest.raises(SecretError, match="ABSENT_TOKEN"):
            secrets.resolve("env://ABSENT_TOKEN")

    def test_reference_without_a_variable_name_is_an_error(self) -> None:
        with pytest.raises(SecretError, match="does not name a variable"):
            secrets.resolve("env://")

    def test_empty_variable_is_rejected_rather_than_returned(self, monkeypatch) -> None:
        """An empty credential is never valid, and would otherwise fail later
        as a confusing 401."""
        monkeypatch.setenv("BLANK_TOKEN", "")
        with pytest.raises(SecretError, match="empty"):
            secrets.resolve("env://BLANK_TOKEN")


class TestFileResolver:
    def test_reads_whole_file_when_there_is_no_fragment(self, tmp_path) -> None:
        target = tmp_path / "token"
        target.write_text("value-from-file\n")
        assert secrets.resolve(f"file://{target}").reveal() == "value-from-file"

    def test_reads_a_dotted_key_path_from_json(self, tmp_path) -> None:
        target = tmp_path / "secrets.json"
        target.write_text(json.dumps({"jira": {"alpha": "scoped-value"}}))
        assert secrets.resolve(f"file://{target}#jira.alpha").reveal() == "scoped-value"

    def test_expands_tilde(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "token").write_text("home-relative")
        assert secrets.resolve("file://~/token").reveal() == "home-relative"

    def test_missing_file_is_a_clear_error(self, tmp_path) -> None:
        with pytest.raises(SecretError, match="not found"):
            secrets.resolve(f"file://{tmp_path / 'absent'}")

    def test_missing_key_path_is_a_clear_error(self, tmp_path) -> None:
        target = tmp_path / "secrets.json"
        target.write_text(json.dumps({"jira": {}}))
        with pytest.raises(SecretError, match="not found in"):
            secrets.resolve(f"file://{target}#jira.alpha")

    def test_non_json_file_with_a_key_path_is_a_clear_error(self, tmp_path) -> None:
        target = tmp_path / "secrets.json"
        target.write_text("just text")
        with pytest.raises(SecretError, match="not valid JSON"):
            secrets.resolve(f"file://{target}#jira.alpha")

    def test_key_path_pointing_at_a_non_string_is_an_error(self, tmp_path) -> None:
        target = tmp_path / "secrets.json"
        target.write_text(json.dumps({"jira": {"alpha": {"nested": "x"}}}))
        with pytest.raises(SecretError, match="not a string"):
            secrets.resolve(f"file://{target}#jira.alpha")


class TestOnePasswordResolver:
    def test_invokes_op_without_a_shell(self) -> None:
        """Argument-vector form, so nothing in the reference can become a command."""
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="op-value\n", stderr=""
        )

        with (
            mock.patch("shutil.which", return_value="/usr/bin/op"),
            mock.patch("subprocess.run", return_value=completed) as run,
        ):
            value = secrets.resolve("op://Private/Jira-ALPHA/credential")

        assert value.reveal() == "op-value"
        args, kwargs = run.call_args
        assert args[0] == ["op", "read", "op://Private/Jira-ALPHA/credential"]
        assert kwargs.get("shell", False) is False

    def test_missing_cli_suggests_another_backend(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with pytest.raises(SecretError, match="not installed") as caught:
                secrets.resolve("op://Private/Jira-ALPHA/credential")
        assert "env://" in caught.value.remediation

    def test_timeout_is_reported_as_a_locked_vault(self) -> None:
        with (
            mock.patch("shutil.which", return_value="/usr/bin/op"),
            mock.patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired("op", 60)
            ),
        ):
            with pytest.raises(SecretError, match="timed out") as caught:
                secrets.resolve("op://Private/Jira-ALPHA/credential")
        assert "unlock" in caught.value.remediation.lower()

    def test_failure_surfaces_stderr_for_diagnosis(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="item not found"
        )
        with (
            mock.patch("shutil.which", return_value="/usr/bin/op"),
            mock.patch("subprocess.run", return_value=completed),
        ):
            with pytest.raises(SecretError) as caught:
                secrets.resolve("op://Private/Absent/credential")
        assert "item not found" in caught.value.details["stderr"]


class TestResolveOncePerProcess:
    """Antigravity's §8.2 requirement: a backend that prompts for biometrics
    must be asked exactly once."""

    def test_backend_is_called_once_across_repeated_resolves(self, monkeypatch) -> None:
        calls = []

        class CountingResolver(secrets.SecretResolver):
            scheme = "counting"

            def resolve(self, ref):
                calls.append(ref.raw)
                return "value"

        secrets.register_resolver(CountingResolver())

        for _ in range(5):
            secrets.resolve("counting://thing")

        assert len(calls) == 1

    def test_repeated_resolves_return_the_same_object(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")
        assert secrets.resolve("env://SOME_TOKEN") is secrets.resolve(
            "env://SOME_TOKEN"
        )

    def test_different_references_are_cached_separately(self, monkeypatch) -> None:
        monkeypatch.setenv("TOKEN_A", "value-a")
        monkeypatch.setenv("TOKEN_B", "value-b")

        assert secrets.resolve("env://TOKEN_A").reveal() == "value-a"
        assert secrets.resolve("env://TOKEN_B").reveal() == "value-b"

    def test_clear_cache_forces_a_fresh_read(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "first")
        assert secrets.resolve("env://SOME_TOKEN").reveal() == "first"

        monkeypatch.setenv("SOME_TOKEN", "second")
        assert secrets.resolve("env://SOME_TOKEN").reveal() == "first", (
            "should be cached"
        )

        secrets.clear_cache()
        assert secrets.resolve("env://SOME_TOKEN").reveal() == "second"

    def test_cached_refs_lists_references_not_values(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")
        secrets.resolve("env://SOME_TOKEN")

        assert secrets.cached_refs() == ["env://SOME_TOKEN"]


class TestResolvedValuesAreContained:
    def test_result_is_a_masked_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")

        resolved = secrets.resolve("env://SOME_TOKEN")

        assert isinstance(resolved, Secret)
        assert "value-from-env" not in repr(resolved)

    def test_resolution_registers_the_value_for_redaction(self, monkeypatch) -> None:
        from core.redact import redact

        monkeypatch.setenv("SOME_TOKEN", "a-long-enough-token-value")
        secrets.resolve("env://SOME_TOKEN")

        assert "a-long-enough-token-value" not in redact(
            "leaked a-long-enough-token-value"
        )

    def test_the_reference_is_kept_because_it_is_not_secret(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")
        assert secrets.resolve("env://SOME_TOKEN").ref == "env://SOME_TOKEN"


class TestExtensibility:
    def test_a_custom_backend_can_be_registered(self) -> None:
        class VaultResolver(secrets.SecretResolver):
            scheme = "vault"

            def resolve(self, ref):
                return f"from-vault:{ref.body}"

        secrets.register_resolver(VaultResolver())

        assert secrets.resolve("vault://apps/jira").reveal() == "from-vault:apps/jira"
        assert "vault://" in secrets.available_schemes()

    def test_unknown_scheme_lists_what_is_available(self) -> None:
        with pytest.raises(SecretError, match="No resolver for scheme") as caught:
            secrets.resolve("nosuch://thing")
        assert "env://" in caught.value.remediation

    def test_a_broken_entry_point_plugin_does_not_take_the_process_down(
        self, monkeypatch
    ) -> None:
        class ExplodingEntryPoint:
            def load(self):
                raise RuntimeError("plugin is broken")

        monkeypatch.setattr(secrets, "_entry_points_loaded", False)
        monkeypatch.setattr(
            "importlib.metadata.entry_points", lambda **_: [ExplodingEntryPoint()]
        )
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")

        assert secrets.resolve("env://SOME_TOKEN").reveal() == "value-from-env"


class TestParsing:
    def test_fragment_is_optional(self) -> None:
        assert secrets.parse_ref("env://TOKEN").fragment is None

    def test_fragment_is_captured_when_present(self) -> None:
        ref = secrets.parse_ref("file://~/s.json#jira.alpha")
        assert ref.body == "~/s.json"
        assert ref.fragment == "jira.alpha"

    def test_scheme_is_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setenv("SOME_TOKEN", "value-from-env")
        assert secrets.resolve("ENV://SOME_TOKEN").reveal() == "value-from-env"

    def test_tilde_in_a_file_path_is_not_parsed_as_a_host(self) -> None:
        """urlparse would read '~' as a netloc and drop it."""
        assert secrets.parse_ref("file://~/secrets.json").body == "~/secrets.json"
