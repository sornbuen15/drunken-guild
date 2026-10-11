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


class TestWindowsPermissionsUseTheAcl:
    """DG-509: ``path.stat().st_mode`` is synthesized on Windows — a directory
    is always reported as ``0o755`` regardless of its real ACL — so this check
    was always true there and the warning it drives could never clear, even
    right after the operator ran the printed ``icacls`` command. On Windows,
    decide from the ACL ``icacls`` reports instead.
    """

    @staticmethod
    def _owner_only(path) -> str:
        """``icacls`` strips its own leading-path column by exact string
        match, not by counting characters — so this fixture must echo back
        whatever path it was actually asked about, same as the real tool."""
        return (
            f"{path} alpha:(OI)(CI)(F)\n"
            "\n"
            "Successfully processed 1 files; Failed processing 0 files.\n"
        )

    @staticmethod
    def _builtin_users(path) -> str:
        return (
            f"{path} BUILTIN\\Users:(OI)(CI)(RX)\n"
            "                          alpha:(OI)(CI)(F)\n"
            "\n"
            "Successfully processed 1 files; Failed processing 0 files.\n"
        )

    @staticmethod
    def _everyone(path) -> str:
        return (
            f"{path} Everyone:(OI)(CI)(F)\n"
            "                          alpha:(OI)(CI)(F)\n"
            "\n"
            "Successfully processed 1 files; Failed processing 0 files.\n"
        )

    def _as_windows_user(self, monkeypatch, username: str | None = "alpha") -> None:
        monkeypatch.setattr(paths, "is_windows", lambda: True)
        for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
            monkeypatch.delenv(name, raising=False)
        if username is not None:
            monkeypatch.setenv("USERNAME", username)

    def test_an_owner_only_acl_is_not_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(paths, "_windows_icacls_output", self._owner_only)

        assert paths.is_group_or_world_accessible(target) is False

    def test_builtin_users_on_the_acl_is_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        """Mutation check: a Windows branch hardcoded to always return False
        would pass the owner-only test above but must fail here."""
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(paths, "_windows_icacls_output", self._builtin_users)

        assert paths.is_group_or_world_accessible(target) is True

    def test_everyone_on_the_acl_is_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(paths, "_windows_icacls_output", self._everyone)

        assert paths.is_group_or_world_accessible(target) is True

    def test_icacls_failing_to_run_keeps_the_conservative_warning(
        self, monkeypatch, tmp_path
    ) -> None:
        """Mutation check: a Windows branch hardcoded to always return True
        would also pass this one, which is why the owner-only test above has
        to fail on it instead."""
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(paths, "_windows_icacls_output", lambda path: None)

        assert paths.is_group_or_world_accessible(target) is True

    def test_unparseable_icacls_output_keeps_the_conservative_warning(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths, "_windows_icacls_output", lambda path: "garbage, no ACEs here\n"
        )

        assert paths.is_group_or_world_accessible(target) is True

    def test_a_same_named_account_on_another_machine_is_not_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        """DG-509 re-review, HIGH: matching only the last ``\\`` component
        against USERNAME let ``OTHERMACHINE\\alpha`` pass as "the current
        user" purely because its short name matched — a fail-open. Only the
        current machine's own qualifier (or no qualifier at all) does."""
        self._as_windows_user(monkeypatch)
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.setenv("COMPUTERNAME", "HOST1")
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} OTHERMACHINE\\alpha:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is True

    def test_the_current_machine_qualified_owner_is_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        """The real-world shape of an owner ACE on a domain-joined or named
        machine: ``<COMPUTERNAME>\\<USERNAME>``, not a bare name."""
        self._as_windows_user(monkeypatch)
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.setenv("COMPUTERNAME", "HOST1")
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} HOST1\\alpha:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_owner_and_system_only_is_not_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          SYSTEM:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_owner_and_administrators_only_is_not_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          BUILTIN\\Administrators:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_owner_and_creator_owner_only_is_not_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          CREATOR OWNER:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_owner_rights_only_is_not_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        """``OWNER RIGHTS`` is the ACE itself, standing in for the owner —
        it needs no separate owner ACE alongside it."""
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} OWNER RIGHTS:(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_the_owner_sid_literal_alone_is_not_accessible_to_others(
        self, monkeypatch, tmp_path
    ) -> None:
        """DG-509 re-review round 3: the fifth trusted entry — the raw SID
        ``_icacls_principal()`` falls back to when nothing names a user — had
        no test that would notice its own deletion from the trusted set.

        A real, known username is deliberately kept here (unlike the
        no-username fallback tests elsewhere): if ``_icacls_principal()``
        also happened to return the same SID, the "is this the current
        user" branch would mask the trusted-set entry's own deletion. This
        only exercises the set membership itself.
        """
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} {paths.ICACLS_OWNER_SID}:(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_a_well_known_name_qualified_by_a_foreign_host_is_not_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        """DG-509 re-review round 3, HIGH: the round-2 fix still trusted
        ``SYSTEM``/``ADMINISTRATORS``/``CREATOR OWNER``/``OWNER RIGHTS`` with
        *any* qualifier at all — so ``FOREIGNHOST\\Administrators`` read as
        this machine's own trusted Administrators group, a fail-open on
        exactly the question this check exists to answer. A well-known name
        is only trusted unqualified, qualified by a fixed pseudo-authority
        (``BUILTIN``, ``NT AUTHORITY``), or qualified by this machine/domain
        — never by an arbitrary other one."""
        self._as_windows_user(monkeypatch)
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.setenv("COMPUTERNAME", "HOST1")
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          FOREIGNHOST\\Administrators:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is True

    def test_a_system_qualified_by_a_foreign_host_is_not_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.setenv("COMPUTERNAME", "HOST1")
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          FOREIGNHOST\\SYSTEM:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is True

    def test_a_creator_owner_qualified_by_a_foreign_host_is_not_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.setenv("COMPUTERNAME", "HOST1")
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          FOREIGNHOST\\CREATOR OWNER:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is True

    def test_builtin_qualified_administrators_is_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        """The pseudo-authority ``BUILTIN`` is a fixed Windows qualifier, not
        a machine or domain name — it is trusted regardless of the current
        machine, unlike ``FOREIGNHOST`` above."""
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          BUILTIN\\Administrators:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_nt_authority_qualified_system_is_trusted(
        self, monkeypatch, tmp_path
    ) -> None:
        self._as_windows_user(monkeypatch)
        target = tmp_path / "state"
        target.mkdir()
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: (
                f"{path} alpha:(OI)(CI)(F)\n"
                "                          NT AUTHORITY\\SYSTEM:(OI)(CI)(F)\n"
                "\n"
                "Successfully processed 1 files; Failed processing 0 files.\n"
            ),
        )

        assert paths.is_group_or_world_accessible(target) is False

    def test_posix_path_never_consults_icacls(self, monkeypatch, tmp_path) -> None:
        """is_windows() is the only seam between the two branches. Proven by
        showing the ACL path is never reached when it answers False, rather
        than by asserting on chmod'd mode bits — `st_mode` on this very host
        is pathlib's own Windows synthesis, the thing this ticket is about,
        so it cannot be the oracle for "the POSIX branch ran unchanged"."""
        monkeypatch.setattr(paths, "is_windows", lambda: False)
        calls: list[Path] = []
        monkeypatch.setattr(
            paths,
            "_windows_icacls_output",
            lambda path: calls.append(path) or "unused",
        )
        target = tmp_path / "auth.json"
        target.write_text("{}")

        paths.is_group_or_world_accessible(target)

        assert calls == [], "the POSIX branch must never consult icacls"


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
