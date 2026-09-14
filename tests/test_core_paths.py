# mypy: ignore-errors
"""Path resolution must depend on the environment, never on where the code
happens to be installed or which directory it was launched from."""

import ast
import os
import shlex
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

        assert set(described) == {"home", "registry", "auth_db"}
        assert described["registry"]["source"] == f"${paths.ENV_REGISTRY}"
        assert described["home"]["source"] == f"${paths.ENV_HOME}"


class TestSecureCommand:
    """The remedy `drunken-doctor` prints has to run on the machine reading it.

    DG-372: on Windows it printed a `chmod 700` over the state directory. The
    warning was right — that directory holds the Jira credential — but Windows
    has no chmod, so the one actionable line in the report could not be acted
    on.
    """

    @staticmethod
    def _on_windows_as(monkeypatch, username: str | None) -> None:
        """Pin both inputs the Windows branch reads, on any host.

        The username is set through the environment rather than by patching
        `getpass.getuser`, because *which* variable is consulted is part of what
        these tests are about: `getuser` reads LOGNAME, USER and LNAME before
        USERNAME, and only the last of those is the Windows account icacls can
        resolve.
        """
        monkeypatch.setattr(os, "name", "nt")
        for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
            monkeypatch.delenv(name, raising=False)
        if username is not None:
            monkeypatch.setenv("USERNAME", username)

    def test_a_directory_on_windows_gets_icacls_and_never_chmod(
        self, monkeypatch, tmp_path
    ) -> None:
        self._on_windows_as(monkeypatch, "argig")
        target = tmp_path / "state"
        target.mkdir()

        command = paths.secure_command(target)

        assert "chmod" not in command, "there is no chmod on Windows"
        assert command.startswith("icacls "), command
        assert "/inheritance:r" in command, (
            "inherited ACEs are how everyone else got access in the first place"
        )
        assert '"argig:(OI)(CI)F"' in command, (
            "a directory grants the owner full control over what it will contain"
        )
        assert f'"{target}"' in command, "a Windows home path can contain spaces"

    def test_a_file_on_windows_grants_no_inheritance(
        self, monkeypatch, tmp_path
    ) -> None:
        """(OI)(CI) on a file is meaningless — nothing is created inside one."""
        self._on_windows_as(monkeypatch, "argig")
        target = tmp_path / "auth.json"
        target.write_text("{}")

        command = paths.secure_command(target)

        assert '"argig:F"' in command, command
        assert "(OI)" not in command

    def test_a_posix_shells_username_never_reaches_icacls(
        self, monkeypatch, tmp_path
    ) -> None:
        """Git Bash, MSYS and a Docker image all set USER on Windows, and
        `getpass.getuser` returns that in preference to USERNAME. icacls
        resolves Windows accounts, so it is USERNAME or nothing."""
        self._on_windows_as(monkeypatch, "argig")
        monkeypatch.setenv("USER", "root")
        monkeypatch.setenv("LOGNAME", "root")
        target = tmp_path / "state"
        target.mkdir()

        command = paths.secure_command(target)

        assert "root" not in command, (
            "icacls would answer 'No mapping between account names and "
            "security IDs was done'"
        )
        assert '"argig:(OI)(CI)F"' in command, command

    def test_no_username_at_all_still_yields_a_runnable_command(
        self, monkeypatch, tmp_path
    ) -> None:
        """`getpass.getuser` raises OSError when nothing in the environment
        names a user — a service account, a scheduled task, a container. The
        diagnostic has to keep printing a report, so it falls back to the
        well-known OWNER RIGHTS SID, which needs no name lookup."""
        self._on_windows_as(monkeypatch, None)
        target = tmp_path / "state"
        target.mkdir()

        command = paths.secure_command(target)

        assert paths.ICACLS_OWNER_SID in command, command
        assert command.startswith("icacls "), command

    def test_a_directory_on_posix_still_gets_chmod_700(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(os, "name", "posix")
        target = tmp_path / "state"
        target.mkdir()

        assert shlex.split(paths.secure_command(target)) == [
            "chmod",
            "700",
            str(target),
        ]

    def test_a_file_on_posix_still_gets_chmod_600(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(os, "name", "posix")
        target = tmp_path / "auth.json"
        target.write_text("{}")

        assert shlex.split(paths.secure_command(target)) == [
            "chmod",
            "600",
            str(target),
        ]

    def test_a_posix_path_with_a_space_is_quoted(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(os, "name", "posix")
        target = tmp_path / "two words"
        target.mkdir()

        command = paths.secure_command(target)

        assert shlex.split(command) == ["chmod", "700", str(target)], (
            "the operator pastes this line as printed"
        )
