"""``drunken-doctor`` — one command that answers "why isn't this working?".

Every failure in MCP-ARCHITECTURE.md §1 shared a shape: the system kept working,
quietly, on the wrong thing. A registry read from a path that did not exist. A
credential taken from a stale ``.env`` four directories up. A board that looked
empty because the token had expired. None of them produced an error anyone could
see, and finding each one took a debugging session.

So this reports not only whether each piece resolved, but **which rule chose
it** — the path, the source of the path, the reference a credential came from.
"It says env://JIRA_TOKEN_ALPHA and that variable is unset" ends the investigation
immediately.

Values never appear in the output, only references and outcomes. The report is
put through :func:`~core.redact.redact` on the way out regardless, because it
quotes upstream error bodies.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404 - git, invoked with a fixed argument list
import sys
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Final, Literal, Optional, Sequence

from . import ai_layer, content_scan, paths, secrets
from .config_gen import (
    count_pins,
    export_requirements,
    install_command,
    is_drunken_managed,
)
from .context import ProjectContext
from .errors import DrunkenError
from .exclude import GitTimedOutError, NotAGitRepositoryError, run_git
from .layer_copy import ai_layer_files_under
from .redact import redact
from .registry import ProjectRegistry

Status = Literal["ok", "warn", "fail", "skip"]

_SYMBOLS: Final[dict[str, str]] = {
    "ok": "OK  ",
    "warn": "WARN",
    "fail": "FAIL",
    "skip": "SKIP",
}


@dataclass
class Check:
    """One question asked and answered."""

    name: str
    status: Status
    detail: str
    remediation: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = {k: v for k, v in asdict(self).items() if v is not None}
        data["detail"] = redact(data["detail"])
        if "remediation" in data:
            data["remediation"] = redact(data["remediation"])
        return data


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(
        self,
        name: str,
        status: Status,
        detail: str,
        remediation: Optional[str] = None,
    ) -> None:
        self.checks.append(Check(name, status, detail, remediation))

    def add_error(self, name: str, exc: Exception) -> None:
        """Record a failure, keeping the remediation when there is one."""
        remediation = exc.remediation if isinstance(exc, DrunkenError) else None
        self.checks.append(Check(name, "fail", redact(exc), remediation))

    @property
    def failed(self) -> bool:
        return any(check.status == "fail" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        counts = {
            status: sum(1 for c in self.checks if c.status == status)
            for status in ("ok", "warn", "fail", "skip")
        }
        return {
            "ok": not self.failed,
            "summary": counts,
            "checks": [check.to_dict() for check in self.checks],
        }


def package_version() -> str:
    """The installed version. Single-sourced from package metadata."""
    try:
        return version("drunken-guild")
    except PackageNotFoundError:
        return "unknown (not installed as a package)"


def declared_version() -> Optional[str]:
    """What the *source tree* declares, read from ``pyproject.toml``.

    Not ``importlib.metadata``. That reports whatever happens to be installed in
    the environment asking, which during DG-256 meant three different answers on
    one machine: ``pyproject`` said 2.1.0, the tag said 2.3.0, and the test
    environment's installed copy said 1.6.0. A check about the declaration has
    to read the declaration.

    Located relative to ``__file__``, which :mod:`core.paths` bans for state and
    for good reason. It is right here, and the reason is the failure mode:
    installed with ``uv tool install`` this resolves inside the virtualenv,
    finds no ``pyproject.toml``, and returns ``None`` -- which is the honest
    answer, because a deployment genuinely cannot see the source declaration.
    The banned pattern fails safe here rather than silently wrong.
    """
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    try:
        lines = pyproject.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    in_project = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            # [build-system] comes first in this file, and [tool.*] blocks come
            # after. Only [project] carries the version that is ours.
            if in_project:
                break
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _version_tuple(raw: str) -> Optional[tuple[int, ...]]:
    """``"v2.3.0"`` -> ``(2, 3, 0)``, or ``None`` if it is not a version.

    Deliberately not ``packaging.version``: it is present in this environment
    only as a transitive dependency of something else, and reaching for an
    undeclared import is the class of mistake this project keeps writing up.
    Release tags here are ``vX.Y.Z`` and nothing more exotic.
    """
    cleaned = raw.strip().lstrip("vV")
    parts = cleaned.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def version_verdict(
    declared: Optional[str], newest_tag: Optional[str]
) -> tuple[Status, str]:
    """Whether *declared* is behind *newest_tag*, and what to say about it.

    Behind is a failure; equal or ahead is fine. Ahead is the normal shape
    during development -- the declaration is bumped first and the tag catches
    up -- and flagging it would make this check noise, which is how a check
    stops being read.

    Not reachability. ``git describe`` finds no tag at all from ``develop`` in
    this repository, because ``main`` carries the release commits and the two
    branches have diverged by design. The question worth asking is "did we
    release without bumping", and the newest tag anywhere answers it.

    Three states, kept apart: ``ok``, ``fail``, and ``skip`` for "could not
    ask" -- a shallow checkout has no tags, and reporting that as a pass would
    be inventing a fact.
    """
    if declared is None:
        return "skip", "no pyproject.toml here, so there is no declaration to check."
    if newest_tag is None:
        return (
            "skip",
            "no tags in this checkout, so there is nothing to compare against.",
        )

    tag_parts = _version_tuple(newest_tag)
    declared_parts = _version_tuple(declared)
    if tag_parts is None or declared_parts is None:
        return "skip", f"cannot compare {declared!r} against {newest_tag!r}."

    if declared_parts < tag_parts:
        return "fail", (
            f"pyproject declares {declared} while {newest_tag} is tagged. "
            "Every surface reports the older number, so comparing a checkout "
            "against a deployment finds them equal when they are not."
        )
    return "ok", f"{declared}, at or ahead of the newest tag {newest_tag}."


def newest_tag() -> Optional[str]:
    """The highest version tag in this repository, or ``None``.

    Never raises and never reports a missing tag as a problem: a source tarball
    or a shallow CI checkout legitimately has none.

    Routed through :func:`core.exclude.run_git` (DG-451) rather than a second,
    unstripped ``subprocess.run(["git", ...])`` — this asks about the repository
    this source tree was loaded from, and the same leaked ``GIT_*`` environment
    that could redirect :func:`tracked_ai_layer_paths` onto a different
    repository could redirect this to list another one's tags instead.

    Both ways :func:`run_git` can fail to answer at all —
    :class:`NotAGitRepositoryError` and :class:`GitTimedOutError` (DG-454
    review) — are equally "no tag to report" *here*: this is a benign
    version-check diagnostic with nothing to protect, unlike
    :func:`tracked_ai_layer_paths` below, which must tell the two apart.
    """
    try:
        result = run_git(
            ["tag", "--sort=-v:refname"],
            Path(__file__).resolve().parent,
            timeout=30,
        )
    except (NotAGitRepositoryError, GitTimedOutError):
        return None
    if result.returncode != 0:
        return None
    return next(iter(result.stdout.split()), None)


def _check_environment(report: Report) -> None:
    report.add("version.drunken-guild", "ok", package_version())
    status, detail = version_verdict(declared_version(), newest_tag())
    report.add(
        "version.declared",
        status,
        detail,
        remediation=(
            "Bump `version` in pyproject.toml to the released tag, and "
            "reinstall so the deployment reports it too."
            if status == "fail"
            else None
        ),
    )
    try:
        mcp_version = version("mcp")
    except PackageNotFoundError:
        report.add(
            "version.mcp",
            "fail",
            "The 'mcp' package is not installed.",
            remediation="Reinstall: uv tool install --force .",
        )
        return

    major = mcp_version.split(".")[0]
    if major.isdigit() and int(major) >= 2:
        report.add(
            "version.mcp",
            "fail",
            f"mcp {mcp_version} — 2.x removed mcp.server.fastmcp, so every server "
            "crashes at import before the host sees any tools.",
            remediation="Pin below 2: uv tool install --force --with 'mcp<2' .",
        )
    else:
        report.add("version.mcp", "ok", mcp_version)


def _check_paths(report: Report) -> None:
    for name, described in paths.describe().items():
        path = Path(described["path"])
        detail = f"{path}  (from {described['source']})"

        if name == "home":
            status: Status = "ok" if path.is_dir() else "warn"
            note = "" if path.is_dir() else "  [not created yet]"
            report.add(
                "paths.home",
                status,
                detail + note,
                None if path.is_dir() else "Created automatically on first write.",
            )
            if path.is_dir() and paths.is_group_or_world_accessible(path):
                report.add(
                    "paths.home.permissions",
                    "warn",
                    f"{path} is readable by other users on this machine.",
                    remediation=paths.secure_command(path),
                )
            continue

        report.add(f"paths.{name}", "ok", detail)

        if (
            name == "auth_db"
            and path.exists()
            and paths.is_group_or_world_accessible(path)
        ):
            report.add(
                "paths.auth_db.permissions",
                "fail",
                f"{path} holds credentials and is readable by other users.",
                remediation=paths.secure_command(path),
            )


#: Where `uv tool install` puts the environment the host actually launches.
#: Overridable for the same reason as everything in :mod:`core.paths` — a
#: container or another machine puts it elsewhere, and a test must be able to
#: point it at a fixture.
ENV_TOOL_ROOT: Final = "DRUNKEN_TOOL_ENV"
TOOL_PACKAGE: Final = "drunken-guild"

#: uv's own setting for where tool environments live. Read before asking uv,
#: which honours it too, so an explicit answer costs no subprocess.
ENV_UV_TOOL_DIR: Final = "UV_TOOL_DIR"

#: Where the *previous* package name installed to. `uv tool` names the
#: directory after the distribution, so DG-264's rename moved it — and a
#: constant pointing at the old path made this check answer about a deployment
#: that is not the one a host launches. Reported by name rather than followed:
#: an installation under the old name is a real thing to know about, and the
#: honest report is "you are running a pre-rename install", not silence and not
#: a green line about the wrong directory.
#: Names, not paths: they live beside the current one, in whatever directory
#: uv uses on this machine (so, uv/tools/drunken-team on POSIX).
LEGACY_TOOL_PACKAGES: Final = ("drunken-team",)  # uv/tools/drunken-team

#: Modules whose absence from the deployment has actually mattered. Not every
#: module — a list that tries to be exhaustive goes stale silently, and the
#: point is to notice a *merge* that has not been deployed, which these are the
#: evidence of.
DEPLOYED_MODULES: Final = (
    "core.permission_rules",
    "core.usage",
    "core.hook",
    "jira_mcp.jql",
    "jira_mcp.assign",
    "jira_mcp.backlog",
)


def default_uv_tool_dir(platform: Optional[str] = None) -> Path:
    """Where uv puts tool environments when nothing says otherwise.

    The POSIX path was once the only answer, on every platform — so on Windows
    this check looked where nothing is ever installed and said SKIP (DG-373).
    """
    if (platform or sys.platform) == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "uv" / "tools"
    return Path("~/.local/share/uv/tools").expanduser()


def uv_tool_dir() -> Path:
    """uv's tool directory, in uv's own order: the setting, uv, the default.

    Asking uv beats reconstructing its answer, because uv is what decided where
    the install went. A uv that is absent or fails is not an error here — the
    default is still the best guess, and the check that follows says whether
    anything is there.
    """
    if raw := os.environ.get(ENV_UV_TOOL_DIR):
        return Path(os.path.expandvars(raw)).expanduser()
    uv = shutil.which("uv")
    if uv:
        try:
            result = subprocess.run(  # nosec B603 - fixed argv, uv from PATH
                [uv, "tool", "dir"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    return default_uv_tool_dir()


def tool_env_root(tool_dir: Optional[Path] = None) -> Path:
    if raw := os.environ.get(ENV_TOOL_ROOT):
        return Path(os.path.expandvars(raw)).expanduser()
    return (tool_dir if tool_dir is not None else uv_tool_dir()) / TOOL_PACKAGE


def _site_dirs(env_root: Path) -> list[Path]:
    """Every site-packages in a venv: `lib/pythonX.Y/…` on POSIX, `Lib/…` on
    Windows, where there is no version directory between the two."""
    found = set(env_root.glob("lib/*/site-packages"))
    windows = env_root / "Lib" / "site-packages"
    if windows.is_dir():
        found.add(windows)
    return sorted(found)


def compare_deployment(env_root: Path, modules: Sequence[str]) -> dict[str, list[str]]:
    """Which of *modules* are present in the installed environment at *env_root*.

    Resolved by looking for the file rather than by importing: importing another
    environment's modules into this process would be both wrong and unsafe, and
    what is being asked is whether the code was *deployed*, not whether it runs.
    A package directory counts, so a module that grows into a package does not
    read as a false gap.
    """
    site_dirs = _site_dirs(env_root)
    present: list[str] = []
    missing: list[str] = []

    for module in modules:
        relative = Path(*module.split("."))
        found = any(
            (site / relative).with_suffix(".py").is_file() or (site / relative).is_dir()
            for site in site_dirs
        )
        (present if found else missing).append(module)

    return {"present": present, "missing": missing}


#: The trees ``pyproject``'s ``packages`` ships, and where each lives in the
#: checkout. ``scripts`` sits at the root; the rest are under ``src/``.
#:
#: Content is compared over all of these rather than over
#: :data:`DEPLOYED_MODULES`. That list is a curated handful kept deliberately
#: short, chosen as *evidence* that a merge was not deployed — and a file it
#: does not name is exactly how DG-275's fix sat undeployed while this check
#: read green.
PACKAGED_TREES: Final = (
    "core",
    "route",
    "service",
    "jira_mcp",
    "scripts",
)

#: How many stale files to name before summarising. Long enough to act on,
#: short enough that the report stays a report.
_STALE_NAMES_SHOWN: Final = 5


def _source_package_dir(source_root: Path, package: str) -> Optional[Path]:
    """Where *package* lives in the checkout, or ``None`` if it does not."""
    for candidate in (source_root / "src" / package, source_root / package):
        if candidate.is_dir():
            return candidate
    return None


def compare_deployed_content(
    env_root: Path, source_root: Path, packages: Sequence[str]
) -> dict[str, list[str]]:
    """Which deployed files differ from the checkout they were installed from.

    Presence is not currency. :func:`compare_deployment` answers "is this module
    there", which a three-month-old copy passes exactly as well as one installed
    a minute ago. On 2026-08-23 that reported all seven modules present while
    the deployment was 22 files behind, including the bridge DG-275 had just
    stopped from reading a ``.env`` found by climbing.

    Compared as bytes rather than by mtime: ``uv tool install`` copies, so a
    timestamp says when the file was written, not which revision it holds.

    ``stale`` is deployed-but-different, ``absent`` is in the checkout and not
    deployed at all. Files only in the deployment are ignored — a stale build
    artefact left behind is not evidence about what merged.
    """
    site_dirs = _site_dirs(env_root)
    stale: list[str] = []
    absent: list[str] = []

    for package in packages:
        source_dir = _source_package_dir(source_root, package)
        if source_dir is None:
            continue
        for source_file in sorted(source_dir.rglob("*.py")):
            if "__pycache__" in source_file.parts:
                continue
            relative = Path(package) / source_file.relative_to(source_dir)
            deployed = next(
                (site / relative for site in site_dirs if (site / relative).is_file()),
                None,
            )
            if deployed is None:
                absent.append(str(relative))
            elif deployed.read_bytes() != source_file.read_bytes():
                stale.append(str(relative))

    return {"stale": stale, "absent": absent}


def describe_drift(result: dict[str, list[str]]) -> str:
    """One line naming the drifted files, truncated once it stops being useful."""
    names = result["stale"] + result["absent"]
    shown = ", ".join(names[:_STALE_NAMES_SHOWN])
    if len(names) > _STALE_NAMES_SHOWN:
        shown += f", and {len(names) - _STALE_NAMES_SHOWN} more"
    return shown


def deployed_version(env_root: Path, package: str) -> Optional[str]:
    """The version of *package* inside *env_root*, read from its dist-info.

    ``None`` when it cannot be determined, which is deliberately different from
    a version that disagrees — see :func:`compare_pin`.
    """
    for site in _site_dirs(env_root):
        for dist in site.glob(f"{package}-*.dist-info"):
            name = dist.name[: -len(".dist-info")]
            if "-" in name:
                return name.rsplit("-", 1)[1]
    return None


def compare_pin(deployed: Optional[str], locked: Optional[str]) -> tuple[Status, str]:
    """Whether what is deployed matches what the lock pins.

    ``uv tool install`` ignores ``uv.lock``, so these drift without anything
    saying so. Both satisfying ``<2`` is not the same as being the same.
    """
    if deployed is None or locked is None:
        return "skip", "Could not determine one of the two versions."
    if deployed == locked:
        return "ok", f"{deployed}, matching uv.lock"
    return (
        "warn",
        f"the deployment has {deployed} while uv.lock pins {locked}. "
        "`uv tool install` ignores the lock file.",
    )


#: Where the AI layer is installed to. Only skills are compared, and only the
#: ones this repository produces. The Antigravity tree that used to sit beside
#: this one was retired with the rest of its plumbing (DG-349).
AI_LAYER_ROOTS: Final = (("claude.skills", "~/.claude/skills"),)


#: The MCP configs a host application actually reads, beyond the one
#: onboarding manages. Reading only the managed file is what once let a
#: retired server keep launching: the host started a ``board`` server the
#: managed file no longer named, because the entry was in the host's own file.
#:
#: Empty since DG-349 retired the Antigravity plumbing — both entries here were
#: Antigravity's own configs under ``~/.gemini``, and emptying it left the check
#: reading nothing at all: every test here injects its own roots, so it stayed
#: green while unable to fire. DG-341's stale-project notice then could not reach
#: the one file where it matters.
#:
#: ``~/.claude.json`` is that file. Its top-level ``mcpServers`` is **user
#: scope** — every session on this machine, whatever project it is opened in,
#: which is the scope that carried the leak this check now reports. Only that
#: block is read: a project-scoped entry under ``projects.<path>`` reaches one
#: directory and is the operator's deliberate choice for it.
HOST_MCP_CONFIGS: Final[tuple[tuple[str, str], ...]] = (
    ("claude.json", "~/.claude.json"),
)

#: This project's Jira server. Anything else answering the same question is a
#: second surface that can disagree with the first, which is the failure this
#: repository was built to cure — not redundancy.
OUR_JIRA_SERVER: Final = "drunken-jira-mcp"

#: How many server names to list before summarising, matching
#: :data:`_STALE_NAMES_SHOWN`.
_HOST_NAMES_SHOWN: Final = 5


def _unresolvable(server: dict[str, Any]) -> list[str]:
    """The commands and arguments of one server that do not resolve on disk.

    An absolute path is checked directly. A bare command — ``node``, ``npx``,
    ``uv`` — is looked up on PATH, because treating every one of those as
    missing would report a healthy config as broken, and a check that cries
    wolf is a check nobody reads.

    Only absolute arguments are checked. A shell fragment passed to ``-c`` is
    not a path and guessing inside it would invent findings.
    """
    missing: list[str] = []
    command = str(server.get("command") or "")
    if command.startswith("/"):
        if not Path(command).exists():
            missing.append(command)
    elif command and shutil.which(command) is None:
        missing.append(command)

    for arg in server.get("args") or []:
        if isinstance(arg, str) and arg.startswith("/") and not Path(arg).exists():
            missing.append(arg)
    return missing


#: Ours, and the only entries a stale project is worth reporting on. A
#: `--project` on somebody else's server is an ordinary flag, and a check that
#: fired on it would be noise an operator learns to skip.
def _stale_project_servers(servers: dict[str, Any]) -> list[str]:
    """Our own entries that still pass a project to a server that takes none.

    DG-341 moved the project into every tool call, which is what stopped one
    user-scope entry deciding the Jira for every session on the machine. An
    entry still carrying the flag is **not broken** — verified by handshake: it
    is accepted and ignored. That is precisely why it is worth naming. It reads
    like the thing that chooses a project, it no longer is, and the user-scope
    entry carrying it is the one an operator still has to remove by hand.
    """
    stale = []
    for name, config in servers.items():
        if not isinstance(config, dict) or not is_drunken_managed(name):
            continue
        args = config.get("args")
        if isinstance(args, list) and any(
            isinstance(arg, str) and arg == "--project" for arg in args
        ):
            stale.append(name)
    return sorted(stale)


def _rival_jira_servers(servers: dict[str, Any]) -> list[str]:
    """Servers other than ours that look like they serve Jira.

    Matched on the name and on the launch arguments, because the one found in
    the wild declared itself neither way round: it was named ``jira-board`` and
    ran ``npx -y @modelcontextprotocol/server-jira``, a package that answers 404.
    """
    rivals = []
    for name, config in servers.items():
        if name == OUR_JIRA_SERVER or not isinstance(config, dict):
            continue
        haystack = " ".join([name, *(str(a) for a in config.get("args") or [])])
        if "jira" in haystack.lower():
            rivals.append(name)
    return sorted(rivals)


def _check_host_configs(
    report: Report,
    roots: Optional[Sequence[tuple[str, Any]]] = None,
) -> None:
    """Whether the servers a host will launch can actually be launched.

    Presence in a config is not the same as being startable, and nothing finds
    out until the host tries. Five of the six servers in one real config could
    not start — an npm package returning 404, and four extension paths for a
    version that is not installed — and every launch attempted all six.

    An absent config is a **skip**: a machine with no Antigravity legitimately
    has none. Everything else is a **warn**, never a failure: these files are
    outside this repository and the remedy is the operator's edit, exactly like
    `ai_layer`.

    ``archivedMcpServers`` is skipped. That key is the host's own record of what
    it stopped launching, and reporting it would report a decision as a defect.
    """
    roots = roots if roots is not None else HOST_MCP_CONFIGS

    for name, raw in roots:
        check = f"host_mcp.{name}"
        path = Path(raw).expanduser() if isinstance(raw, str) else Path(raw)
        if not path.is_file():
            report.add(check, "skip", f"No host config at {path}.")
            continue

        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            # `.get`, not `[...]`. `~/.claude.json` holds far more than MCP
            # servers, and a host declaring none is ordinary -- reading a missing
            # key as unparseable would report the common case as a fault, which
            # is how a check earns the habit of being ignored.
            servers = (
                document.get("mcpServers") or {} if isinstance(document, dict) else {}
            )
            if not isinstance(servers, dict):
                raise ValueError("mcpServers is not an object")
        except (OSError, ValueError) as exc:
            report.add(
                check,
                "warn",
                f"Could not read {path}: {exc}",
                remediation=(
                    "A host config this tool cannot parse is one the host may "
                    "not be reading either. Open it and check the JSON."
                ),
            )
            continue

        broken = {
            server: paths_missing
            for server, config in servers.items()
            if isinstance(config, dict) and (paths_missing := _unresolvable(config))
        }
        rivals = _rival_jira_servers(servers)
        stale = _stale_project_servers(servers)

        if not servers:
            report.add(check, "skip", f"{path} declares no MCP servers.")
            continue

        if not broken and not rivals and not stale:
            report.add(check, "ok", f"all {len(servers)} server(s) in {path} resolve")
            continue

        parts = []
        if broken:
            named = sorted(broken)[:_HOST_NAMES_SHOWN]
            more = len(broken) - len(named)
            listed = ", ".join(f"{s} -> {broken[s][0]}" for s in named)
            parts.append(
                f"{len(broken)} of {len(servers)} server(s) cannot start: {listed}"
                + (f", and {more} more" if more else "")
            )
        if rivals:
            parts.append(f"{', '.join(rivals)} serve(s) Jira beside {OUR_JIRA_SERVER}")
        if stale:
            parts.append(
                f"{', '.join(stale)} still pass(es) --project, which this "
                "checkout's server ignores — every tool takes the project as an "
                "argument (DG-341)"
            )

        report.add(
            check,
            "warn",
            f"{path}: " + "; ".join(parts),
            remediation=(
                "Editing a host's own config is the operator's step, never this "
                "tool's. A server that cannot start is attempted on every launch "
                "and fails silently; a second Jira server is a surface that can "
                "disagree with this project's. On --project: leave it in place "
                "until the deployment above reports no drift. This checkout "
                "ignores it, but the *installed* server is what a host launches, "
                "and a version predating DG-341 needs it — remove it first and "
                'every tool call answers "started without a project" instead. '
                "Reinstall, confirm, then drop the args."
            ),
        )


def source_tree_root() -> Optional[Path]:
    """The checkout this code was loaded from, or ``None`` once installed.

    Located relative to ``__file__``, which :mod:`core.paths` bans for *state*
    and rightly. This is not state: the question is literally "where is the
    source I came from", and installed under `uv tool` it resolves inside the
    virtualenv, finds no ``skills/`` and returns ``None`` — which is the honest
    answer, because a deployment has no source tree to compare against.
    """
    root = Path(__file__).resolve().parent.parent.parent
    return root if (root / "skills").is_dir() else None


def repo_skills(root: Path) -> dict[str, Path]:
    """Every skill this repository produces, by name."""
    return {
        skill.parent.name: skill.parent
        for skill in sorted((root / "skills").glob("*/*/SKILL.md"))
    }


def extras_skill_names(root: Path) -> set[str]:
    """Skills that moved to ``plugins/drunken-extras/skills/`` (DG-352/353).

    Named separately from :func:`repo_skills` because they are still
    first-party and still shipped — just not from ``skills/`` any more, and
    an install that still carries one is not the same finding as one carrying
    something this project never produced at all (DG-359).
    """
    extras_dir = root / "plugins" / "drunken-extras" / "skills"
    if not extras_dir.is_dir():
        return set()
    return {skill.parent.name for skill in extras_dir.glob("*/SKILL.md")}


def external_skill_names(root: Path) -> set[str]:
    """Names declared third-party in ``skills/.external``.

    Same file ``install_skills.sh`` reads: a name listed there is a deliberate
    statement that this repository did not author it, so it is not reported as
    an unexplained extra either.
    """
    external_file = root / "skills" / ".external"
    if not external_file.is_file():
        return set()
    names = set()
    for line in external_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.add(stripped)
    return names


#: Relative to the repository root. The single list both installers and this
#: module read, so "retired" means one thing everywhere (DG-359 review
#: finding #1).
RETIRED_SKILLS_FILE: Final = "scripts/install/retired_skills.txt"


def retired_skill_names(root: Path) -> set[str]:
    """Names on ``scripts/install/retired_skills.txt`` — the *only* names an
    install script's ``--prune-apply`` may ever remove.

    Comments (``#``) and blank lines are skipped; ``\\r`` is stripped so a
    CRLF checkout parses identically to an LF one. **Never** returns a name
    that :func:`repo_skills` also returns — a retired name must not be able
    to delete something the guild still ships; that invariant is asserted in
    ``tests/test_install_prune.py``, not enforced here, because this function
    answers "what does the list say", not "is the list sane".
    """
    list_file = root / RETIRED_SKILLS_FILE
    if not list_file.is_file():
        return set()
    names = set()
    for raw_line in list_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip("\r").strip()
        if stripped and not stripped.startswith("#"):
            names.add(stripped)
    return names


def compare_ai_layer(root: Path, install_root: Path) -> dict[str, list[str]]:
    """Which of the repository's skills are absent, different, or extra at
    *install_root*.

    Compared by reading ``SKILL.md`` rather than by mtime or by counting
    directories. A count matched while `git-workflow` was installed at 120 lines
    against 196 in the source, and both surfaces reported themselves healthy.

    ``extra`` names a directory installed with a ``SKILL.md`` that this
    repository's ``skills/`` does not produce. It is **not** drift — content
    that is present and correct is not "different" — and it is not ownership:
    a third-party pack such as Gemini CLI's own ``~/.gemini/.../skills`` is
    never passed as *install_root* here, but if it ever were, a name this
    repository has no stake in is still worth a caller naming rather than
    silently absorbing into "fine" (DG-359). Classifying an extra as retired
    versus merely moved elsewhere is the caller's job — see
    :func:`extras_skill_names` and :func:`external_skill_names` — because that
    answer depends on the repository, not on the comparison itself.
    """
    missing: list[str] = []
    drifted: list[str] = []

    ours = repo_skills(root)
    for name, source in ours.items():
        installed = install_root / name / "SKILL.md"
        if not installed.is_file():
            missing.append(name)
            continue
        try:
            if installed.read_bytes() != (source / "SKILL.md").read_bytes():
                drifted.append(name)
        except OSError:
            drifted.append(name)

    extra: list[str] = []
    if install_root.is_dir():
        for entry in sorted(install_root.iterdir()):
            if (
                entry.is_dir()
                and entry.name not in ours
                and (entry / "SKILL.md").is_file()
            ):
                extra.append(entry.name)

    return {"missing": missing, "drifted": drifted, "extra": extra}


def _check_ai_layer(report: Report, root: Optional[Path] = None) -> None:
    """Whether what is installed is what this repository says.

    Nothing checked this before, and the gap was not theoretical. The
    session-checkpoint stated that ``~/.claude/`` follows this repository; when
    somebody finally looked, `git-workflow` was installed at 120 lines against
    196, `project-hygiene` at 68 against 88, three skills were not installed at
    all, and Antigravity's copy was two months old with 21 of 28 shared skills
    drifted. Two agents were reading two different halves of the git rules and
    neither matched the source.

    An absent install root is a **skip**: a container, CI or a fresh clone
    legitimately has none, and a check that cries wolf there is one everybody
    learns to ignore. Drift is a **warn** rather than a failure because the
    remedy is an install, which is the operator's to run, not this tool's.

    ``ok`` used to mean only "ours are present and correct" — the question this
    answered was always "are ours all there", never "is anything else there
    too". `install_skills.sh` was run after the 2.0.0 re-scope and left 34
    retired skill directories installed beside the 11 this repository ships;
    this check reported "all 11 skills match the source" in the same run,
    because nothing it compared ever looked past the 11 it already knew about
    (DG-359). An extra directory now ends the ``ok``, named apart from drift
    and from a merely-moved skill — see :func:`compare_ai_layer`,
    :func:`extras_skill_names` and :func:`external_skill_names`.
    """
    root = root if root is not None else source_tree_root()
    if root is None:
        report.add(
            "ai_layer.source",
            "skip",
            "Running from an installed package, so there is no source tree to "
            "compare the installed skills against.",
        )
        return

    total = len(repo_skills(root))
    moved = extras_skill_names(root)
    external = external_skill_names(root)
    # A name on the retired list that has since reappeared under `skills/` or
    # `plugins/drunken-extras/skills/` is shipped again, by whichever surface
    # claims it — `moved`/`ours` always wins over "retired", so this check
    # never calls something the guild currently ships prunable.
    retired = retired_skill_names(root) - moved - set(repo_skills(root))
    for name, raw in AI_LAYER_ROOTS:
        install_root = Path(raw).expanduser()
        if not install_root.is_dir():
            report.add(f"ai_layer.{name}", "skip", f"Nothing installed at {raw}.")
            continue

        result = compare_ai_layer(root, install_root)
        missing, drifted = result["missing"], result["drifted"]
        extra = [e for e in result["extra"] if e not in external]
        extra_moved = sorted(e for e in extra if e in moved)
        extra_retired = sorted(e for e in extra if e not in moved and e in retired)
        extra_unrecognised = sorted(
            e for e in extra if e not in moved and e not in retired
        )

        if not missing and not drifted and not extra:
            report.add(
                f"ai_layer.{name}",
                "ok",
                f"all {total} skills match the source",
            )
            continue

        parts = []
        if drifted:
            parts.append(
                f"{len(drifted)} differ ({', '.join(sorted(drifted)[:4])}"
                + (", …" if len(drifted) > 4 else "")
                + ")"
            )
        if missing:
            parts.append(
                f"{len(missing)} not installed ({', '.join(sorted(missing)[:4])}"
                + (", …" if len(missing) > 4 else "")
                + ")"
            )
        if extra_moved:
            parts.append(
                f"{len(extra_moved)} moved to plugins/drunken-extras "
                f"({', '.join(extra_moved[:4])}"
                + (", …" if len(extra_moved) > 4 else "")
                + ")"
            )
        if extra_retired:
            parts.append(
                f"{len(extra_retired)} retired, will be pruned "
                f"({', '.join(extra_retired[:4])}"
                + (", …" if len(extra_retired) > 4 else "")
                + ")"
            )
        if extra_unrecognised:
            parts.append(
                f"{len(extra_unrecognised)} unrecognised, never pruned "
                f"({', '.join(extra_unrecognised[:4])}"
                + (", …" if len(extra_unrecognised) > 4 else "")
                + ")"
            )
        report.add(
            f"ai_layer.{name}",
            "warn",
            "; ".join(parts)
            + ". Run scripts/install/install_skills.sh — an install is the "
            "operator's to run, and pruning is opt-in and list-only by "
            "default (--prune to list, --prune --prune-apply to remove only "
            "the retired ones). An unrecognised name is never pruned "
            "automatically — add it to skills/.external if it is yours, or "
            "to scripts/install/retired_skills.txt if it is retired.",
        )


#: A code span (`/build`, `jira_*`, `skills/INDEX.md`) or a bold role name
#: (**worker**) inside the guild block's pointer table.
_ROUTE_CODE_SPAN: Final = re.compile(r"`([^`]+)`")
_ROUTE_BOLD_ROLE: Final = re.compile(r"\*\*(manager|worker|reviewer)\*\*")

#: `@mcp.tool()`, any number of other decorators, then the `def` it names.
#: Read as source rather than imported -- importing the server module runs its
#: own setup, and the only question here is what name follows the decorator.
_MCP_TOOL_DEF: Final = re.compile(
    r"@mcp\.tool\(\)[^\n]*\n(?:@[^\n]*\n)*(?:async\s+)?def\s+(\w+)"
)

#: The three roles a route can name. Each resolves to `agents/<role>.md`.
ROUTE_ROLES: Final = ("manager", "worker", "reviewer")


def guild_block(agents_md_text: str) -> str:
    """The pointer table between the guild-block markers, or ``""``.

    An absent marker is not an error here — :func:`_check_routes` is the one
    that decides whether a missing block is worth reporting, and reports it as
    a skip rather than inventing a table that is not there.
    """
    if "<!-- guild-block:start -->" not in agents_md_text:
        return ""
    try:
        return agents_md_text.split("<!-- guild-block:start -->", 1)[1].split(
            "<!-- guild-block:end -->", 1
        )[0]
    except IndexError:
        return ""


def route_targets(block: str) -> list[str]:
    """Every pointer named in the guild block: code spans and bold role names.

    A wildcard such as ``jira_*`` is kept exactly as written — resolving it
    against the registered tool names is :func:`unresolved_routes`'s job, not
    this one's.
    """
    return _ROUTE_CODE_SPAN.findall(block) + _ROUTE_BOLD_ROLE.findall(block)


def _skill_dirs(skills_root: Path) -> dict[str, Path]:
    """Every skill under *skills_root*, by its folder name."""
    if not skills_root.is_dir():
        return {}
    return {
        skill.parent.name: skill.parent
        for skill in sorted(skills_root.glob("*/*/SKILL.md"))
    }


def _route_target_resolves(
    target: str,
    skills: dict[str, Path],
    agents_root: Path,
    tools: set[str],
) -> bool:
    """Whether one route target names something that actually exists.

    A path ending ``.md`` is handled by the caller before this is reached —
    it is checked against the repository root, which this function is not
    given.
    """
    if target.endswith("*"):
        prefix = target[:-1]
        return any(tool.startswith(prefix) for tool in tools)
    if target.startswith("/"):
        return target[1:] in skills
    if target in ROUTE_ROLES:
        return (agents_root / f"{target}.md").is_file()
    return target in tools


def _resolves_under_repo(repo_root: Path, target: str) -> bool:
    """Whether a ``.md`` route target is both an existing file and still
    inside the repository, once ``..`` is resolved away.

    A target like ``../../etc/passwd`` reads as a file on disk the same way
    a real one does; this check's job is to say the route named something
    real, not to resolve a path that walks outside the tree it names.
    """
    try:
        resolved_root = repo_root.resolve()
        candidate = (repo_root / target).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        return False
    return candidate.is_file()


def unresolved_routes(
    targets: Sequence[str],
    skills_root: Path,
    agents_root: Path,
    mcp_tools: Sequence[str],
) -> list[str]:
    """Which of *targets* name a skill, role or MCP tool that does not exist.

    A slash command (``/build``) resolves to a skill folder of that name,
    wherever under ``skills/`` it sits. A bare role name resolves to
    ``agents/<role>.md``. A path ending ``.md`` is checked directly, relative
    to the repository root ``skills_root``'s parent holds, and must resolve
    to a file inside that root — a ``..`` that walks outside it is reported
    as missing rather than followed. ``jira_*`` is a wildcard over the
    registered tool names, matched by prefix — the wildcard itself is never
    "missing", only unmatched by anything registered.
    """
    skills = _skill_dirs(skills_root)
    tools = set(mcp_tools)
    repo_root = skills_root.parent

    missing: list[str] = []
    for target in targets:
        if target.endswith(".md"):
            if not _resolves_under_repo(repo_root, target):
                missing.append(target)
            continue
        if not _route_target_resolves(target, skills, agents_root, tools):
            missing.append(target)
    return missing


def registered_mcp_tools(server_path: Path) -> list[str]:
    """The tool names ``src/jira_mcp/server.py`` registers, read as text."""
    try:
        text = server_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return _MCP_TOOL_DEF.findall(text)


def skill_description(skill_md: Path) -> str:
    """The frontmatter ``description:`` field of a ``SKILL.md``, or ``""``.

    Handles both a plain value on the same line and a YAML block scalar
    (``>`` or ``|``) indented on the lines that follow, which is how every
    skill in this repository writes it.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""

    collecting = False
    collected: list[str] = []
    for line in parts[1].splitlines():
        if collecting:
            if line.strip() and (line.startswith(" ") or line.startswith("\t")):
                collected.append(line.strip())
                continue
            break
        if line.strip().startswith("description:"):
            value = line.split(":", 1)[1].strip()
            if value in (">", "|", ""):
                collecting = True
                continue
            return value
    return " ".join(collected)


#: A name, optionally slash-prefixed, as a whole word — not a substring of a
#: longer hyphenated one. ``\b`` alone is not enough: ``\bbuild\b`` still
#: matches inside ``build-step`` (a word/non-word boundary sits at the
#: hyphen), so the boundary here treats a hyphen as part of the word too,
#: the same way a skill's own folder name uses it.
def _mentions(text: str, name: str) -> bool:
    pattern = re.compile(rf"(?<![\w-])/?{re.escape(name)}(?![\w-])")
    return bool(pattern.search(text))


def unreachable_skills(
    skills_root: Path, agents_root: Path, guild_block_text: str
) -> list[str]:
    """Skills named by nothing: not the guild block, not an agent file, and
    not another skill's own text (a "next step" line included).

    A skill's own description is deliberately not asked here (REQ-013, as
    the Boss approved it): being a good match for an agent picking by
    description is a separate fact from being *routed* to, and the literal
    requirement is that every skill is reached one of those ways — not that
    it merely has a description that reads well. Matched whole-word, slash
    form included, so a skill named ``build`` is not satisfied by another
    skill's prose saying ``rebuild``. A skill's own file is excluded from the
    texts checked against it, so a skill cannot make itself reachable by
    naming itself.
    """
    skills = _skill_dirs(skills_root)
    texts = {
        name: (path / "SKILL.md").read_text(encoding="utf-8")
        for name, path in skills.items()
    }
    agent_texts = (
        [p.read_text(encoding="utf-8") for p in sorted(agents_root.glob("*.md"))]
        if agents_root.is_dir()
        else []
    )

    unreachable: list[str] = []
    for name in sorted(skills):
        others = (
            guild_block_text
            + "\n"
            + "\n".join(agent_texts)
            + "\n"
            + "\n".join(text for other, text in texts.items() if other != name)
        )
        if _mentions(others, name):
            continue
        unreachable.append(name)
    return unreachable


def _check_routes(report: Report, repo_root: Optional[Path] = None) -> None:
    """REQ-013: fail when a route's target is missing, or a skill is reached
    by nothing at all.

    The routes are the guild block's pointer table in ``AGENTS.md`` (REQ-011)
    and each flow skill's own "next step" hand-off (REQ-012) — not a second,
    separate check of whether every pointer anywhere in the repository's
    prose resolves to a file. That is DG-393's job, scoped deliberately
    narrower, and run later. A skill's own description (REQ-010) is not
    asked here: it is how an agent *picks* a skill, a different fact from
    whether anything *routes* to it, and the literal requirement is reached
    by one of the guild block, an agent file, or another skill's text.

    An absent source tree, or an ``AGENTS.md`` with no guild block, is a
    **skip**: an installed package has neither, and a check that cries wolf
    there is one nobody reads.
    """
    repo_root = repo_root if repo_root is not None else source_tree_root()
    if repo_root is None:
        report.add(
            "routes.guild_block",
            "skip",
            "Running from an installed package, so there is no AGENTS.md or "
            "skills/ tree to check routes against.",
        )
        return

    agents_md = repo_root / "AGENTS.md"
    if not agents_md.is_file():
        report.add("routes.guild_block", "skip", f"No AGENTS.md at {agents_md}.")
        return

    text = agents_md.read_text(encoding="utf-8")
    block = guild_block(text)
    if not block:
        report.add(
            "routes.guild_block",
            "skip",
            f"{agents_md} carries no guild block.",
        )
        return

    skills_root = repo_root / "skills"
    agents_root = repo_root / "agents"
    server_path = repo_root / "src" / "jira_mcp" / "server.py"

    targets = route_targets(block)
    tools = registered_mcp_tools(server_path)
    missing = sorted(set(unresolved_routes(targets, skills_root, agents_root, tools)))
    if missing:
        report.add(
            "routes.targets",
            "fail",
            f"{len(missing)} route target(s) in {agents_md.name} name a skill, "
            "role or tool that does not exist: " + ", ".join(missing),
            remediation="Fix the route, or add the skill, role or tool it names.",
        )
    else:
        report.add(
            "routes.targets",
            "ok",
            f"all {len(set(targets))} route target(s) in {agents_md.name} resolve",
        )

    unreachable = unreachable_skills(skills_root, agents_root, block)
    if unreachable:
        report.add(
            "routes.reachable",
            "fail",
            f"{len(unreachable)} skill(s) are named by no route in "
            f"{agents_md.name}, no agent file and no other skill: "
            + ", ".join(unreachable),
            remediation=(
                "Name the skill in a guild-block route, in an agent file, or "
                "in another skill's own text."
            ),
        )
    else:
        report.add(
            "routes.reachable",
            "ok",
            "every skill is reached by a route, an agent file or another skill",
        )


def _check_deployment(
    report: Report,
    env_root: Optional[Path] = None,
    modules: Optional[Sequence[str]] = None,
    legacy_roots: Optional[Sequence[str]] = None,
    source_root: Optional[Path] = None,
) -> None:
    """Report the gap between this checkout and the environment the host runs.

    This is the check §10.7 was reaching for. Merging a fix does not deploy it:
    ``~/.local/bin/drunken-*`` symlinks into the ``uv tool`` environment, and
    that is what a host config launches — not this checkout. The gap has been
    found twice by hand and never by a check.

    A missing environment is a **skip**, not a failure: a container, CI or a
    fresh clone legitimately has none, and a check that cries wolf there is a
    check everyone learns to ignore.

    *source_root* is the checkout to compare deployed content against, and
    ``None`` means there is none to compare with — which is the ordinary case
    when the installed ``drunken-doctor`` runs itself. Unlike the other three
    parameters, ``None`` here is an answer rather than "use the default", so
    :func:`run_doctor` resolves it rather than this function: a check that
    quietly located its own source tree would report on a checkout the caller
    never named.

    Drift is a **warn**, matching `ai_layer.source` and the missing-module case
    directly above. The failure this fixes was a green line, not an ignored
    yellow one, and the remedy is an install — the operator's to run, never
    this tool's.
    """
    # `legacy_roots` is injectable for the same reason as `env_root`: otherwise
    # this check reads the developer's own machine, and a test asserting "no
    # install is a skip" passes or fails depending on whose laptop runs it.
    if env_root is None or legacy_roots is None:
        # Asked once: it can be a subprocess, and both roots live in its answer.
        tool_dir = uv_tool_dir()
        env_root = env_root if env_root is not None else tool_env_root(tool_dir)
        if legacy_roots is None:
            legacy_roots = tuple(str(tool_dir / name) for name in LEGACY_TOOL_PACKAGES)
    modules = modules if modules is not None else DEPLOYED_MODULES

    if not env_root.is_dir():
        stale = [
            path
            for path in (Path(raw).expanduser() for raw in legacy_roots)
            if path.is_dir()
        ]
        if stale:
            report.add(
                "deployment.tool_env",
                "warn",
                f"Nothing installed at {env_root}, but {stale[0]} exists. That "
                "is an install under the previous package name, so every "
                "`drunken-*` command on PATH predates the rename. Reinstall "
                "with `uv tool install .`.",
            )
            return
        report.add(
            "deployment.tool_env",
            "skip",
            f"No installed tool environment at {env_root}.",
            remediation=(
                "Normal in a container or a fresh clone. On a workstation that "
                "runs the MCP servers, install with: uv tool install --force ."
            ),
        )
        return

    result = compare_deployment(env_root, modules)
    if result["missing"]:
        report.add(
            "deployment.tool_env",
            "warn",
            f"{env_root} is behind this checkout — missing: "
            + ", ".join(result["missing"]),
            remediation=(
                "Redeploy it: uv tool install --force . — merging a fix does "
                "not deploy it to the environment the host actually launches."
            ),
        )
    elif (
        source_root is not None
        and (drift := compare_deployed_content(env_root, source_root, PACKAGED_TREES))
        and (drift["stale"] or drift["absent"])
    ):
        count = len(drift["stale"]) + len(drift["absent"])
        report.add(
            "deployment.tool_env",
            "warn",
            f"{env_root} carries all {len(result['present'])} checked modules, "
            f"but {count} file(s) differ from {source_root}: " + describe_drift(drift),
            remediation=(
                "Reinstall so the deployment matches the checkout: "
                "uv tool install . --reinstall — every module being present "
                "says nothing about which revision of it is there."
            ),
        )
    else:
        detail = f"{env_root} carries all {len(result['present'])} checked modules"
        if source_root is None:
            detail += ", and there is no checkout here to compare their content against"
        else:
            detail += f", matching {source_root}"
        report.add("deployment.tool_env", "ok", detail)

    status, detail = compare_pin(deployed_version(env_root, "mcp"), _locked_version())
    report.add("deployment.mcp_pin", status, detail)


def _locked_version(package: str = "mcp") -> Optional[str]:
    """The version ``uv.lock`` pins, read as text.

    Deliberately not parsed as TOML: the lock is not ours, its shape is free to
    change, and a doctor check must never be the thing that raises. A shape it
    does not recognise reads as "unknown", which :func:`compare_pin` reports as
    a skip.
    """
    lock = Path.cwd() / "uv.lock"
    try:
        lines = lock.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for index, line in enumerate(lines):
        if line.strip() == f'name = "{package}"':
            for following in lines[index + 1 : index + 3]:
                stripped = following.strip()
                if stripped.startswith("version = "):
                    return stripped.split('"')[1] if '"' in stripped else None
            return None
    return None


def describe_missing_git_root(git_root: Path) -> str:
    """Say what was actually found where a repository was expected.

    The old message was ``{path} is not a git repository``. That was literally
    true of BETA on 2026-08-16 and cost hours, because the two facts the reader
    needed — that the path did not exist, and that a repository sat one
    directory deeper — were both knowable at the moment it was written and
    neither was said.

    One level down only. A `doctor` that walks a filesystem is a `doctor`
    nobody runs, and a repository three levels away is not the one that was
    meant anyway.
    """
    if not git_root.exists():
        return f"{git_root} does not exist."

    if not git_root.is_dir():
        return f"{git_root} is a file, not a directory."

    try:
        nested = sorted(
            child.name
            for child in git_root.iterdir()
            if child.is_dir() and (child / ".git").exists()
        )
    except OSError:
        nested = []

    if nested:
        return (
            f"{git_root} is not a git repository, but {', '.join(nested)} "
            f"inside it {'is' if len(nested) == 1 else 'are'}."
        )
    return f"{git_root} is not a git repository, and nothing directly inside it is."


def _check_registry(report: Report, registry: ProjectRegistry) -> list[str]:
    registry_file = Path(registry.registry_path)
    if not registry_file.exists():
        report.add(
            "registry.file",
            "fail",
            f"No registry at {registry_file}.",
            remediation=(
                "Create it with: drunken-init --project <id> --path <absolute-path>. "
                "Point DRUNKEN_REGISTRY_PATH at an existing one to use that instead."
            ),
        )
        return []

    project_ids = registry.project_ids()
    schema = registry.schema_version()

    if not project_ids:
        report.add(
            "registry.file",
            "fail",
            f"{registry_file} exists but contains no projects — it may be malformed.",
            remediation="Check that it is valid JSON with an object per project.",
        )
        return []

    report.add(
        "registry.file",
        "ok",
        f"{registry_file}  (schema v{schema}, {len(project_ids)} projects)",
    )
    if schema < 2:
        report.add(
            "registry.schema",
            "warn",
            "Schema v1: projects carry a path only, so Jira and Discord identity "
            "still come from scattered .env files.",
            remediation="Upgrade to v2 to hold identity centrally. v1 keeps working.",
        )
    return project_ids


def _check_secret(report: Report, project_id: str, context: ProjectContext) -> None:
    """Confirm the credential resolved, and name the reference it came from.

    Naming the reference is the point: "it says env://JIRA_TOKEN_ALPHA" is what
    turns a mystery into a one-line fix. The value itself never appears.
    """
    if context.jira is None or context.config.jira is None:
        return
    report.add(
        f"project.{project_id}.credential",
        "ok",
        f"resolved from {context.config.jira.credential}",
    )


def _check_jira_live(report: Report, project_id: str, context: ProjectContext) -> None:
    """Confirm the credential works *and* that the project key exists.

    Two facts, two calls. DG-260: this printed `OK ... (project ALPHA)` off the
    identity call alone, while Jira answered "No project could be found with
    key 'ALPHA'". The key was echoed straight back from the registry, so the line
    proved only that the registry could be read.
    """
    name = f"project.{project_id}.jira"
    try:
        jira = context.require_jira()
        identity = context.verify_jira_identity()
        project = context.verify_jira_project()
    except DrunkenError as exc:
        report.add_error(name, exc)
        return
    named = f"{project.key} — {project.name}" if project.name else project.key
    report.add(
        name,
        "ok",
        f"{jira.url} as {identity.display_name or identity.email} (project {named})",
    )


def _check_project_paths(
    report: Report, project_id: str, context: ProjectContext
) -> None:
    if context.config.path is None:
        report.add(
            f"project.{project_id}.path",
            "skip",
            "No path declared — fine for a Jira/Discord-only or containerised project.",
        )
        return

    # DG-445: expanduser lives in one place, ProjectConfig.resolved_path —
    # wrapping the raw registry string in Path() here used to leave a
    # registered "~/checkout" as a literal directory named "~" that never
    # exists, so this reported "does not exist" for a project that was
    # actually there under the real home.
    root = context.root_path()
    if not root.is_dir():
        report.add(
            f"project.{project_id}.path",
            "fail",
            f"{root} does not exist.",
            remediation=f"Fix it with: drunken-init --project {project_id} --path <path>",
        )
        return

    report.add(f"project.{project_id}.path", "ok", str(root))

    git_root = context.git_root_path()
    if (git_root / ".git").exists():
        report.add(f"project.{project_id}.git", "ok", str(git_root))
    else:
        report.add(
            f"project.{project_id}.git",
            "warn",
            describe_missing_git_root(git_root),
            remediation=(
                f"If the repo lives in a subdirectory, point at it: "
                f"drunken-init --project {project_id} --git-root <subdirectory>. "
                "Under the three-part layout the wrapper is deliberately not a "
                "repository, so this warning can also be the right answer to "
                "the wrong question."
            ),
        )


def _check_project(
    report: Report,
    project_id: str,
    registry: ProjectRegistry,
    offline: bool,
) -> None:
    try:
        context = ProjectContext.build(project_id, registry)
    except DrunkenError as exc:
        report.add_error(f"project.{project_id}", exc)
        return

    _check_project_paths(report, project_id, context)
    _check_secret(report, project_id, context)

    if context.jira is None:
        report.add(f"project.{project_id}.jira", "skip", "No Jira configured.")
    elif offline:
        report.add(
            f"project.{project_id}.jira",
            "skip",
            "Offline mode — credential resolved but not verified against Jira.",
        )
    else:
        _check_jira_live(report, project_id, context)

    _check_notifications(report, project_id, context)


def _check_notifications(
    report: Report, project_id: str, context: ProjectContext
) -> None:
    """Whether one-way Discord notifications are configured, and reachable.

    Three states rather than two. A project with no webhook is *not*
    misconfigured — notifications are optional — but a registry still carrying
    the retired ``channel_id`` is a third thing: it looks configured to whoever
    wrote it, and nothing will ever be sent. Saying so is the only way that
    ever gets noticed, because nobody is blocked when a notification is missing.
    """
    identity = context.discord
    if identity is not None and identity.webhook:
        report.add(
            f"project.{project_id}.notify",
            "ok",
            f"webhook from {identity.webhook}",
        )
        return

    if identity is not None and identity.legacy_channel_id:
        report.add(
            f"project.{project_id}.notify",
            "warn",
            f"discord.channel_id {identity.legacy_channel_id} is set, but a "
            "channel is no longer how anything is sent, so nothing will be.",
            remediation=(
                f"Replace it with a 'discord.webhook' reference for {project_id} "
                "(for example 'env://DISCORD_WEBHOOK_URL'), or drop the block."
            ),
        )
        return

    report.add(
        f"project.{project_id}.notify",
        "skip",
        "No Discord webhook configured. Notifications are optional.",
    )


def _same_checkout(a: Path, b: Path) -> bool:
    """Whether *a* and *b* name the same directory on disk.

    ``resolve()`` rather than string equality: a registered path may carry a
    trailing slash, a different case on a case-insensitive filesystem, or a
    symlink hop, and none of those make it a different checkout.
    """
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def tracked_ai_layer_paths(git_root: Path) -> Optional[list[str]]:
    """Every path git tracks under *git_root* that :mod:`core.ai_layer` names.

    Read-only — ``git ls-files`` lists the index; nothing here ever writes to
    the checkout it is pointed at. ``None`` means git could not be run at all
    (no binary, no repository, a timeout), which a caller must tell apart from
    "ran, and tracks nothing": the first is a question that was not answered,
    the second is a clean project.

    Run with ``-z``, and read as bytes rather than ``text=True``. Without it,
    ``git`` applies ``core.quotepath`` and C-quotes any path holding a
    non-ASCII byte or a special character — a tracked
    ``packages/\xe9/CLAUDE.md`` comes back as the *literal* quoted text, which
    never equals the real path and so never matches
    :func:`core.ai_layer.is_ai_layer_path`: a silent false negative on exactly
    the files this check exists to catch. ``-z`` NUL-separates instead of
    quoting, so splitting on ``b"\0"`` and decoding (``surrogateescape``, so a
    byte sequence that is not valid UTF-8 becomes an odd ``str`` instead of
    raising) recovers the real path whole.

    Routed through :func:`core.exclude.run_git` (DG-451) rather than a second,
    unstripped ``subprocess.run(["git", ...])``: this was found running with
    the caller's full inherited environment, so a process with ``GIT_DIR`` /
    ``GIT_WORK_TREE`` / ``GIT_INDEX_FILE`` set — a git hook, among others —
    could make it answer about a different repository's (or a different
    index's) tracked files than *git_root*'s own. It is read-only, so this
    misreports rather than damages, but this is exactly the check a person
    trusts (REQ-019). ``text=False`` keeps the bytes/``-z`` handling above
    unchanged — ``run_git``'s default ``text=True`` would hand back a ``str``
    already decoded (and newline-translated) by the subprocess layer itself,
    which is the same class of silent corruption ``-z`` exists to avoid.
    """
    try:
        result = run_git(["ls-files", "-z"], git_root, text=False, timeout=30)
    except (NotAGitRepositoryError, GitTimedOutError):
        # Both ways run_git can fail to answer at all (DG-454 review) land
        # here as the same None: the docstring above already promises a
        # timeout is one of the reasons, and the caller
        # (_check_project_layering) already reads None as "skip", never
        # as "ran, and tracks nothing" — the two must stay tellable apart.
        return None
    if result.returncode != 0:
        return None
    tracked = (
        raw.decode("utf-8", errors="surrogateescape")
        for raw in result.stdout.split(b"\0")
        if raw
    )
    return sorted(path for path in tracked if ai_layer.is_ai_layer_path(path))


def _check_project_layering(
    report: Report,
    project_id: str,
    registry: ProjectRegistry,
    repo_root: Optional[Path],
) -> None:
    """Whether *project_id*'s own git tracks any path its AI layer owns.

    REQ-019: a project's AI layer stays out of its own repository. This never
    writes to the project — it only lists what git already tracks and reads
    the result, the same way :func:`_check_project_paths` only looks.

    A missing checkout or one with no ``.git`` is a **skip**, never a pass:
    the question "does it track AI-layer paths" was not answered, which is a
    different fact from "it answered no". This repository's own checkout is
    a skip too, exempt by rule — it is where the AI layer is *authored*, the
    opposite situation from a project it must stay out of.
    """
    name = f"layering.tracked.{project_id}"
    try:
        config = registry.get_project_config(project_id)
    except DrunkenError as exc:
        report.add_error(name, exc)
        return

    if not config.path:
        report.add(
            name,
            "skip",
            "No path declared, so there is no checkout to inspect.",
        )
        return

    # DG-445: same expanduser as _check_project_paths and
    # ProjectContext.root_path() — all three go through
    # ProjectConfig.resolved_path() now, so a registered "~/checkout" is
    # inspected rather than silently skipped as a checkout that "does not
    # exist" under its literal "~" name.
    root = config.resolved_path("this operation")
    git_root = root / config.git_root if config.git_root else root

    if repo_root is not None and _same_checkout(git_root, repo_root):
        report.add(
            name,
            "skip",
            f"{git_root} is this repository's own checkout, exempt by rule.",
        )
        return

    if not git_root.is_dir() or not (git_root / ".git").exists():
        report.add(name, "skip", describe_missing_git_root(git_root))
        return

    tracked = tracked_ai_layer_paths(git_root)
    if tracked is None:
        report.add(name, "skip", f"`git ls-files` could not run in {git_root}.")
        return

    if tracked:
        report.add(
            name,
            "fail",
            f"{len(tracked)} AI-layer path(s) tracked in git: " + ", ".join(tracked),
            remediation=(
                "Untrack them (`git rm --cached <path>` for each) and exclude "
                "them going forward — a project's AI layer stays out of its "
                "own repository (REQ-019)."
            ),
        )
        return

    report.add(name, "ok", "no AI-layer paths tracked")


def _check_project_content_scan(
    report: Report,
    project_id: str,
    registry: ProjectRegistry,
    repo_root: Optional[Path],
) -> None:
    """DG-443: whether any of *project_id*'s already-copied, on-disk
    AI-layer files hold a credential-, identity- or path-shaped value.

    Read-only, and a second, independent line of defence behind
    ``drunken-init``'s own pre-write refusal (:mod:`core.layer_copy`,
    :mod:`core.content_scan`) — this catches a file hand-edited after the
    copy, or one copied in by a build that predates this check entirely.
    Walks the checkout with :func:`core.layer_copy.ai_layer_files_under`,
    the same symlink-refusing walk ``drunken-init`` itself uses, so a
    symlinked ``.claude`` pointed outside the project is never read here
    either — one definition of "walk a project's AI layer", not two.

    A missing checkout, same as :func:`_check_project_layering`, is a
    **skip**, never a pass — the question was not asked, which is not the
    same fact as "asked, found clean". This repository's own checkout is
    exempt for the same reason that check exempts it: here the AI layer is
    authored, not received from a config repo under this rule.
    """
    name = f"content_scan.{project_id}"
    try:
        config = registry.get_project_config(project_id)
    except DrunkenError as exc:
        report.add_error(name, exc)
        return

    if not config.path:
        report.add(
            name,
            "skip",
            "No path declared, so there is no checkout to inspect.",
        )
        return

    root = config.resolved_path("this operation")
    git_root = root / config.git_root if config.git_root else root

    if repo_root is not None and _same_checkout(git_root, repo_root):
        report.add(
            name,
            "skip",
            f"{git_root} is this repository's own checkout, exempt by rule.",
        )
        return

    if not git_root.is_dir():
        report.add(name, "skip", describe_missing_git_root(git_root))
        return

    findings = []
    for relative in ai_layer_files_under(git_root):
        findings.extend(
            content_scan.scan_file(git_root / relative, relative.as_posix())
        )

    if findings:
        detail = "; ".join(finding.describe() for finding in findings)
        report.add(
            name,
            "fail",
            f"{len(findings)} finding(s) in the project's own AI-layer "
            f"content: {detail}",
            remediation=(
                "Replace the value with a reference (env://, file://, "
                "op://, keyring://), or remove it from the project and the "
                "config repo it was copied from."
            ),
        )
        return

    report.add(name, "ok", "no credential-, identity- or path-shaped content found")


def _check_content_scan(
    report: Report,
    project_ids: Sequence[str],
    registry: ProjectRegistry,
    repo_root: Optional[Path],
) -> None:
    """For each registered project, DG-443's read-only content scan."""
    for project_id in project_ids:
        _check_project_content_scan(report, project_id, registry, repo_root)


def _check_layering(
    report: Report,
    project_ids: Sequence[str],
    registry: ProjectRegistry,
    repo_root: Optional[Path],
) -> None:
    """For each registered project, whether its own git tracks its AI layer.

    A different concept from :data:`AI_LAYER_ROOTS` / :func:`compare_ai_layer`
    above, which compare *this repository's* skill install on the host
    against ``~/.claude`` — drift in an install, not a project's own
    repository tracking files it should not. Keep the two apart; see
    :mod:`core.ai_layer`'s own docstring on the same point.

    Absent git entirely is one **skip** for the whole check, not one per
    project: the question could not be asked of any of them.
    """
    if shutil.which("git") is None:
        report.add(
            "layering.tracked",
            "skip",
            "git is not on PATH, so tracked AI-layer paths cannot be listed.",
        )
        return

    for project_id in project_ids:
        _check_project_layering(report, project_id, registry, repo_root)


#: The substring proving a `.pre-commit-config.yaml` actually runs DG-317's
#: operator-inventory guard, rather than merely declaring hook types a
#: *different* set of hooks would use. Matched as a raw substring over the
#: whole file rather than parsed hook-by-hook: the hook's `entry` line
#: (``entry: python scripts/check_operator_inventory.py``) and its `id`
#: (``check-operator-inventory``) spell the same guard two different ways,
#: and a substring catches either without this file growing a second,
#: hook-shape YAML parser it does not otherwise need.
_OPERATOR_INVENTORY_GUARD_MARKER: Final = "check_operator_inventory"

#: What `pre-commit install` wires when a config declares no
#: `default_install_hook_types` of its own — pre-commit's own documented
#: default, not this project's invention.
_DEFAULT_HOOK_TYPES_WHEN_UNDECLARED: Final = ("pre-commit",)

#: `default_install_hook_types: [pre-commit, commit-msg]` — flow-style YAML,
#: the shape this repository's own config currently uses.
_HOOK_TYPES_FLOW: Final = re.compile(r"^default_install_hook_types:\s*\[(.*)\]\s*$")

#: `default_install_hook_types:` with nothing after the colon — block style,
#: where each type follows on its own `- type` line.
_HOOK_TYPES_BLOCK_KEY: Final = re.compile(r"^default_install_hook_types:\s*$")


def runs_operator_inventory_guard(config_text: str) -> bool:
    """Whether *config_text* (a `.pre-commit-config.yaml`'s contents) runs
    DG-317's operator-inventory guard at all.

    A repository whose config does not run this guard is not this check's
    business — see :func:`_check_git_hooks_for_root`, which reads this as
    "nothing to verify here" rather than a defect.
    """
    return _OPERATOR_INVENTORY_GUARD_MARKER in config_text


def declared_hook_types(config_text: str) -> list[str]:
    """`default_install_hook_types` exactly as *config_text* declares it.

    Reads flow style (``[pre-commit, commit-msg]``) or block style (one
    ``- type`` per line), and falls back to pre-commit's own default of
    ``("pre-commit",)`` when the key is absent entirely — never a list this
    module hardcodes itself, so a config later adding a third or fourth
    hook type (DG-464, in parallel, is expected to add ``pre-push`` to this
    very key) is read correctly with no code change here.

    Deliberately hand-rolled rather than a YAML parser: this reads one
    scalar list, the same shape :func:`declared_version` reads one scalar
    out of ``pyproject.toml`` above, and PyYAML is not a dependency this
    package's own runtime carries — only `pre-commit`'s own dev extra pulls
    it in, and introducing it here for one list would be the second-surface
    mistake this project keeps writing up.

    Malformed or unexpected YAML near the key is read as "not this shape",
    never raised: a doctor check must not crash on a config it cannot fully
    parse, and falling back to the documented default is the same fail-safe
    direction every other parsing helper in this module already takes.
    """
    lines = config_text.splitlines()
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        flow_match = _HOOK_TYPES_FLOW.match(stripped)
        if flow_match:
            items = [
                item.strip().strip("'\"") for item in flow_match.group(1).split(",")
            ]
            return [item for item in items if item]
        if _HOOK_TYPES_BLOCK_KEY.match(stripped):
            types: list[str] = []
            for following in lines[index + 1 :]:
                item = following.strip()
                if not item:
                    continue
                if not item.startswith("-"):
                    break
                types.append(item[1:].strip().strip("'\""))
            return types
    return list(_DEFAULT_HOOK_TYPES_WHEN_UNDECLARED)


def hooks_dir(git_root: Path) -> Optional[Path]:
    """Where git itself says *git_root*'s hooks live, or ``None`` if git
    could not answer at all.

    Resolved with ``git rev-parse --git-path hooks`` rather than assumed as
    ``<git_root>/.git/hooks`` — the same reasoning as
    :func:`core.exclude.resolve_info_exclude_path`, and verified directly:
    this honours ``core.hooksPath`` when a repository sets one, and in a
    `git worktree` it resolves to the *main* checkout's shared
    ``.git/hooks`` even though the worktree's own ``.git`` is a file, not a
    directory — exactly the "a linked worktree is judged by the shared
    hooks" requirement, satisfied by git's own resolution rather than a
    second, hand-rolled worktree-detection path here.

    Routed through :func:`core.exclude.run_git` (DG-451) rather than a raw
    ``subprocess.run(["git", ...])`` — this module's own git calls
    (:func:`newest_tag`, :func:`tracked_ai_layer_paths`) already learned
    that lesson: a process with ``GIT_DIR``/``GIT_WORK_TREE`` leaked into
    its environment (a git hook, among others) can redirect an unstripped
    call onto a completely different repository, silently. ``None`` covers
    both ways :func:`run_git` can fail to answer at all —
    :class:`NotAGitRepositoryError` and :class:`GitTimedOutError` — the
    same "could not ask" outcome :func:`newest_tag` already gives those two
    for this read-only diagnostic.
    """
    try:
        result = run_git(["rev-parse", "--git-path", "hooks"], git_root, timeout=30)
    except (NotAGitRepositoryError, GitTimedOutError):
        return None
    if result.returncode != 0:
        return None
    raw: str = str(result.stdout).strip()
    if not raw:
        return None
    return (git_root / raw).resolve()


def missing_hook_types(hooks_dir_path: Path, hook_types: Sequence[str]) -> list[str]:
    """Which of *hook_types* have no usable hook file in *hooks_dir_path*.

    "Usable" means present *and*, on a platform where the bit means
    anything, executable: ``git`` invokes a hook file directly rather than
    through an interpreter it chooses, so a `pre-commit install`-written
    hook that lost its execute bit — a careless ``chmod``, an archive that
    does not preserve permissions — is silently never run, which is the
    same failure as the file not existing at all. Skipped on Windows,
    where ``os.access(..., os.X_OK)`` reports every file executable
    regardless of any real permission bit, so checking it there would only
    ever read "fine" and prove nothing.
    """
    missing: list[str] = []
    for hook_type in hook_types:
        hook_file = hooks_dir_path / hook_type
        if not hook_file.is_file():
            missing.append(hook_type)
            continue
        if sys.platform != "win32" and not os.access(hook_file, os.X_OK):
            missing.append(hook_type)
    return missing


def _check_git_hooks_for_root(report: Report, name: str, git_root: Path) -> None:
    """`guard.git_hooks`: see :func:`declared_hook_types` and
    :func:`hooks_dir` for the two questions this answers in turn — what the
    config declares, and what git itself reports as installed.

    A config that does not exist, or exists but never runs the
    operator-inventory guard, is a **skip**: this check's whole premise is
    "a repository that runs this guard also needs the hooks that run it
    installed", and a repository with no stake in that guard is not this
    check's business at all (SCOPE: "a repository without the guard is not
    checked").
    """
    config_path = git_root / ".pre-commit-config.yaml"
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        report.add(
            name,
            "skip",
            f"No readable .pre-commit-config.yaml at {config_path}.",
        )
        return

    if not runs_operator_inventory_guard(config_text):
        report.add(
            name,
            "skip",
            f"{config_path} does not run check_operator_inventory, so this "
            "checkout carries no guard for this check to verify.",
        )
        return

    resolved_hooks_dir = hooks_dir(git_root)
    if resolved_hooks_dir is None:
        report.add(
            name,
            "skip",
            f"`git rev-parse --git-path hooks` could not be answered for {git_root}.",
        )
        return

    hook_types = declared_hook_types(config_text)
    missing = missing_hook_types(resolved_hooks_dir, hook_types)
    if missing:
        report.add(
            name,
            "fail",
            f"{', '.join(missing)} hook(s) declared in default_install_hook_types "
            f"({', '.join(hook_types)}) are missing from {resolved_hooks_dir} — "
            "a checkout that runs check_operator_inventory but never installed "
            "the hooks that run it is not actually guarded.",
            remediation="pre-commit install",
        )
        return

    report.add(
        name,
        "ok",
        f"all {len(hook_types)} declared hook type(s) ({', '.join(hook_types)}) "
        f"present in {resolved_hooks_dir}",
    )


def _check_git_hooks(
    report: Report,
    project_ids: Sequence[str],
    registry: ProjectRegistry,
    repo_root: Optional[Path],
) -> None:
    """DG-466: for the source tree and every registered project whose
    ``.pre-commit-config.yaml`` runs DG-317's operator-inventory guard,
    confirm the hooks that guard depends on are actually installed.

    Checking registered roots matters on its own, independent of the
    source-tree check above: an *installed* ``drunken-doctor`` has no
    source tree at all (:func:`source_tree_root` returns ``None``), so a
    check that only ever looked at the source tree would always skip for
    exactly the deployment this check most needs to answer about.
    """
    if repo_root is not None:
        _check_git_hooks_for_root(report, "guard.git_hooks", repo_root)
    else:
        report.add(
            "guard.git_hooks",
            "skip",
            "Running from an installed package, so there is no source tree "
            "to check hooks against.",
        )

    for project_id in project_ids:
        name = f"guard.git_hooks.{project_id}"
        try:
            config = registry.get_project_config(project_id)
        except DrunkenError as exc:
            report.add_error(name, exc)
            continue

        if not config.path:
            report.add(
                name,
                "skip",
                "No path declared, so there is no checkout to inspect.",
            )
            continue

        # Same expanduser-through-resolved_path() as every other per-project
        # check in this module (DG-445) — a registered "~/checkout" must be
        # inspected, not silently skipped as a checkout that "does not
        # exist" under its literal "~" name.
        root = config.resolved_path("this operation")
        git_root = root / config.git_root if config.git_root else root

        if repo_root is not None and _same_checkout(git_root, repo_root):
            report.add(
                name,
                "skip",
                f"{git_root} is this repository's own checkout, already "
                "checked as guard.git_hooks.",
            )
            continue

        if not git_root.is_dir() or not (git_root / ".git").exists():
            report.add(name, "skip", describe_missing_git_root(git_root))
            continue

        _check_git_hooks_for_root(report, name, git_root)


def run_doctor(
    project: Optional[str] = None,
    registry: Optional[ProjectRegistry] = None,
    offline: bool = False,
) -> Report:
    """Check everything, or everything about one project."""
    report = Report()
    registry = registry or ProjectRegistry()

    _check_environment(report)
    _check_paths(report)

    project_ids = _check_registry(report, registry)
    if project:
        project_ids = [project]

    for project_id in project_ids:
        _check_project(report, project_id, registry, offline)

    _check_layering(report, project_ids, registry, source_tree_root())
    _check_content_scan(report, project_ids, registry, source_tree_root())
    _check_git_hooks(report, project_ids, registry, source_tree_root())

    _check_deployment(report, source_root=source_tree_root())
    _check_ai_layer(report)
    _check_routes(report)
    _check_host_configs(report)

    if secrets.cached_refs():
        report.add(
            "secrets.resolved",
            "ok",
            f"{len(secrets.cached_refs())} reference(s) resolved this run: "
            + ", ".join(secrets.cached_refs()),
        )
    return report


def render(report: Report) -> str:
    """Human-readable form. Values never appear — only references and outcomes."""
    width = max((len(check.name) for check in report.checks), default=0)
    lines = []
    for check in report.checks:
        data = check.to_dict()
        lines.append(
            f"{_SYMBOLS[check.status]}  {check.name.ljust(width)}  {data['detail']}"
        )
        if "remediation" in data:
            lines.append(f"{' ' * (width + 8)}-> {data['remediation']}")

    counts = report.to_dict()["summary"]
    lines.append("")
    lines.append(
        f"{counts['ok']} ok, {counts['warn']} warning, "
        f"{counts['fail']} failed, {counts['skip']} skipped"
    )
    return "\n".join(lines)


def emit_requirements(out: Optional[str] = None) -> int:
    """Write the pinned requirements and print the install command. Never runs it.

    Moved here from the retired ``drunken-config --kind install`` (DG-356). It
    belongs with the check that finds the problem: ``uv tool install`` ignores
    ``uv.lock`` and resolves afresh inside the declared ranges, so a deployment
    drifts silently — ``deployment.mcp_pin`` above is what notices, and the
    remedy used to live in a second command that warning had to name.

    **Printed, never run.** Installing replaces the deployment a host config is
    already pointing at, and doing that as a side effect of asking a diagnostic
    question is the kind of surprise this project keeps writing post-mortems
    about. Installing is the operator's step.
    """
    root = Path.cwd()
    exported = export_requirements(root)
    if exported is None:
        print(
            "warning: could not export uv.lock (is `uv` on PATH, and is this a "
            "project root?). Falling back to an unpinned install.",
            file=sys.stderr,
        )
        print(install_command(None))
        return 0

    target = Path(out).expanduser() if out else root / "requirements.lock.txt"
    target.write_text(exported, encoding="utf-8")
    # Say what was and was not done, in that order. The first version of this
    # printed the filename and the command with no verb between them, which
    # reads as a report of work completed -- and was taken as one, leaving a
    # deployment three tickets behind while every surface looked fine.
    print(f"Wrote {target} ({count_pins(exported)} pinned packages).")
    print("NOT INSTALLED. To deploy, run:\n")
    print(f"    {install_command(target)}\n")
    return 0


def main() -> int:
    """Entry point for ``drunken-doctor``."""
    import argparse  # noqa: PLC0415 - CLI only

    parser = argparse.ArgumentParser(
        prog="drunken-doctor",
        description="Diagnose drunken-guild configuration, credentials and connectivity.",
    )
    parser.add_argument("--project", help="Check only this project id.")
    parser.add_argument(
        "--registry", help="Registry file to use instead of the resolved default."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip network checks (does not verify credentials against Jira).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text."
    )
    parser.add_argument(
        "--requirements",
        nargs="?",
        const="",
        metavar="FILE",
        help=(
            "Write uv.lock as pinned requirements and print the install command "
            "that honours it. Prints; never installs."
        ),
    )
    args = parser.parse_args()

    if args.requirements is not None:
        return emit_requirements(args.requirements or None)

    report = run_doctor(
        project=args.project,
        registry=ProjectRegistry(args.registry) if args.registry else None,
        offline=args.offline,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render(report))

    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
