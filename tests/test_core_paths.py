# mypy: ignore-errors
"""Path resolution must depend on the environment, never on where the code
happens to be installed or which directory it was launched from."""

import ast
import os
import stat
from pathlib import Path

import pytest

from core import paths


@pytest.fixture(autouse=True)  # type: ignore[misc]
def isolated_env(monkeypatch, tmp_path):
    """Start every test from a known-empty environment."""
    for var in (
        paths.ENV_HOME,
        paths.ENV_REGISTRY,
        paths.ENV_SOCKET,
        paths.ENV_AUTH_DB,
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


class TestNoFileDerivation:
    def test_source_never_references_dunder_file(self) -> None:
        """The §1.3 bug in one assertion: deriving state paths from __file__
        resolves inside the venv once installed as a uv tool.

        Checked against the parsed AST rather than the raw text, so prose in a
        docstring explaining the bug does not count as committing it.
        """
        tree = ast.parse(Path(paths.__file__).read_text(encoding="utf-8"))
        referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert "__file__" not in referenced

    def test_paths_are_unaffected_by_the_working_directory(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "state"))
        before = paths.registry_path().path

        monkeypatch.chdir(tmp_path)

        assert paths.registry_path().path == before


class TestHome:
    def test_defaults_under_the_user_home(self) -> None:
        assert paths.home().path == Path.home() / ".drunken"

    def test_environment_override_wins(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "elsewhere"))
        assert paths.home().path == tmp_path / "elsewhere"

    def test_override_expands_tilde(self, monkeypatch) -> None:
        monkeypatch.setenv(paths.ENV_HOME, "~/custom-drunken")
        assert paths.home().path == Path.home() / "custom-drunken"

    def test_override_expands_environment_variables(
        self, monkeypatch, tmp_path
    ) -> None:
        """launchd and container entrypoints commonly pass $XDG_STATE_HOME style values."""
        monkeypatch.setenv("SOME_BASE", str(tmp_path))
        monkeypatch.setenv(paths.ENV_HOME, "$SOME_BASE/state")
        assert paths.home().path == tmp_path / "state"

    def test_relative_override_is_made_absolute(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(paths.ENV_HOME, "relative-state")
        assert paths.home().path.is_absolute()


class TestEntries:
    def test_registry_sits_under_home_by_default(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
        assert paths.registry_path().path == tmp_path / "projects.json"

    def test_registry_env_override_wins_over_home(self, monkeypatch, tmp_path) -> None:
        """Antigravity's config already sets DRUNKEN_REGISTRY_PATH — keep it working."""
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
        monkeypatch.setenv(paths.ENV_REGISTRY, str(tmp_path / "custom.json"))
        assert paths.registry_path().path == tmp_path / "custom.json"

    def test_socket_sits_under_home_by_default(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
        assert paths.daemon_socket_path().path == tmp_path / "daemon.sock"

    def test_the_retired_agy_variable_is_ignored(self, monkeypatch, tmp_path) -> None:
        """``AGY_DAEMON_SOCKET`` was the deprecated alias, removed in DT-244
        along with the rest of the old product name.

        Asserted rather than simply deleted: silently ignoring a variable
        someone has set would point their daemon at one socket and their
        clients at another, which is the exact failure DT-241 was about.
        ``drunken-doctor`` reports the path it resolved, so a stale setting
        shows up there.
        """
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
        monkeypatch.setenv("AGY_DAEMON_SOCKET", str(tmp_path / "old.sock"))

        assert paths.daemon_socket_path().path == tmp_path / "daemon.sock"


class TestPermissions:
    def test_ensure_home_creates_owner_only_directory(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "state"))

        created = paths.ensure_home()

        assert created.is_dir()
        assert stat.S_IMODE(created.stat().st_mode) == paths.HOME_MODE

    def test_ensure_home_tightens_an_existing_loose_directory(
        self, monkeypatch, tmp_path
    ) -> None:
        loose = tmp_path / "state"
        loose.mkdir(mode=0o777)
        monkeypatch.setenv(paths.ENV_HOME, str(loose))

        paths.ensure_home()

        assert stat.S_IMODE(loose.stat().st_mode) == paths.HOME_MODE

    def test_secure_file_restricts_to_owner(self, tmp_path) -> None:
        target = tmp_path / "auth.json"
        target.write_text("{}")
        os.chmod(target, 0o644)

        paths.secure_file(target)

        assert stat.S_IMODE(target.stat().st_mode) == paths.SECRET_FILE_MODE

    def test_secure_file_is_a_noop_for_a_missing_path(self, tmp_path) -> None:
        paths.secure_file(tmp_path / "absent")

    def test_detects_a_world_readable_secret_file(self, tmp_path) -> None:
        target = tmp_path / "auth.json"
        target.write_text("{}")
        os.chmod(target, 0o644)

        assert paths.is_group_or_world_accessible(target) is True

    def test_owner_only_file_is_not_flagged(self, tmp_path) -> None:
        target = tmp_path / "auth.json"
        target.write_text("{}")
        os.chmod(target, 0o600)

        assert paths.is_group_or_world_accessible(target) is False


class TestDescribe:
    def test_reports_every_location_with_its_source(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
        monkeypatch.setenv(paths.ENV_REGISTRY, str(tmp_path / "custom.json"))

        described = paths.describe()

        assert set(described) == {"home", "registry", "daemon_socket", "auth_db"}
        assert described["registry"]["source"] == f"${paths.ENV_REGISTRY}"
        assert described["home"]["source"] == f"${paths.ENV_HOME}"
        assert described["daemon_socket"]["path"] == str(tmp_path / "daemon.sock")
