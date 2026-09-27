# mypy: ignore-errors
"""Checks that can see past this checkout — DG-252.

Checkpoint §10.7 asked for "a `doctor --all` that walks every registered project
and reports the drift". Half of that already existed: a bare `drunken-doctor`
walks every project. The half that did not is the more useful half.

**`drunken-doctor` checks the checkout it is run from.** It has no idea that
`~/.local/share/uv/tools/<package>/` exists, and *that* is the deployment
Antigravity's `mcp_config.json` actually launches. That directory is named after
the distribution, so DG-264's rename moved it -- see the legacy-root case in
`test_ai_layer_drift.py`. The gap between the two has
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

from pathlib import Path

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
        env = tmp_path / "tools" / "drunken-guild"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core").mkdir(parents=True)
        (site / "core" / "away.py").write_text("", encoding="utf-8")

        result = doctor.compare_deployment(env, ["core.away", "core.usage"])

        assert result["present"] == ["core.away"]
        assert result["missing"] == ["core.usage"]

    def test_everything_deployed_is_reported_as_such(self, tmp_path) -> None:
        env = tmp_path / "tools" / "drunken-guild"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core").mkdir(parents=True)
        for module in ("away.py", "usage.py"):
            (site / "core" / module).write_text("", encoding="utf-8")

        result = doctor.compare_deployment(env, ["core.away", "core.usage"])

        assert result["missing"] == []

    def test_a_dotted_module_resolves_to_its_nested_file(self, tmp_path) -> None:
        env = tmp_path / "tools" / "drunken-guild"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "jira_mcp").mkdir(parents=True)
        (site / "jira_mcp" / "backlog.py").write_text("", encoding="utf-8")

        assert doctor.compare_deployment(env, ["jira_mcp.backlog"])["missing"] == []

    def test_a_package_directory_counts_as_deployed(self, tmp_path) -> None:
        """`core.memory` could be a package rather than a module. Missing it
        would report a false gap, which is worse than reporting none."""
        env = tmp_path / "tools" / "drunken-guild"
        site = env / "lib" / "python3.13" / "site-packages"
        (site / "core" / "memory").mkdir(parents=True)
        (site / "core" / "memory" / "__init__.py").write_text("", encoding="utf-8")

        assert doctor.compare_deployment(env, ["core.memory"])["missing"] == []

    def test_no_installed_environment_is_a_skip_not_a_failure(self, tmp_path) -> None:
        """A container, CI, or a fresh clone legitimately has no `uv tool`
        install. Failing there would train everyone to ignore this check, which
        is how a real finding gets missed."""
        report = doctor.Report()
        # `legacy_roots` is passed explicitly so this asserts the code, not the
        # machine: an install under the previous package name is a *different*
        # answer (a warn, see test_ai_layer_drift), and whether one exists is
        # not something this test should depend on.
        doctor._check_deployment(report, env_root=tmp_path / "absent", legacy_roots=())

        check = _named(report, "deployment.tool_env")
        assert check is not None and check.status == "skip"

    def test_a_drifted_environment_warns_and_names_the_fix(self, tmp_path) -> None:
        env = tmp_path / "tools" / "drunken-guild"
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
        env = tmp_path / "tools" / "drunken-guild"
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

    @pytest.mark.parametrize("name", ["version.drunken-guild", "paths.home"])
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


class TestSeeingThatTheDeployedCodeIsStale:
    """DG-278. Presence is not currency.

    `compare_deployment` asks whether a module *exists* in the deployment, so a
    file that merged an hour ago and a file three months old read identically.
    On 2026-08-23 that printed `ok ... carries all 7 checked modules` while the
    installed tree was 22 files behind `develop` — and the gap contained
    DG-275's security fix, so the bridge the daemon runs was still walking up
    the tree for a `.env`. Nothing on any surface said so.
    """

    @staticmethod
    def _tree(root, source_text: str, deployed_text: str):
        """A source checkout and an install of it, agreeing or not."""
        src = root / "checkout" / "src" / "core"
        src.mkdir(parents=True)
        (src / "away.py").write_text(source_text, encoding="utf-8")

        site = root / "tools" / "drunken-guild" / "lib" / "python3.13" / "site-packages"
        (site / "core").mkdir(parents=True)
        (site / "core" / "away.py").write_text(deployed_text, encoding="utf-8")

        return root / "checkout", root / "tools" / "drunken-guild"

    def test_a_deployed_file_that_differs_is_reported(self, tmp_path) -> None:
        source, env = self._tree(tmp_path, "def fixed(): ...\n", "def broken(): ...\n")

        result = doctor.compare_deployed_content(env, source, ["core"])

        assert result["stale"] == ["core/away.py"], (
            "the stale file has to be named — 'drift detected' sends the reader "
            "back to the shell to find out which, which is how DG-275 stayed "
            f"undeployed. Got {result}"
        )

    def test_identical_content_is_not_reported_as_stale(self, tmp_path) -> None:
        source, env = self._tree(tmp_path, "same\n", "same\n")

        result = doctor.compare_deployed_content(env, source, ["core"])

        assert result["stale"] == [], (
            f"a current deployment must be quiet. Got {result}"
        )

    def test_the_check_warns_rather_than_reporting_ok(self, tmp_path) -> None:
        """The failure mode was a green line, so the assertion is about status,
        not about wording."""
        source, env = self._tree(tmp_path, "def fixed(): ...\n", "def broken(): ...\n")
        report = doctor.Report()

        doctor._check_deployment(
            report, env_root=env, modules=["core.away"], source_root=source
        )

        check = _named(report, "deployment.tool_env")
        assert check.status == "warn", (
            "a deployment running different code from the checkout must never "
            f"read ok — that is the whole of DG-278. Got {check.status}: {check.detail}"
        )
        assert "away.py" in check.detail, "the reader needs the file name"
        assert "reinstall" in (check.remediation or "").lower(), (
            "the remedy is one command and the report should carry it"
        )

    def test_no_source_tree_to_compare_against_is_not_a_failure(self, tmp_path) -> None:
        """Run from the installed binary there is no checkout, which is the
        honest answer rather than a complaint — same rule `ai_layer.source`
        already follows."""
        source, env = self._tree(tmp_path, "a\n", "b\n")
        report = doctor.Report()

        doctor._check_deployment(
            report, env_root=env, modules=["core.away"], source_root=None
        )

        check = _named(report, "deployment.tool_env")
        assert check.status in ("ok", "skip"), (
            f"no source tree must not manufacture a drift report. Got {check.status}"
        )


class TestFindingUvsToolDirectory:
    """DG-373. The tool root was `~/.local/share/uv/tools` on every platform,
    and uv on Windows keeps it under `%APPDATA%`. So on Windows the check looked
    somewhere nothing is ever installed, said SKIP, and the gap it exists to
    catch — merged but not deployed — was never reported there.

    Resolved in uv's own order of precedence rather than reconstructed from one
    platform's convention: `UV_TOOL_DIR`, then uv itself, then the default.
    """

    @pytest.fixture(autouse=True)
    def _no_overrides(self, monkeypatch) -> None:
        monkeypatch.delenv("UV_TOOL_DIR", raising=False)
        monkeypatch.delenv(doctor.ENV_TOOL_ROOT, raising=False)

    @staticmethod
    def _no_uv(monkeypatch) -> None:
        monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    @staticmethod
    def _uv_says(monkeypatch, stdout: str, returncode: int = 0) -> list:
        calls: list = []

        def run(argv, **kwargs):
            calls.append(argv)
            return doctor.subprocess.CompletedProcess(argv, returncode, stdout, "")

        monkeypatch.setattr(doctor.shutil, "which", lambda name: "/bin/uv")
        monkeypatch.setattr(doctor.subprocess, "run", run)
        return calls

    def test_uv_tool_dir_env_wins_without_asking_uv(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "custom"))
        calls = self._uv_says(monkeypatch, str(tmp_path / "elsewhere"))

        assert doctor.uv_tool_dir() == tmp_path / "custom"
        assert calls == [], "an explicit setting needs no subprocess"

    def test_uv_on_path_is_asked(self, tmp_path, monkeypatch) -> None:
        calls = self._uv_says(monkeypatch, f"{tmp_path / 'from-uv'}\n")

        assert doctor.uv_tool_dir() == tmp_path / "from-uv"
        assert calls == [["/bin/uv", "tool", "dir"]]

    def test_a_uv_that_fails_falls_back_to_the_default(self, monkeypatch) -> None:
        self._uv_says(monkeypatch, "", returncode=2)

        assert doctor.uv_tool_dir() == doctor.default_uv_tool_dir()

    def test_windows_default_is_under_appdata(self, tmp_path, monkeypatch) -> None:
        """The case the ticket is about: the path uv really uses on Windows."""
        monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

        assert (
            doctor.default_uv_tool_dir("win32") == tmp_path / "Roaming" / "uv" / "tools"
        )

    def test_posix_default_is_unchanged(self) -> None:
        expected = Path("~/.local/share/uv/tools").expanduser()

        assert doctor.default_uv_tool_dir("linux") == expected
        assert doctor.default_uv_tool_dir("darwin") == expected

    def test_the_tool_env_is_named_after_the_package_inside_that_dir(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path))

        assert doctor.tool_env_root() == tmp_path / "drunken-guild"

    def test_the_explicit_override_still_outranks_uv(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "uv"))
        monkeypatch.setenv(doctor.ENV_TOOL_ROOT, str(tmp_path / "pinned"))

        assert doctor.tool_env_root() == tmp_path / "pinned"

    def test_the_legacy_install_is_looked_for_in_the_same_dir(
        self, tmp_path, monkeypatch
    ) -> None:
        """The pre-rename root was hardcoded to the same POSIX path, so on
        Windows it was just as blind."""
        monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path))
        (tmp_path / "drunken-team").mkdir()

        report = doctor.Report()
        doctor._check_deployment(report)

        check = _named(report, "deployment.tool_env")
        assert check.status == "warn"
        assert "previous package name" in check.detail

    def test_a_windows_venv_layout_is_read(self, tmp_path) -> None:
        """A Windows venv has `Lib/site-packages`, with no python-version
        directory between them. Finding the root and then reading none of it
        would turn a false SKIP into a false "everything missing"."""
        env = tmp_path / "drunken-guild"
        site = env / "Lib" / "site-packages"
        (site / "core").mkdir(parents=True)
        (site / "core" / "usage.py").write_text("", encoding="utf-8")

        assert doctor.compare_deployment(env, ["core.usage"])["missing"] == []
