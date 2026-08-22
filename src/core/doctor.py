"""``drunken-doctor`` — one command that answers "why isn't this working?".

Every failure in MCP-ARCHITECTURE.md §1 shared a shape: the system kept working,
quietly, on the wrong thing. A registry read from a path that did not exist. A
credential taken from a stale ``.env`` four directories up. A board that looked
empty because the token had expired. None of them produced an error anyone could
see, and finding each one took a debugging session.

So this reports not only whether each piece resolved, but **which rule chose
it** — the path, the source of the path, the reference a credential came from.
"It says env://JIRA_TOKEN_TWA and that variable is unset" ends the investigation
immediately.

Values never appear in the output, only references and outcomes. The report is
put through :func:`~core.redact.redact` on the way out regardless, because it
quotes upstream error bodies.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - git, invoked with a fixed argument list
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Final, Literal, Optional, Sequence

from . import paths, secrets
from .context import ProjectContext
from .errors import DrunkenError
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
    """
    try:
        result = subprocess.run(  # nosec B603 - fixed argv, no shell
            ["git", "tag", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.SubprocessError):
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
                    remediation=f"chmod {oct(paths.HOME_MODE)[2:]} {path}",
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
                remediation=f"chmod 600 {path}",
            )


#: Where `uv tool install` puts the environment the host actually launches.
#: Overridable for the same reason as everything in :mod:`core.paths` — a
#: container or another machine puts it elsewhere, and a test must be able to
#: point it at a fixture.
ENV_TOOL_ROOT: Final = "DRUNKEN_TOOL_ENV"
DEFAULT_TOOL_ROOT: Final = "~/.local/share/uv/tools/drunken-guild"

#: Where the *previous* package name installed to. `uv tool` names the
#: directory after the distribution, so DG-264's rename moved it — and a
#: constant pointing at the old path made this check answer about a deployment
#: that is not the one a host launches. Reported by name rather than followed:
#: an installation under the old name is a real thing to know about, and the
#: honest report is "you are running a pre-rename install", not silence and not
#: a green line about the wrong directory.
LEGACY_TOOL_ROOTS: Final = ("~/.local/share/uv/tools/drunken-team",)

#: Modules whose absence from the deployment has actually mattered. Not every
#: module — a list that tries to be exhaustive goes stale silently, and the
#: point is to notice a *merge* that has not been deployed, which these are the
#: evidence of.
DEPLOYED_MODULES: Final = (
    "core.away",
    "core.permission_rules",
    "core.usage",
    "service.approval_hook",
    "jira_mcp.jql",
    "jira_mcp.assign",
    "jira_mcp.backlog",
)


def tool_env_root() -> Path:
    raw = os.environ.get(ENV_TOOL_ROOT) or DEFAULT_TOOL_ROOT
    return Path(os.path.expandvars(raw)).expanduser()


def compare_deployment(env_root: Path, modules: Sequence[str]) -> dict[str, list[str]]:
    """Which of *modules* are present in the installed environment at *env_root*.

    Resolved by looking for the file rather than by importing: importing another
    environment's modules into this process would be both wrong and unsafe, and
    what is being asked is whether the code was *deployed*, not whether it runs.
    A package directory counts, so a module that grows into a package does not
    read as a false gap.
    """
    site_dirs = sorted(env_root.glob("lib/*/site-packages"))
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


def deployed_version(env_root: Path, package: str) -> Optional[str]:
    """The version of *package* inside *env_root*, read from its dist-info.

    ``None`` when it cannot be determined, which is deliberately different from
    a version that disagrees — see :func:`compare_pin`.
    """
    for site in sorted(env_root.glob("lib/*/site-packages")):
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


