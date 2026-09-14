"""Where drunken-guild keeps its state, and how that location is decided.

The bug this replaces (MCP-ARCHITECTURE.md §1.3): two modules derived their
paths from ``__file__``. Run from a checkout that resolves to the repo and looks
correct; installed with ``uv tool install`` the same expression resolves inside
the tool's virtualenv, so the registry and the rest of the state pointed at
``.../lib/python3.14/.agents/`` — a directory that has never existed. Neither
failed loudly. The board just came back empty.

So: **no path in this system is ever derived from ``__file__``.** State lives
under ``$DRUNKEN_HOME`` (default ``~/.drunken``), every entry is overridable by
its own environment variable, and :func:`describe` reports which rule won — the
question "where is it actually reading from?" should never require a debugger.

Overrides are what make the deployment targets work: a container mounts a secret
volume and points ``DRUNKEN_HOME`` at it; nothing else in the system has to know.
"""

from __future__ import annotations

import getpass
import os
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ENV_HOME: Final = "DRUNKEN_HOME"
ENV_REGISTRY: Final = "DRUNKEN_REGISTRY_PATH"
ENV_AUTH_DB: Final = "DRUNKEN_AUTH_DB"

DEFAULT_HOME: Final = "~/.drunken"

#: Home holds credentials and the auth database — owner only.
HOME_MODE: Final = 0o700
#: Anything inside it that may carry a secret.
SECRET_FILE_MODE: Final = 0o600

#: The NTFS equivalent of :data:`HOME_MODE`: full control for the owner, and the
#: same for everything created inside the directory later. ``OI`` is object
#: inherit, ``CI`` container inherit.
ICACLS_DIR_RIGHTS: Final = "(OI)(CI)F"
#: The same for a single file. Nothing is created inside a file, so the inherit
#: flags would be noise in a line an operator has to read and trust.
ICACLS_FILE_RIGHTS: Final = "F"


@dataclass(frozen=True)
class ResolvedPath:
    """A path plus the rule that produced it, so :mod:`core.doctor` can explain."""

    path: Path
    source: str

    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)


def _expand(raw: str) -> Path:
    """Expand ``~`` and ``$VAR`` then make absolute.

    Container and launchd environments routinely pass one or the other, and a
    relative override would quietly reintroduce the cwd dependence this module
    exists to remove.
    """
    return Path(os.path.expandvars(os.path.expanduser(raw))).absolute()


def home() -> ResolvedPath:
    """The state directory. Does not create it — see :func:`ensure_home`."""
    override = os.environ.get(ENV_HOME)
    if override:
        return ResolvedPath(_expand(override), f"${ENV_HOME}")
    return ResolvedPath(_expand(DEFAULT_HOME), f"default ({DEFAULT_HOME})")


def _under_home(filename: str, env_var: str) -> ResolvedPath:
    override = os.environ.get(env_var)
    if override:
        return ResolvedPath(_expand(override), f"${env_var}")
    base = home()
    return ResolvedPath(base.path / filename, f"{base.source} + /{filename}")


def registry_path() -> ResolvedPath:
    """The central project registry.

    ``DRUNKEN_REGISTRY_PATH`` is the override, and it is what a container
    pointing at a mounted file uses. This used to claim Antigravity's config
    already sets it; checked in DG-246, it does not — that config declared no
    drunken-guild server at all until DG-246 added them, and it sets no
    environment for them.
    """
    return _under_home("projects.json", ENV_REGISTRY)


def auth_db_path() -> ResolvedPath:
    """Bearer-token database for HTTP mode. Consumed from 2.4.0 onwards."""
    return _under_home("auth.json", ENV_AUTH_DB)


def ensure_home() -> Path:
    """Create the state directory if absent and enforce owner-only access."""
    path = home().path
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(HOME_MODE)
    return path


def secure_file(path: Path) -> None:
    """Restrict *path* to the owner. Call after creating anything secret-bearing."""
    if path.exists():
        path.chmod(SECRET_FILE_MODE)


def is_group_or_world_accessible(path: Path) -> bool:
    """True when someone other than the owner can reach *path*.

    Used by :mod:`core.doctor` rather than enforced here: on a shared machine a
    world-readable credential file is a real finding, but silently re-chmod'ing
    a path the operator chose is its own kind of surprise.
    """
    if not path.exists():
        return False
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))


def is_windows() -> bool:
    """One named seam for the platform question, rather than the test scattered.

    :mod:`core.doctor` asks it about what to print; the tests patch it to report
    about the other platform without pretending to be it.
    """
    return os.name == "nt"


def secure_command(path: Path) -> str:
    """The command that restricts *path* to its owner, for *this* machine.

    ``drunken-doctor`` prints this under the warning and an operator pastes it
    as printed. DG-372: on Windows it printed ``chmod``, which does not exist
    there — the warning was correct and the only actionable line under it could
    not be followed. Printing both platforms' commands would leave the reader
    to work out which one is theirs, so the platform is detected instead.
    """
    if is_windows():
        rights = ICACLS_DIR_RIGHTS if path.is_dir() else ICACLS_FILE_RIGHTS
        # Quoted unconditionally: the default home sits under C:\Users\<name>,
        # and a Windows account name is allowed to contain spaces.
        return f'icacls "{path}" /inheritance:r /grant:r "{getpass.getuser()}:{rights}"'
    mode = HOME_MODE if path.is_dir() else SECRET_FILE_MODE
    return f"chmod {oct(mode)[2:]} {shlex.quote(str(path))}"


def describe() -> dict[str, dict[str, str]]:
    """Every resolved location with the rule that produced it, for diagnostics."""
    return {
        name: {"path": str(resolved.path), "source": resolved.source}
        for name, resolved in (
            ("home", home()),
            ("registry", registry_path()),
            ("auth_db", auth_db_path()),
        )
    }
