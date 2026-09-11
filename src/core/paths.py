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
import re
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


def daemon_socket_path(project: str | None = None) -> ResolvedPath:
    """The Discord approval daemon's socket, one per project.

    DG-313: the socket used to be a single ``daemon.sock`` for the whole
    machine, so every project's MCP server reached the same daemon and that
    daemon answered with whichever channel it had been pinned to. Approvals
    raised by alpha and beta posted into drunken-guild's room and reported
    success. The channel is read once at daemon start and handed to
    ``ApprovalManager`` at construction, so no per-request argument could have
    fixed it -- the split has to be one daemon per project.

    ``project`` is taken from the caller when given, else ``DRUNKEN_PROJECT``.
    Naming the socket after the project is what makes the two ends meet without
    a second knob to keep in sync: the MCP server passes ``--project alpha`` and
    dials ``daemon-alpha.sock``; the daemon started with ``DRUNKEN_PROJECT=alpha``
    binds the same name. Neither has to be told the other's socket.

    With neither set the name stays ``daemon.sock``, so a single-project machine
    behaves exactly as before.

    The deprecated ``AGY_DAEMON_SOCKET`` alias is gone as of DG-244.
    ``DRUNKEN_DAEMON_SOCKET`` remains the override and still wins outright --
    it names a path, so it cannot be per-project.
    """
    name = _project_scope(project)
    filename = f"daemon-{_slug(name)}.sock" if name else "daemon.sock"
    return _under_home(filename, ENV_SOCKET)


def _project_scope(project: str | None) -> str:
    """Which project a per-project state file belongs to, or ``""`` for none.

    DG-318: this was written out twice — once for the socket, once for the
    approval snapshot — and two copies of one rule is the failure this
    repository exists to cure. It matters more here than most places: a machine
    where the socket resolved to alpha and the snapshot to beta would answer in
    the right room and persist into the wrong file, which is harder to see than
    either half being wrong, because both look correct on their own.

    The order is the project's own and is stated in
    :func:`daemon_socket_path`: an explicit argument, then ``DRUNKEN_PROJECT``,
    then the registered project whose path contains cwd. Nothing climbs, and
    nothing guesses from a directory name.
    """
    return (
        project or os.environ.get("DRUNKEN_PROJECT", "").strip() or _project_from_cwd()
    )


def _project_from_cwd() -> str:
    """The registered project whose path contains the working directory.

    The daemon knows its project from ``DRUNKEN_PROJECT`` in its plist, but the
    processes that dial it do not: the pre-commit approval check, the away-mode
    PreToolUse hook and ``drunken-doctor`` all run from a plain shell. Without
    this they would keep resolving ``daemon.sock`` while the daemon had moved to
    ``daemon-<project>.sock``, and the approval gate would go quiet -- a
    regression introduced by the very change that split the socket.

    Matched on the registry entry's own ``path``, never guessed from the
    directory name: a checkout is not required to be named after its key.
    Returns ``""`` when nothing matches, which keeps the un-suffixed name.

    Never raises. An unreadable registry is a first run before ``drunken-init``,
    and resolving a path must not be the thing that kills a hook (principle 8).
    """
    try:
        from core.registry import ProjectRegistry

        cwd = os.path.realpath(os.getcwd())
        best, best_len = "", -1
        for key, entry in ProjectRegistry().get_projects().items():
            # get_projects() yields plain dicts today; tolerate an object too,
            # so this does not silently stop matching if that type changes.
            raw = (
                entry.get("path")
                if isinstance(entry, dict)
                else getattr(entry, "path", None)
            ) or ""
            if not raw:
                continue
            root = os.path.realpath(_expand(str(raw)))
            if cwd == root or cwd.startswith(root.rstrip("/") + "/"):
                # Longest match wins, so a checkout nested inside another
                # project's wrapper resolves to the inner one.
                if len(root) > best_len:
                    best, best_len = key, len(root)
        return best
    except Exception:
        return ""


def _slug(name: str) -> str:
    """A project id reduced to what is safe in a filename.

    A registry key is operator input. It reaches a path here, so anything that
    is not a plain word becomes ``-`` rather than being trusted -- a key
    containing ``/`` or ``..`` would otherwise choose the directory.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "-", name).strip("-.") or "unnamed"


def auth_db_path() -> ResolvedPath:
    """Bearer-token database for HTTP mode. Consumed from 2.4.0 onwards."""
    return _under_home("auth.json", ENV_AUTH_DB)


def approval_snapshot_path(project: str | None = None) -> ResolvedPath:
    """Pending approvals and answers nobody has collected yet, one set per project.

    The only thing between a daemon restart and a lost approval, which is why
    it is state rather than something that may sit next to a checkout.

    DG-318: this was a single ``approvals.json`` for the whole machine while
    :func:`daemon_socket_path` — three functions above — was already per
    project. :meth:`ApprovalManager._snapshot` rewrites the whole file from its
    own memory, so with a daemon per project the last one to write erased the
    others. Seen the day DG-313 was deployed: three approvals were granted,
    all three read ``approved`` in memory, and one survived on disk.

    The restart is the worse half. ``recover_from_snapshot()`` read the shared
    file and adopted requests belonging to other projects, re-posting them into
    *this* daemon's room and commenting on a foreign ticket through its own Jira
    client — the cross-project posting DG-313 removed, reached through the state
    instead of the socket.

    Resolution is :func:`_project_scope`, the same rule the socket uses and
    deliberately not a second one. With nothing to resolve the name stays
    ``approvals.json``, so a single-project machine is unchanged.
    ``DRUNKEN_APPROVAL_SNAPSHOT`` still wins outright — it names a path, so it
    cannot be per-project.
    """
    name = _project_scope(project)
    filename = f"approvals-{_slug(name)}.json" if name else "approvals.json"
    return _under_home(filename, ENV_APPROVAL_SNAPSHOT)


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