#: Where the AI layer is installed to, and what shape it takes there.
#:
#: Only skills are compared, and only the ones this repository produces. The
#: Antigravity *agents* are generated with a transformation — the model is
#: rewritten to its tier equivalent and the skill-index path is repointed — so
#: they are correctly not byte-identical to their source and comparing them
#: would report drift on every healthy install.
AI_LAYER_ROOTS: Final = (
    ("claude.skills", "~/.claude/skills"),
    ("antigravity.skills", "~/.gemini/config/skills"),
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


def compare_ai_layer(root: Path, install_root: Path) -> dict[str, list[str]]:
    """Which of the repository's skills are absent or different at *install_root*.

    Compared by reading ``SKILL.md`` rather than by mtime or by counting
    directories. A count matched while `git-workflow` was installed at 120 lines
    against 196 in the source, and both surfaces reported themselves healthy.
    """
    missing: list[str] = []
    drifted: list[str] = []

    for name, source in repo_skills(root).items():
        installed = install_root / name / "SKILL.md"
        if not installed.is_file():
            missing.append(name)
            continue
        try:
            if installed.read_bytes() != (source / "SKILL.md").read_bytes():
                drifted.append(name)
        except OSError:
            drifted.append(name)

    return {"missing": missing, "drifted": drifted}


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
    for name, raw in AI_LAYER_ROOTS:
        install_root = Path(raw).expanduser()
        if not install_root.is_dir():
            report.add(f"ai_layer.{name}", "skip", f"Nothing installed at {raw}.")
            continue

        result = compare_ai_layer(root, install_root)
        missing, drifted = result["missing"], result["drifted"]
        if not missing and not drifted:
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
        report.add(
            f"ai_layer.{name}",
            "warn",
            "; ".join(parts)
            + ". Run scripts/install/install_skills.sh — an install is the "
            "operator's to run.",
        )


def _check_deployment(
    report: Report,
    env_root: Optional[Path] = None,
    modules: Optional[Sequence[str]] = None,
    legacy_roots: Optional[Sequence[str]] = None,
) -> None:
    """Report the gap between this checkout and the environment the host runs.

    This is the check §10.7 was reaching for. Merging a fix does not deploy it:
    ``~/.local/bin/drunken-*`` symlinks into the ``uv tool`` environment, and
    that is what a host config launches — not this checkout. The gap has been
    found twice by hand and never by a check.

    A missing environment is a **skip**, not a failure: a container, CI or a
    fresh clone legitimately has none, and a check that cries wolf there is a
    check everyone learns to ignore.
    """
    env_root = env_root if env_root is not None else tool_env_root()
    modules = modules if modules is not None else DEPLOYED_MODULES
    # Injectable for the same reason as `env_root`: otherwise this check reads
    # the developer's own machine, and a test asserting "no install is a skip"
    # passes or fails depending on whose laptop runs it.
    legacy_roots = legacy_roots if legacy_roots is not None else LEGACY_TOOL_ROOTS

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
    else:
        report.add(
            "deployment.tool_env",
            "ok",
            f"{env_root} carries all {len(result['present'])} checked modules",
        )

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
    true of ISAC on 2026-08-16 and cost hours, because the two facts the reader
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

    Naming the reference is the point: "it says env://JIRA_TOKEN_TWA" is what
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
    name = f"project.{project_id}.jira"
    try:
        jira = context.require_jira()
        identity = context.verify_jira_identity()
    except DrunkenError as exc:
        report.add_error(name, exc)
        return
    report.add(
        name,
        "ok",
        f"{jira.url} as {identity.display_name or identity.email} "
        f"(project {jira.project_key})",
    )


def _check_project_paths(
    report: Report, project_id: str, context: ProjectContext
) -> None:
    declared = context.config.path
    if declared is None:
        report.add(
            f"project.{project_id}.path",
            "skip",
            "No path declared — fine for a Jira/Discord-only or containerised project.",
        )
        return

    root = Path(declared)
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

    if context.discord is None:
        report.add(
            f"project.{project_id}.discord", "skip", "No Discord channel configured."
        )
    else:
        report.add(
            f"project.{project_id}.discord",
            "ok",
            f"channel {context.discord.channel_id}",
        )


def _check_daemon(report: Report) -> None:
    socket = paths.daemon_socket_path()
    path = socket.path
    if not path.exists():
        report.add(
            "daemon.socket",
            "warn",
            f"No socket at {path} (from {socket.source}) — the approval daemon is not running.",
            remediation=(
                "Start it with 'drunken-listen'. Discord approval falls back to "
                "asking in-conversation, so this is not fatal."
            ),
        )
        return

    report.add("daemon.socket", "ok", f"{path}  (from {socket.source})")
    if paths.is_group_or_world_accessible(path):
        report.add(
            "daemon.socket.permissions",
            "fail",
            f"{path} is reachable by other users on this machine, who could "
            "approve actions as the Boss.",
            remediation=f"chmod 600 {path} and restart the daemon.",
        )


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

    _check_daemon(report)
    _check_deployment(report)
    _check_ai_layer(report)

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
    args = parser.parse_args()

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
