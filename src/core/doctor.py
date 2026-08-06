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
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Final, Literal, Optional

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
        return version("drunken-team")
    except PackageNotFoundError:
        return "unknown (not installed as a package)"


def _check_environment(report: Report) -> None:
    report.add("version.drunken-team", "ok", package_version())
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
            f"{git_root} is not a git repository.",
            remediation=(
                "If the repo lives in a subdirectory, set 'git_root' for this "
                "project so git commands run in the right place."
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
        description="Diagnose drunken-team configuration, credentials and connectivity.",
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
