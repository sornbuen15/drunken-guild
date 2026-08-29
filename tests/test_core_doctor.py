# mypy: ignore-errors
"""The diagnostic must name the rule that chose each value, and must never
print a credential."""

import json
import urllib.error
from unittest import mock

import pytest

from core import context, doctor, paths, secrets
from core.errors import UpstreamError
from core.redact import forget_secrets
from core.registry import ProjectRegistry

V2_DOCUMENT = {
    "version": 2,
    "projects": {
        "alpha": {
            "path": None,
            "jira": {
                "url": "https://example.atlassian.net",
                "email": "someone@example.com",
                "project_key": "ALPHA",
                "credential": "env://JIRA_TOKEN_ALPHA",
            },
            "discord": {"channel_id": "123456789012345678"},
        }
    },
}


@pytest.fixture(autouse=True)  # type: ignore[misc]
def clean_state(monkeypatch, tmp_path):
    secrets.clear_cache()
    forget_secrets()
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv(paths.ENV_REGISTRY, raising=False)
    monkeypatch.delenv(paths.ENV_SOCKET, raising=False)
    monkeypatch.setenv("JIRA_TOKEN_ALPHA", "a-valid-looking-token-value")
    yield
    secrets.clear_cache()
    forget_secrets()


@pytest.fixture  # type: ignore[misc]
def registry(tmp_path) -> ProjectRegistry:
    target = tmp_path / "projects.json"
    target.write_text(json.dumps(V2_DOCUMENT), encoding="utf-8")
    return ProjectRegistry(str(target))


def _identity_response() -> mock.MagicMock:
    response = mock.MagicMock()
    response.read.return_value = json.dumps(
        {"accountId": "abc", "displayName": "R. Jakkawan"}
    ).encode()
    response.__enter__.return_value = response
    return response


def _project_response() -> mock.MagicMock:
    response = mock.MagicMock()
    response.read.return_value = json.dumps(
        {"key": "ALPHA", "name": "Alpha Web App"}
    ).encode()
    response.__enter__.return_value = response
    return response


def find(report: doctor.Report, name: str) -> doctor.Check:
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(
        f"no check named {name!r} in {[c.name for c in report.checks]}"
    )


#: Checks that describe the machine, not what a test set up. They read the
#: checkout's pyproject, its git tags and the installed tool env, so a test
#: about a registry or a socket must not be red because this machine's
#: deployment drifted. Checkpoint lesson 6: an assertion over a whole doctor
#: report is clean only where the machine happens to agree, and `develop` has
#: gone red that way before.
ENVIRONMENT_CHECKS = frozenset(
    {"version.declared", "deployment.tool_env", "deployment.mcp_pin"}
)


def failures_under_test(report: doctor.Report) -> list[str]:
    """Names of failing checks this test is actually responsible for."""
    return [
        check.name
        for check in report.checks
        if check.status == "fail" and check.name not in ENVIRONMENT_CHECKS
    ]


class TestCredentialsNeverAppear:
    def test_the_token_is_absent_from_the_whole_report(self, registry) -> None:
        with mock.patch("urllib.request.urlopen", return_value=_identity_response()):
            report = doctor.run_doctor(registry=registry)

        rendered = doctor.render(report) + json.dumps(report.to_dict())
        assert "a-valid-looking-token-value" not in rendered

    def test_the_reference_is_shown_because_that_is_the_useful_part(
        self, registry
    ) -> None:
        report = doctor.run_doctor(registry=registry, offline=True)
        assert (
            "env://JIRA_TOKEN_ALPHA" in find(report, "project.alpha.credential").detail
        )

    def test_an_upstream_error_body_is_redacted(self, registry) -> None:
        secrets.resolve("env://JIRA_TOKEN_ALPHA")
        error = UpstreamError("upstream echoed a-valid-looking-token-value")

        with mock.patch.object(
            doctor.ProjectContext, "verify_jira_identity", side_effect=error
        ):
            report = doctor.run_doctor(registry=registry)

        assert "a-valid-looking-token-value" not in json.dumps(report.to_dict())


