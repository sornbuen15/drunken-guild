"""Where drunken-guild keeps its state, and how that location is decided.

The bug this replaces (MCP-ARCHITECTURE.md §1.3): two modules derived their
paths from ``__file__``. Run from a checkout that resolves to the repo and looks
correct; installed with ``uv tool install`` the same expression resolves inside
the tool's virtualenv, so the registry and the daemon socket both pointed at
``.../lib/python3.14/.agents/`` — a directory that has never existed. Neither
failed loudly. The board just came back empty and Discord just said
"unavailable".

So: **no path in this system is ever derived from ``__file__``.** State lives
under ``$DRUNKEN_HOME`` (default ``~/.drunken``), every entry is overridable by
its own environment variable, and :func:`describe` reports which rule won — the
question "where is it actually reading from?" should never require a debugger.

Overrides are what make the deployment targets work: a container mounts a secret
volume and points ``DRUNKEN_HOME`` at it; nothing else in the system has to know.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ENV_HOME: Final = "DRUNKEN_HOME"
ENV_REGISTRY: Final = "DRUNKEN_REGISTRY_PATH"
ENV_SOCKET: Final = "DRUNKEN_DAEMON_SOCKET"
ENV_AUTH_DB: Final = "DRUNKEN_AUTH_DB"
ENV_PID_REGISTRY: Final = "DRUNKEN_PID_REGISTRY"
ENV_APPROVAL_SNAPSHOT: Final = "DRUNKEN_APPROVAL_SNAPSHOT"
ENV_AWAY_FLAG: Final = "DRUNKEN_AWAY_FLAG"

DEFAULT_HOME: Final = "~/.drunken"

#: Home holds credentials and the auth database — owner only.
HOME_MODE: Final = 0o700
#: Anything inside it that may carry a secret.
SECRET_FILE_MODE: Final = 0o600


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


def daemon_socket_path() -> ResolvedPath:
    """The Discord approval daemon's socket.

    The deprecated ``AGY_DAEMON_SOCKET`` alias is gone as of DG-244: the
    product is drunken-guild, and nothing we own keeps the old name. Removing a
    deprecated alias ahead of 3.0.0 is a deliberate call — nothing in this repo
    set it, and Antigravity's config does not either, so it had no users left
    to break. ``DRUNKEN_DAEMON_SOCKET`` is the override.
    """
    return _under_home("daemon.sock", ENV_SOCKET)


def auth_db_path() -> ResolvedPath:
    """Bearer-token database for HTTP mode. Consumed from 2.4.0 onwards."""
    return _under_home("auth.json", ENV_AUTH_DB)


def approval_snapshot_path() -> ResolvedPath:
    """Pending approvals and answers nobody has collected yet.

    The only thing between a daemon restart and a lost approval, which is why
    it is state rather than something that may sit next to a checkout.
    """
    return _under_home("approvals.json", ENV_APPROVAL_SNAPSHOT)


def pid_registry_path() -> ResolvedPath:
    """PIDs of agent subprocesses, kept on disk so they survive a daemon crash.

    A fresh runner starts with no handle on a child orphaned by the previous
    process instance, so this is how those get reaped. It is state, not code —
    hence here rather than next to the module that writes it.
    """
    return _under_home("pids.json", ENV_PID_REGISTRY)


def away_flag_path() -> ResolvedPath:
    """Whether the Boss is away, in a form the *machine* can read.

    "I'm going out, send it to Discord" has only ever reached the model, which
    is why saying it never worked: the harness asks for permission before the
    model is involved at all, and no instruction can redirect a question the
    model never sees. A file can. ``DRUNKEN_AWAY_FLAG`` is the override.
    """
    return _under_home("away.json", ENV_AWAY_FLAG)


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


def describe() -> dict[str, dict[str, str]]:
    """Every resolved location with the rule that produced it, for diagnostics."""
    return {
        name: {"path": str(resolved.path), "source": resolved.source}
        for name, resolved in (
            ("home", home()),
            ("registry", registry_path()),
            ("daemon_socket", daemon_socket_path()),
            ("auth_db", auth_db_path()),
        )
    }
