# mypy: ignore-errors
"""Checks that can see past this checkout — DT-252.

Checkpoint §10.7 asked for "a `doctor --all` that walks every registered project
and reports the drift". Half of that already existed: a bare `drunken-doctor`
walks every project. The half that did not is the more useful half.

**`drunken-doctor` checks the checkout it is run from.** It has no idea that
`~/.local/share/uv/tools/drunken-team/` exists, and *that* is the deployment
Antigravity's `mcp_config.json` actually launches. The gap between the two has
now caused two incidents inside four days — on 2026-08-13 the tool env was
missing every S1/S2/S8 fix for hours after they merged, and on 2026-08-16 it was
two files behind again within minutes of a merge. Both times it was found by a
hand-written `find | grep`, which is not a check.

The other half is §13's lesson: an answer that is true and unusable is barely an
answer. `X is not a git repository` was literally true of BETA and cost hours,
because the useful facts — that the path did not exist, and that a repository
sat one directory deeper — were exactly what it did not say.
"""

from __future__ import annotations

import pytest

from core import doctor


def _named(report, name):
    return next((c for c in report.checks if c.name == name), None)


class TestSeeingTheDeployment:
    def test_it_reports_what_the_installed_environment_is_missing(
        self, tmp_path
    ) -> None:
        """The whole point. A module that merged and is not deployed is the
        gap, and it has to be named — "drift detected" would send the reader
        back to the shell to find out which."""
        env = tmp_path / "tools" / "drunken-team"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core").mkdir(parents=True)
        (site / "core" / "away.py").write_text("", encoding="utf-8")

        result = doctor.compare_deployment(env, ["core.away", "core.usage"])

        assert result["present"] == ["core.away"]
        assert result["missing"] == ["core.usage"]

    def test_everything_deployed_is_reported_as_such(self, tmp_path) -> None:
        env = tmp_path / "tools" / "drunken-team"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core").mkdir(parents=True)
        for module in ("away.py", "usage.py"):
            (site / "core" / module).write_text("", encoding="utf-8")

        result = doctor.compare_deployment(env, ["core.away", "core.usage"])

        assert result["missing"] == []

    def test_a_dotted_module_resolves_to_its_nested_file(self, tmp_path) -> None:
        env = tmp_path / "tools" / "drunken-team"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "jira_mcp").mkdir(parents=True)
        (site / "jira_mcp" / "backlog.py").write_text("", encoding="utf-8")

        assert doctor.compare_deployment(env, ["jira_mcp.backlog"])["missing"] == []

    def test_a_package_directory_counts_as_deployed(self, tmp_path) -> None:
        """`core.memory` could be a package rather than a module. Missing it
        would report a false gap, which is worse than reporting none."""
        env = tmp_path / "tools" / "drunken-team"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core" / "memory").mkdir(parents=True)
        (site / "core" / "memory" / "__init__.py").write_text("", encoding="utf-8")

        assert doctor.compare_deployment(env, ["core.memory"])["missing"] == []

    def test_no_installed_environment_is_a_skip_not_a_failure(self, tmp_path) -> None:
        """A container, CI, or a fresh clone legitimately has no `uv tool`
        install. Failing there would train everyone to ignore this check, which
        is how a real finding gets missed."""
        report = doctor.Report()
        doctor._check_deployment(report, env_root=tmp_path / "absent")

        check = _named(report, "deployment.tool_env")
        assert check is not None and check.status == "skip"

    def test_a_drifted_environment_warns_and_names_the_fix(self, tmp_path) -> None:
        env = tmp_path / "tools" / "drunken-team"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core").mkdir(parents=True)

        report = doctor.Report()
        doctor._check_deployment(report, env_root=env, modules=["core.away"])

        check = _named(report, "deployment.tool_env")
        assert check.status == "warn"
        assert "core.away" in check.detail, "the reader must not have to go looking"
        assert "uv tool install" in (check.remediation or "")

    def test_it_never_reports_a_failure_as_deployed(self, tmp_path) -> None:
        """An unreadable environment is unknown, not healthy. Reporting ok here
        is the S4 shape: a reassuring answer that means nothing was checked."""
        env = tmp_path / "tools" / "drunken-team"
        env.mkdir(parents=True)

        report = doctor.Report()
        doctor._check_deployment(report, env_root=env, modules=["core.away"])

        check = _named(report, "deployment.tool_env")
        assert check.status in ("warn", "skip")
        assert check.status != "ok"