class TestReportsWhichRuleChoseEachPath:
    def test_names_the_source_of_the_home_directory(self, registry) -> None:
        report = doctor.run_doctor(registry=registry, offline=True)
        assert f"${paths.ENV_HOME}" in find(report, "paths.home").detail

    def test_names_the_source_of_the_registry_path(self, monkeypatch, tmp_path) -> None:
        target = tmp_path / "custom.json"
        target.write_text(json.dumps(V2_DOCUMENT), encoding="utf-8")
        monkeypatch.setenv(paths.ENV_REGISTRY, str(target))

        report = doctor.run_doctor(offline=True)

        assert f"${paths.ENV_REGISTRY}" in find(report, "paths.registry").detail

    def test_names_the_registry_file_and_schema(self, registry) -> None:
        detail = find(
            doctor.run_doctor(registry=registry, offline=True), "registry.file"
        ).detail
        assert "schema v2" in detail


class TestJiraVerification:
    def test_a_working_credential_reports_who_we_are(self, registry) -> None:
        with mock.patch("urllib.request.urlopen", return_value=_identity_response()):
            report = doctor.run_doctor(registry=registry)

        check = find(report, "project.alpha.jira")
        assert check.status == "ok"
        assert "R. Jakkawan" in check.detail

    def test_a_rejected_credential_is_a_failure_not_an_empty_board(
        self, registry
    ) -> None:
        """The S4 regression, stated as a check: this is the whole reason doctor
        makes a network call at all."""
        import urllib.error

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("u", 401, "no", {}, None),
        ):
            report = doctor.run_doctor(registry=registry)

        check = find(report, "project.alpha.jira")
        assert check.status == "fail"
        assert report.failed is True
        assert "empty board" in check.remediation

    def test_offline_mode_skips_the_network_call(self, registry) -> None:
        with mock.patch("urllib.request.urlopen") as urlopen:
            report = doctor.run_doctor(registry=registry, offline=True)

        urlopen.assert_not_called()
        assert find(report, "project.alpha.jira").status == "skip"

    def test_an_unresolvable_credential_fails_with_its_remediation(
        self, monkeypatch, registry
    ) -> None:
        monkeypatch.delenv("JIRA_TOKEN_ALPHA")

        report = doctor.run_doctor(registry=registry, offline=True)

        check = find(report, "project.alpha")
        assert check.status == "fail"
        assert "JIRA_TOKEN_ALPHA" in check.detail


class TestRegistryProblems:
    def test_a_missing_registry_is_a_failure_with_the_fix(self, tmp_path) -> None:
        report = doctor.run_doctor(
            registry=ProjectRegistry(str(tmp_path / "absent.json"))
        )

        check = find(report, "registry.file")
        assert check.status == "fail"
        assert "drunken-init" in check.remediation

    def test_a_corrupt_registry_is_reported_rather_than_read_as_empty(
        self, tmp_path
    ) -> None:
        """The registry itself swallows the parse error so startup survives —
        doctor is where that gets said out loud."""
        target = tmp_path / "projects.json"
        target.write_text("{ not json", encoding="utf-8")

        report = doctor.run_doctor(registry=ProjectRegistry(str(target)))

        assert find(report, "registry.file").status == "fail"

    def test_a_v1_registry_warns_without_failing(self, tmp_path) -> None:
        target = tmp_path / "projects.json"
        target.write_text(
            json.dumps({"alpha": {"path": str(tmp_path)}}), encoding="utf-8"
        )

        report = doctor.run_doctor(registry=ProjectRegistry(str(target)), offline=True)

        assert find(report, "registry.schema").status == "warn"
        assert failures_under_test(report) == [], (
            "A v1 registry must warn, not take the whole report down."
        )


