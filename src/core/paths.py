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

import locale
import os
import shlex
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ENV_HOME: Final = "DRUNKEN_HOME"
ENV_REGISTRY: Final = "DRUNKEN_REGISTRY_PATH"
ENV_AUTH_DB: Final = "DRUNKEN_AUTH_DB"
ENV_SESSION_METADATA: Final = "DRUNKEN_SESSION_METADATA_PATH"

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
#: OWNER RIGHTS — "whoever owns this", resolved by the SID rather than by a
#: name lookup. The fallback for a machine whose environment names no user at
#: all: a service account, a scheduled task, a container. It grants what
#: :data:`HOME_MODE` means without having to know what to call the owner.
ICACLS_OWNER_SID: Final = "*S-1-3-4"


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


def session_metadata_path() -> ResolvedPath:
    """Local Hub session metadata, kept outside project source trees."""
    return _under_home("sessions.json", ENV_SESSION_METADATA)


def ensure_home() -> Path:
    """Create the state directory if absent and enforce owner-only access."""
    path = home().path
    path.mkdir(parents=True, exist_ok=True)
    if is_windows():
        _secure_windows_path(path)
    else:
        path.chmod(HOME_MODE)
    return path


def secure_file(path: Path) -> None:
    """Restrict *path* to the owner. Call after creating anything secret-bearing."""
    if path.exists():
        if is_windows():
            _secure_windows_path(path)
        else:
            path.chmod(SECRET_FILE_MODE)


def _secure_windows_path(path: Path) -> None:
    """Remove inherited and existing ACL entries, then grant owner access only."""
    rights = ICACLS_DIR_RIGHTS if path.is_dir() else ICACLS_FILE_RIGHTS
    commands = [
        ["icacls", str(path), "/reset"],
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{_icacls_principal()}:{rights}",
        ],
    ]
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=5,
                check=False,
                text=True,
                encoding=locale.getpreferredencoding(False),
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PermissionError(f"Could not restrict Windows ACL for {path}") from exc
        if completed.returncode != 0:
            raise PermissionError(f"Could not restrict Windows ACL for {path}")


def is_group_or_world_accessible(path: Path) -> bool:
    """True when someone other than the owner can reach *path*.

    Used by :mod:`core.doctor` rather than enforced here: on a shared machine a
    world-readable credential file is a real finding, but silently re-chmod'ing
    a path the operator chose is its own kind of surprise.

    DG-509: ``path.stat().st_mode`` is the right question on POSIX and the
    wrong one on Windows — ``pathlib`` synthesizes it there from a single
    read-only attribute bit, so a directory is reported ``0o755`` and a file
    ``0o644`` *regardless of its real ACL*. On Windows this answer always
    came back "accessible", and the warning it drives could never clear, not
    even right after running the ``icacls`` command the report itself
    printed. On Windows the ACL is asked instead; POSIX is unchanged.
    """
    if not path.exists():
        return False
    if is_windows():
        return _windows_is_group_or_world_accessible(path)
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))


#: Principals an ACE naming them does not make *is_group_or_world_accessible*
#: true: the machine's own trusted accounts, and the two spellings
#: ``icacls`` uses for "whoever owns this" when it cannot resolve a name.
#: Membership alone is not enough to trust an ACE — see
#: :func:`_windows_is_trusted_principal`: a *qualified* ACE naming one of
#: these only counts when the qualifier is itself trustworthy, never an
#: arbitrary other machine's own identically-named account or group.
_WINDOWS_TRUSTED_PRINCIPALS: Final = frozenset(
    {
        "SYSTEM",
        "ADMINISTRATORS",
        "CREATOR OWNER",
        "OWNER RIGHTS",
        ICACLS_OWNER_SID.upper(),
    }
)

#: The fixed Windows pseudo-authorities a well-known name is legitimately
#: qualified by, regardless of which machine or domain this is — unlike
#: ``FOREIGNHOST\Administrators``, ``BUILTIN\Administrators`` always means
#: the same, local, trusted group everywhere. Deliberately not extended to
#: ``NT SERVICE``: nothing in this check's current fixtures or real-world
#: ``icacls`` output needs it, and adding it un-asked would widen trust.
_WINDOWS_PSEUDO_AUTHORITIES: Final = frozenset({"BUILTIN", "NT AUTHORITY"})

#: The two lines ``icacls <path>`` ends every successful run with — never an
#: ACE, always the summary. Matched to know where the ACE lines stop,
#: independently of locale, since both start with the identical token.
_ICACLS_SUMMARY_PREFIXES: Final = ("Successfully processed", "Failed processing")


