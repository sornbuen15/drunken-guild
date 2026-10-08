# mypy: ignore-errors
"""The diagnostic must name the rule that chose each value, and must never
print a credential."""

import json
import shlex
import subprocess
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


#: Checks that describe the machine or the checkout, not what a test set up.
#: They read the checkout's pyproject, its git tags, the installed tool env,
#: and (DG-401) this same checkout's AGENTS.md and skills/ — so a test about
#: a registry or a socket must not be red because this machine's deployment
#: drifted, or because the checkout itself carries a routing gap these tests
#: never asked about. Checkpoint lesson 6: an assertion over a whole doctor
#: report is clean only where the machine happens to agree, and `develop` has
#: gone red that way before.
ENVIRONMENT_CHECKS = frozenset(
    {
        "version.declared",
        "deployment.tool_env",
        "deployment.mcp_pin",
        "routes.targets",
        "routes.reachable",
        # DG-466's guard.git_hooks reads this checkout's own
        # .pre-commit-config.yaml and whatever `git rev-parse --git-path
        # hooks` reports for it — real state of the machine running the
        # test, not anything a test here sets up. A clean CI checkout never
        # ran `pre-commit install`, so this fails there on every run while
        # passing on a contributor's own already-hooked machine; see
        # TestTheCheckoutsOwnHookStateNeverFailsAnUnrelatedTest below for the
        # reproduction and core.doctor.test_core_doctor_git_hooks for the
        # check's own direct, hermetic coverage of the fail path.
        "guard.git_hooks",
    }
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


class TestThePermissionsRemedyMatchesThePlatform:
    """DG-372: the warning was correct and the fix under it was unrunnable."""

    def _loose_home(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        home.chmod(0o777)
        return home

    def test_on_windows_the_home_remedy_does_not_say_chmod(
        self, monkeypatch, registry, tmp_path
    ) -> None:
        self._loose_home(tmp_path)
        monkeypatch.setattr(paths, "is_windows", lambda: True)

        report = doctor.run_doctor(registry=registry, offline=True)

        remediation = find(report, "paths.home.permissions").remediation
        assert "chmod" not in remediation, (
            "there is no chmod on Windows, so this line cannot be followed"
        )
        assert remediation.startswith("icacls "), remediation

    def test_on_windows_the_auth_db_remedy_does_not_say_chmod(
        self, monkeypatch, registry, tmp_path
    ) -> None:
        """The same line one check further down, reported the same way."""
        home = self._loose_home(tmp_path)
        auth_db = home / "auth.json"
        auth_db.write_text("{}", encoding="utf-8")
        auth_db.chmod(0o666)
        monkeypatch.setenv(paths.ENV_AUTH_DB, str(auth_db))
        monkeypatch.setattr(paths, "is_windows", lambda: True)

        report = doctor.run_doctor(registry=registry, offline=True)

        remediation = find(report, "paths.auth_db.permissions").remediation
        assert "chmod" not in remediation, remediation
        assert remediation.startswith("icacls "), remediation

    def test_a_machine_with_no_username_still_gets_a_whole_report(
        self, monkeypatch, registry, tmp_path
    ) -> None:
        """The remedy is one line of a diagnostic. Failing to name the user is
        not a reason for the other twenty checks to go unanswered."""
        self._loose_home(tmp_path)
        for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(paths, "is_windows", lambda: True)

        report = doctor.run_doctor(registry=registry, offline=True)

        assert len(report.checks) > 1
        assert find(report, "paths.home.permissions").remediation.startswith("icacls ")

    def test_on_posix_the_home_remedy_is_unchanged(
        self, monkeypatch, registry, tmp_path
    ) -> None:
        home = self._loose_home(tmp_path)
        monkeypatch.setattr(paths, "is_windows", lambda: False)

        report = doctor.run_doctor(registry=registry, offline=True)

        remediation = find(report, "paths.home.permissions").remediation
        assert shlex.split(remediation) == ["chmod", "700", str(home)], remediation


class TestARegisteredTildePathIsChecked:
    """DG-445: ``_check_project_paths`` built the checkout path with
    ``Path(config.path)`` and no ``expanduser()``, so a project registered
    with a literal ``"~/checkout"`` was treated as pointing at a directory
    named ``~`` that never exists, rather than the real checkout."""

    def _registry_with_tilde(self, tmp_path) -> ProjectRegistry:
        target = tmp_path / "projects.json"
        target.write_text(
            json.dumps({"version": 2, "projects": {"tilde": {"path": "~/checkout"}}}),
            encoding="utf-8",
        )
        return ProjectRegistry(str(target))

    def test_a_registered_tilde_path_resolves_under_the_real_home(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("HOMEDRIVE", raising=False)
        monkeypatch.delenv("HOMEPATH", raising=False)
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        report = doctor.run_doctor(
            registry=self._registry_with_tilde(tmp_path), offline=True
        )

        check = find(report, "project.tilde.path")
        assert check.status == "ok", (
            "a registered '~/checkout' that exists under the real home must "
            f"be found, not reported missing. Got {check.status}: {check.detail}"
        )
        assert str(checkout) in check.detail, check.detail

    def test_mutation_reintroducing_the_unexpanded_path_fails_the_assertion(
        self, tmp_path, monkeypatch
    ) -> None:
        """Mutation: patch ``ProjectConfig.resolved_path`` back to the
        pre-fix shape — ``Path(self.path)`` with no ``expanduser()`` — and
        confirm the check regresses to reporting the real checkout as
        missing. Seen failing first against the real (unpatched) fix before
        this mutation was added, which is what proves the mutation, not the
        assertion, is doing the work here."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.delenv("HOMEDRIVE", raising=False)
        monkeypatch.delenv("HOMEPATH", raising=False)
        checkout = tmp_path / "checkout"
        checkout.mkdir()

        from core.registry import ProjectConfig

        def _unexpanded(self, reason: str):
            from pathlib import Path

            return Path(self.require_path(reason))

        monkeypatch.setattr(ProjectConfig, "resolved_path", _unexpanded)

        report = doctor.run_doctor(
            registry=self._registry_with_tilde(tmp_path), offline=True
        )

        check = find(report, "project.tilde.path")
        assert check.status == "fail", (
            "this is the mutation's own (wrong) outcome — the real fix must "
            f"disagree with it. Got {check.status}: {check.detail}"
        )


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


_GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]

#: Runs the guard, declares both hook types, installs neither — exactly the
#: shape a clean CI checkout has (DG-466 reads `.pre-commit-config.yaml` and
#: the real `.git/hooks` of whatever `source_tree_root()` reports, so a
#: checkout that never ran `pre-commit install` fails `guard.git_hooks` on
#: its own merits, independent of whether this developer's machine happens
#: to have the hooks installed).
_GUARDED_CONFIG = (
    "default_install_hook_types: [pre-commit, commit-msg]\n"
    "repos:\n"
    "  - repo: local\n"
    "    hooks:\n"
    "      - id: check-operator-inventory\n"
    "        entry: python scripts/check_operator_inventory.py\n"
    "        language: system\n"
)


def _unhooked_guarded_repo(root) -> None:
    """A real git repo at *root* whose config runs the guard but which never
    had `pre-commit install` run against it — reproduces a clean CI checkout
    regardless of this test runner's own machine state."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    (root / ".pre-commit-config.yaml").write_text(_GUARDED_CONFIG, encoding="utf-8")
    subprocess.run(
        ["git", *_GIT_IDENTITY, "add", "-A"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", *_GIT_IDENTITY, "commit", "-m", "init", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


class TestTheCheckoutsOwnHookStateNeverFailsAnUnrelatedTest:
    """DG-466 wired `guard.git_hooks` into every `run_doctor()` call,
    including the source tree's own real `.git/hooks` — so any existing test
    asserting a whole report is clean now depends on whether *this* checkout
    happens to have run `pre-commit install`. A clean CI checkout never has,
    so this went red on `develop` for every test using `failures_under_test`
    while passing on a contributor's own already-hooked machine."""

    def test_an_unhooked_checkout_does_not_fail_a_test_about_something_else(
        self, monkeypatch, registry, tmp_path
    ) -> None:
        fake_source_tree = tmp_path / "fake-source-tree"
        _unhooked_guarded_repo(fake_source_tree)
        monkeypatch.setattr(doctor, "source_tree_root", lambda: fake_source_tree)

        report = doctor.run_doctor(registry=registry, offline=True)

        assert find(report, "guard.git_hooks").status == "fail", (
            "the fixture repo never ran pre-commit install, so the check "
            "itself must still genuinely fail — this proves the production "
            "check was not weakened to make the assertion below pass"
        )
        assert failures_under_test(report) == [], (
            "a checkout's own missing hooks are not this test's business"
        )


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