class TestDaemonSocket:
    def test_a_missing_socket_warns_rather_than_fails(self, registry) -> None:
        """Approval falls back to asking in-conversation, so this is not fatal."""
        report = doctor.run_doctor(registry=registry, offline=True)

        assert find(report, "daemon.socket").status == "warn"
        assert failures_under_test(report) == [], (
            "Approval falls back to asking in-conversation, so a missing "
            "socket must not fail the report."
        )

    def test_a_world_accessible_socket_is_a_failure(
        self, registry, monkeypatch, tmp_path
    ) -> None:
        socket = tmp_path / "daemon.sock"
        socket.write_text("")
        socket.chmod(0o666)
        monkeypatch.setenv(paths.ENV_SOCKET, str(socket))

        report = doctor.run_doctor(registry=registry, offline=True)

        check = find(report, "daemon.socket.permissions")
        assert check.status == "fail"
        assert "as the Boss" in check.detail


class TestEnvironment:
    def test_reports_the_installed_version(self, registry) -> None:
        detail = find(
            doctor.run_doctor(registry=registry, offline=True), "version.drunken-guild"
        ).detail
        assert detail

    def test_an_mcp_2x_install_is_reported_as_the_cause_of_a_dead_server(
        self, registry
    ) -> None:
        """§1.1 — the failure that produced no message anywhere."""
        real_version = doctor.version

        def fake_version(name: str) -> str:
            return "2.0.0" if name == "mcp" else real_version(name)

        with mock.patch.object(doctor, "version", fake_version):
            report = doctor.run_doctor(registry=registry, offline=True)

        check = find(report, "version.mcp")
        assert check.status == "fail"
        assert "fastmcp" in check.detail
        assert "mcp<2" in check.remediation


class TestOutputShape:
    def test_json_form_carries_a_summary_and_an_overall_verdict(self, registry) -> None:
        payload = doctor.run_doctor(registry=registry, offline=True).to_dict()

        assert set(payload) == {"ok", "summary", "checks"}
        assert set(payload["summary"]) == {"ok", "warn", "fail", "skip"}

    def test_rendered_form_shows_remediation_under_the_failing_check(
        self, tmp_path
    ) -> None:
        rendered = doctor.render(
            doctor.run_doctor(registry=ProjectRegistry(str(tmp_path / "absent.json")))
        )

        assert "FAIL" in rendered
        assert "-> " in rendered

    def test_single_project_mode_checks_only_that_project(self, registry) -> None:
        report = doctor.run_doctor(project="alpha", registry=registry, offline=True)
        assert any(check.name.startswith("project.alpha") for check in report.checks)


class TestALiveProjectKeyIsVerified:
    """DG-260. The credential working and the project existing are two facts.

    `/myself` answers the first and says nothing about the second, so a report
    built on it alone printed `OK ... (project ALPHA)` while Jira answered "No
    project could be found with key 'ALPHA'". A green line that means "the token
    is valid" but reads as "this project is fine" is worse than no line.
    """

    @staticmethod
    def _routed(project_status: int | None) -> mock.MagicMock:
        """Answer /myself, and give *project_status* to the project lookup."""

        def route(request, timeout=None):  # noqa: ANN001
            if request.full_url.endswith(context.IDENTITY_ENDPOINT):
                return _identity_response()
            if project_status is not None:
                raise urllib.error.HTTPError(
                    request.full_url, project_status, "Not Found", {}, None
                )
            return _project_response()

        return mock.MagicMock(side_effect=route)

    def test_a_missing_project_key_fails_the_check(self, registry) -> None:
        with mock.patch("urllib.request.urlopen", self._routed(404)):
            report = doctor.run_doctor(registry=registry)

        check = find(report, "project.alpha.jira")
        assert check.status == "fail", (
            "a project key Jira cannot find must not report ok — the whole "
            f"point of DG-260. Got {check.status}: {check.detail}"
        )
        assert "ALPHA" in check.detail, (
            "the failure has to name the key that was not found, or the "
            "reader has to guess which of url/email/key is wrong"
        )

    def test_a_project_that_exists_still_reports_ok(self, registry) -> None:
        with mock.patch("urllib.request.urlopen", self._routed(None)):
            report = doctor.run_doctor(registry=registry)

        check = find(report, "project.alpha.jira")
        assert check.status == "ok", (
            f"the happy path must survive the new call. Got {check.detail}"
        )