def _windows_icacls_output(path: Path) -> str | None:
    """The raw text of ``icacls <path>``, or ``None`` if it could not be run.

    Kept separate from the parsing below so a test can hand it real, captured
    output without depending on an actual Windows ACL existing on disk — and
    so a production failure to even launch ``icacls`` (missing from PATH, no
    permission to run it, a timeout) is one ``None`` the caller treats the
    same way as output it could not parse.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — no shell, fixed argv, no user input in argv[0]
            ["icacls", str(path)],
            capture_output=True,
            timeout=5,
            check=False,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _windows_icacls_principals(output: str, path: Path) -> list[str] | None:
    """The principal named on every ACE line of ``icacls`` output for *path*.

    ``icacls`` prints the path and the first ACE on one line, then every
    further ACE on its own indented line, and closes with a summary line.
    The path is stripped by exact string match — not by a column count,
    since a Windows account name may itself contain spaces — so the caller
    passes the same :class:`Path` it asked ``icacls`` about. ``None`` means
    "this did not look like real ``icacls`` output" — no summary line found,
    or no ACE recognised — and the caller must answer conservatively, not
    guess that nobody else has access.
    """
    lines = output.splitlines()
    if not lines:
        return None
    path_str = str(path)
    if lines[0].startswith(path_str):
        lines[0] = lines[0][len(path_str) :]
    principals: list[str] = []
    saw_summary = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(_ICACLS_SUMMARY_PREFIXES):
            saw_summary = True
            continue
        if ":" not in stripped:
            continue
        principal, _, _rights = stripped.partition(":")
        principal = principal.strip()
        if principal:
            principals.append(principal)
    if not saw_summary or not principals:
        return None
    return principals


def _windows_current_machine() -> str:
    """The ``MACHINE`` half of a ``MACHINE\\<user>`` ACE that means "this
    machine's own account", not merely an account of the same short name
    somewhere else.

    ``USERDOMAIN`` takes priority for the same reason ``USERNAME`` already
    does in :func:`_icacls_principal`: for a domain account it is the domain
    the account was actually issued under, where ``COMPUTERNAME`` is just
    this machine's own name and would be the wrong qualifier to trust for a
    domain account logged in from elsewhere. Read through its own function,
    not inlined, so a test can pin it without depending on the real host.
    """
    return os.environ.get("USERDOMAIN") or os.environ.get("COMPUTERNAME") or ""


def _windows_is_trusted_principal(
    full: str, current_user: str, current_machine: str
) -> bool:
    """Whether a single ACE principal (already upper-cased) is the current
    user, the owner, or one of the machine's own trusted accounts — never
    merely a name that *looks* like one.

    DG-509 re-review round 2: trusting "the current user" by its bare short
    name alone accepted ``OTHERMACHINE\\alpha`` as if it were this machine's
    own ``alpha``. Round 3: the same mistake was still there for the
    well-known names — ``FOREIGNHOST\\Administrators`` read as the trusted
    local Administrators group purely because the *name* after the ``\\``
    matched, regardless of what came before it. Both now require the
    qualifier itself to be trustworthy: unqualified, a fixed Windows
    pseudo-authority (``BUILTIN``, ``NT AUTHORITY``) for a well-known name,
    or this machine's own name/domain for either a well-known name or the
    current user. An arbitrary other qualifier trusts nothing, however
    familiar the name after the ``\\`` looks.
    """
    if "\\" in full:
        qualifier, _, name = full.partition("\\")
        qualifier = qualifier.strip()
        name = name.strip()
    else:
        qualifier, name = "", full.strip()

    if name in _WINDOWS_TRUSTED_PRINCIPALS:
        if not qualifier:
            return True
        if qualifier in _WINDOWS_PSEUDO_AUTHORITIES:
            return True
        return bool(current_machine) and qualifier == current_machine

    if name == current_user:
        if not qualifier:
            return True
        return bool(current_machine) and qualifier == current_machine

    return False


def _windows_is_group_or_world_accessible(path: Path) -> bool:
    """DG-509: accessible to others when an ACE names anyone but the current
    user, the owner, or one of the machine's own trusted accounts — an
    ``Everyone``, ``BUILTIN\\Users`` or ``NT AUTHORITY\\Authenticated Users``
    ACE included, since none of those is any one of those three. See
    :func:`_windows_is_trusted_principal` for exactly what "trusted" means.

    Unparseable or unrunnable ``icacls`` output answers ``True`` — the same,
    conservative "warn" this check always gave on Windows before DG-509 —
    rather than risk a parsing gap reading as a silent, wrong "fine".
    """
    output = _windows_icacls_output(path)
    if output is None:
        return True
    principals = _windows_icacls_principals(output, path)
    if principals is None:
        return True
    current_user = _icacls_principal().upper()
    current_machine = _windows_current_machine().upper()
    for principal in principals:
        full = principal.upper()
        if not _windows_is_trusted_principal(full, current_user, current_machine):
            return True
    return False


def is_windows() -> bool:
    """One named seam for the platform question, rather than the test scattered.

    :mod:`core.doctor` asks it about what to print; the tests patch it to report
    about the other platform without pretending to be it.
    """
    return os.name == "nt"


def _icacls_principal() -> str:
    """Who to grant to, in a form ``icacls`` can actually resolve.

    Not :func:`getpass.getuser`: it reads LOGNAME, USER and LNAME *before*
    USERNAME, and the first three are what a POSIX-shaped shell on Windows sets
    — Git Bash, MSYS, a container. icacls resolves Windows accounts, so being
    handed ``root`` from a Git Bash gets "No mapping between account names and
    security IDs was done". USERNAME is the Windows variable; it comes first.

    And when nothing names a user, `getpass.getuser` raises rather than
    returning — which would take the whole diagnostic down over one line of it.
    """
    for variable in ("USERNAME", "LOGNAME", "USER", "LNAME"):
        user = os.environ.get(variable)
        if user:
            return user
    return ICACLS_OWNER_SID


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
        principal = _icacls_principal()
        return f'icacls "{path}" /inheritance:r /grant:r "{principal}:{rights}"'
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
