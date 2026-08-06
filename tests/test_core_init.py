# mypy: ignore-errors
"""Setup must be scriptable, idempotent, and incapable of storing a token."""

import json
import stat

import pytest

from core import init, paths


@pytest.fixture(autouse=True)  # type: ignore[misc]
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "state"))
    monkeypatch.delenv(paths.ENV_REGISTRY, raising=False)
    return tmp_path


def run(*argv: str, monkeypatch=None) -> int:
    import sys

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", ["drunken-init", *argv])
        return init.main()


def registry_contents(tmp_path) -> dict:
    return json.loads(
        (tmp_path / "state" / "projects.json").read_text(encoding="utf-8")
    )


class TestBootstrap:
    def test_creates_the_state_directory_owner_only(self, tmp_path) -> None:
        assert run() == 0

        state = tmp_path / "state"
        assert state.is_dir()
        assert stat.S_IMODE(state.stat().st_mode) == paths.HOME_MODE

    def test_writes_an_empty_v2_registry(self, tmp_path) -> None:
        run()
        assert registry_contents(tmp_path) == {"version": 2, "projects": {}}

    def test_registers_a_project(self, tmp_path) -> None:
        project = tmp_path / "proj"
        project.mkdir()

        assert run("--project", "sample", "--path", str(project)) == 0
        assert registry_contents(tmp_path)["projects"]["sample"]["path"] == str(project)

    def test_path_is_optional_for_a_containerised_project(self, tmp_path) -> None:
        assert run("--project", "api-only") == 0
        assert registry_contents(tmp_path)["projects"]["api-only"] == {}

    def test_a_missing_path_is_rejected_with_the_reason(self, tmp_path, capsys) -> None:
        assert run("--project", "sample", "--path", str(tmp_path / "absent")) == 1
        assert "does not exist" in capsys.readouterr().out

    def test_an_invalid_project_id_is_rejected(self, tmp_path, capsys) -> None:
        assert run("--project", "../escape") == 1
        assert "Invalid project id" in capsys.readouterr().out


class TestNoSecretCanBeStored:
    """There is deliberately no flag that accepts a token."""

    def test_a_bare_token_is_refused(self, tmp_path, capsys) -> None:
        code = run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
        )

        assert code == 1
        assert "no scheme" in capsys.readouterr().out

    def test_the_refusal_does_not_echo_the_token(self, tmp_path, capsys) -> None:
        run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
        )
        assert "ATATT3xFfGF0-EXAMPLE" not in capsys.readouterr().out

    def test_nothing_is_written_when_the_credential_is_refused(self, tmp_path) -> None:
        run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
        )
        assert not (tmp_path / "state" / "projects.json").exists()

    def test_a_reference_is_accepted_and_stored_verbatim(self, tmp_path) -> None:
        assert (
            run(
                "--project",
                "sample",
                "--jira-url",
                "https://example.atlassian.net",
                "--jira-email",
                "someone@example.com",
                "--jira-project-key",
                "SMP",
                "--jira-credential",
                "env://SAMPLE_TOKEN",
            )
            == 0
        )

        jira = registry_contents(tmp_path)["projects"]["sample"]["jira"]
        assert jira["credential"] == "env://SAMPLE_TOKEN"

    def test_partial_jira_options_are_rejected_rather_than_half_written(
        self, tmp_path, capsys
    ) -> None:
        code = run("--project", "sample", "--jira-url", "https://example.atlassian.net")

        assert code == 1
        assert "Incomplete Jira options" in capsys.readouterr().out


class TestIdempotence:
    def test_rerunning_is_safe(self, tmp_path) -> None:
        project = tmp_path / "proj"
        project.mkdir()

        run("--project", "sample", "--path", str(project))
        run("--project", "sample", "--path", str(project))

        assert list(registry_contents(tmp_path)["projects"]) == ["sample"]

    def test_updating_one_field_leaves_the_others_alone(self, tmp_path) -> None:
        """A provisioning script that sets the path must not wipe Jira."""
        run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "env://SAMPLE_TOKEN",
        )
        project = tmp_path / "proj"
        project.mkdir()
        run("--project", "sample", "--path", str(project))

        entry = registry_contents(tmp_path)["projects"]["sample"]
        assert entry["path"] == str(project)
        assert entry["jira"]["project_key"] == "SMP"

    def test_a_second_project_joins_the_first(self, tmp_path) -> None:
        run("--project", "one")
        run("--project", "two")

        assert sorted(registry_contents(tmp_path)["projects"]) == ["one", "two"]


class TestV1Migration:
    def test_a_v1_registry_is_wrapped_only_when_the_operator_asks(
        self, tmp_path
    ) -> None:
        """Reading a v1 file never rewrites it; running drunken-init is the
        explicit request that does."""
        state = tmp_path / "state"
        state.mkdir(parents=True)
        (state / "projects.json").write_text(
            json.dumps({"legacy": {"path": "/abs/legacy"}}), encoding="utf-8"
        )

        assert run("--project", "fresh") == 0

        document = registry_contents(tmp_path)
        assert document["version"] == 2
        assert document["projects"]["legacy"]["path"] == "/abs/legacy"
        assert "fresh" in document["projects"]

    def test_a_malformed_registry_is_reported_not_overwritten(
        self, tmp_path, capsys
    ) -> None:
        state = tmp_path / "state"
        state.mkdir(parents=True)
        (state / "projects.json").write_text("[]", encoding="utf-8")

        assert run("--project", "fresh") == 1
        assert "not a JSON object" in capsys.readouterr().out


class TestOutput:
    def test_points_at_the_next_step(self, tmp_path, capsys) -> None:
        run("--project", "sample")
        assert "drunken-doctor" in capsys.readouterr().out

    def test_there_is_no_flag_that_takes_a_token(self) -> None:
        """The guarantee is structural: if no flag accepts a value, a value
        cannot be stored — or land in shell history."""
        options = {
            action.dest
            for action in init.build_parser()._actions  # noqa: SLF001
        }
        assert "jira_token" not in options
        assert "discord_token" not in options
        assert "jira_credential" in options