class TestAGitRootThatSaysWhatItFound:
    """`{path} is not a git repository` was true about BETA and useless.

    What the reader needed was that the path did not exist, and that a
    repository sat one level deeper. Both were knowable at the moment the
    warning was written.
    """

    def test_a_repository_one_level_deeper_is_named(self, tmp_path) -> None:
        root = tmp_path / "wrapper"
        (root / "backend" / ".git").mkdir(parents=True)

        found = doctor.describe_missing_git_root(root)

        assert "backend" in found, "the answer was one directory away"

    def test_a_path_that_does_not_exist_says_so_rather_than_blaming_git(
        self, tmp_path
    ) -> None:
        """Distinct diagnoses. "Not a repository" about a directory that is not
        there sends the reader to fix the wrong thing."""
        found = doctor.describe_missing_git_root(tmp_path / "nowhere")
        assert "does not exist" in found.lower()

    def test_nothing_nearby_is_reported_plainly(self, tmp_path) -> None:
        root = tmp_path / "empty"
        root.mkdir()
        assert doctor.describe_missing_git_root(root)

    def test_it_does_not_wander_far_looking_for_one(self, tmp_path) -> None:
        """One level down, not a filesystem walk. A `doctor` that takes a
        minute is a `doctor` nobody runs, and a repository three levels away is
        not the one that was meant."""
        root = tmp_path / "wrapper"
        (root / "a" / "b" / "c" / ".git").mkdir(parents=True)

        found = doctor.describe_missing_git_root(root)

        assert "b" not in found.split("/")[-1] or "does not" in found.lower()


class TestThePinThatIsActuallyDeployed:
    def test_a_match_is_reported_as_ok(self) -> None:
        assert doctor.compare_pin("1.28.1", "1.28.1")[0] == "ok"

    def test_a_difference_is_reported_rather_than_hidden(self) -> None:
        """`uv tool install` ignores `uv.lock`. Both may satisfy `<2` and still
        differ, and nothing has ever said so out loud."""
        status, detail = doctor.compare_pin("1.29.0", "1.28.1")
        assert status == "warn"
        assert "1.29.0" in detail and "1.28.1" in detail

    def test_an_unknown_version_is_a_skip_not_a_match(self) -> None:
        assert doctor.compare_pin(None, "1.28.1")[0] == "skip"
        assert doctor.compare_pin("1.29.0", None)[0] == "skip"


class TestItStillDoesWhatItDid:
    """Anti-regression: the checks that already worked must be untouched."""

    @pytest.mark.parametrize("name", ["version.drunken-team", "paths.home"])
    def test_the_existing_checks_are_still_produced(self, name) -> None:
        report = doctor.run_doctor(offline=True)
        assert _named(report, name) is not None

    def test_the_new_checks_never_raise_the_exit_code(self) -> None:
        """A warning is a warning. `doctor` exits non-zero only on failure, and
        a tool env that is one merge behind must not break anybody's CI.

        Asserted on the new checks alone, not on `report.failed`. The first
        version of this test asserted the whole report was clean and passed
        only because the machine it was written on happens to have a registry;
        CI has none, `registry.file` is a legitimate `fail` there, and the test
        went red for a reason that had nothing to do with what it was testing.
        A test that depends on the developer's own state is S9's two-sources
        problem wearing a different hat — and `verify_clean_install.sh` exists
        precisely because this repo keeps rediscovering it.
        """
        report = doctor.run_doctor(offline=True)

        deployment = [c for c in report.checks if c.name.startswith("deployment.")]
        assert deployment, "the new checks must run in every environment"
        assert [c for c in deployment if c.status == "fail"] == []
