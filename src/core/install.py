"""``drunken-install`` puts the guild's skills into ``~/.claude/skills`` from the installed package — DG-499.

REQ-022: a new skill reaches a machine that has the guild installed with one command, no clone and no
model call. The skills travel inside the wheel as ``drunken_skills`` (DG-498); this reads that copy —
or, run from a source checkout, the repository's own ``skills/`` — and makes the target match it.

It does what ``scripts/install/install_skills.sh`` and ``.ps1`` do, in one place that behaves the same
on Windows and POSIX (the two scripts disagreed: DG-455 a case-only name, DG-458 ``$env:HOME`` not
sandboxing, DG-488 a missing BOM). The scripts stay until this has shipped.

* **Install/update:** each skill folder is copied file by file; a file is rewritten only when its
  bytes differ, through a temporary file and an atomic replace, so an interrupted run leaves either
  the old file or the new one.
* **Never through a link.** A target folder or file that is a symlink is refused for that skill and
  named; the target root itself being a link refuses the whole run.
* **Prune is opt-in and narrow.** ``--prune`` lists, ``--prune-apply`` removes, and only names on
  ``scripts/install/retired_skills.txt``; anything else installed but not shipped is reported as
  unrecognised and never removed (a hand-written skill was once deleted by a broader first cut).
* **The target is explicit.** ``--target`` or ``~/.claude/skills``; an unresolvable home refuses
  rather than writing relative to wherever the shell happens to be (DG-359). Tests always pass
  ``--target``, so nothing here is ever run against the real one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import sysconfig
import tempfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Optional, Sequence

from .errors import DrunkenError, ValidationError

#: Where a source checkout keeps the skills when ``drunken_skills`` is not importable.
_SOURCE_TREE = Path(__file__).resolve().parent.parent.parent


class InstallRefusedError(ValidationError):
    """The run was refused before it changed anything."""


@dataclass
class SkillAction:
    name: str
    status: str  # "new" | "updated" | "unchanged" | "refused"
    files: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class Orphan:
    name: str
    kind: str  # "retired" | "unrecognised"
    note: str = ""


@dataclass
class InstallResult:
    source: Path
    target: Path
    applied: bool
    skills: list[SkillAction] = field(default_factory=list)
    index_updated: bool = False
    orphans: list[Orphan] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)


def packaged_skills_dir() -> Path:
    """The skills shipped with this install: the wheel's ``drunken_skills``, else the repo's ``skills/``."""
    try:
        root = Path(str(resources.files("drunken_skills")))
        if root.is_dir():
            return root
    except (ModuleNotFoundError, TypeError):
        pass
    candidate = _SOURCE_TREE / "skills"
    if candidate.is_dir():
        return candidate
    raise InstallRefusedError(
        "no packaged skills were found, and this is not a source checkout.",
        remediation="Reinstall: uv tool install --force <the guild>.",
    )


def retired_names() -> frozenset[str]:
    """The only names ``--prune-apply`` may ever remove (``retired_skills.txt``, minus comments)."""
    candidates: list[Path] = []
    try:
        candidates.append(
            Path(str(resources.files("scripts"))) / "install" / "retired_skills.txt"
        )
    except (ModuleNotFoundError, TypeError):
        pass
    candidates.append(_SOURCE_TREE / "scripts" / "install" / "retired_skills.txt")
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8-sig")
            return frozenset(
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
    return frozenset()


def _external_names(source: Path) -> frozenset[str]:
    path = source / ".external"
    if not path.is_file():
        return frozenset()
    return frozenset(
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _skill_folders(source: Path) -> dict[str, Path]:
    """{install name: source folder} for every folder that holds a SKILL.md; duplicates refuse."""
    found: dict[str, Path] = {}
    for skill_md in sorted(source.rglob("SKILL.md")):
        folder = skill_md.parent
        if folder == source:
            continue
        if folder.name in found:
            raise InstallRefusedError(
                f"two skills share the folder name {folder.name!r}; they would install to the "
                f"same place ({found[folder.name]} and {folder}).",
                remediation="Rename one of them in the source; nothing was changed.",
            )
        found[folder.name] = folder
    return found


def _files_in(folder: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise InstallRefusedError(
                f"the source skill file {path} is a symlink.",
                remediation="The shipped skills hold real files only; nothing was changed.",
            )
        if path.is_file():
            out.append(path.relative_to(folder))
    return out


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _differs(source: Path, target: Path) -> bool:
    return not target.is_file() or _digest(source) != _digest(target)


def _behind_a_link(target_root: Path, path: Path) -> Optional[Path]:
    """The first link on the way from *target_root* (exclusive) down to *path*, if any."""
    current = path
    while current != target_root and target_root in current.parents:
        if current.is_symlink():
            return current
        current = current.parent
    return None


def _plan_skill(name: str, src: Path, target_root: Path) -> SkillAction:
    dest = target_root / name
    rels = _files_in(src)
    if dest.is_symlink():
        return SkillAction(name, "refused", reason=f"{dest} is a link, not touched")
    for rel in rels:
        link = _behind_a_link(target_root, dest / rel)
        if link is not None:
            return SkillAction(name, "refused", reason=f"{link} is a link, not touched")
    changed = [rel.as_posix() for rel in rels if _differs(src / rel, dest / rel)]
    if not dest.exists():
        return SkillAction(name, "new", changed)
    return SkillAction(name, "updated" if changed else "unchanged", changed)


def _write_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".drunken-install-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.read_bytes())
        shutil.copymode(source, tmp_name)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _apply_skill(action: SkillAction, src: Path, target_root: Path) -> None:
    for rel in action.files:
        _write_atomic(src / rel, target_root / action.name / rel)


def _installed_names(target_root: Path) -> list[str]:
    if not target_root.is_dir():
        return []
    names = []
    for entry in sorted(target_root.iterdir()):
        if entry.is_symlink() or (entry.is_dir() and (entry / "SKILL.md").is_file()):
            names.append(entry.name)
    return names


def _find_orphans(
    target_root: Path, ours: set[str], external: frozenset[str], retired: frozenset[str]
) -> list[Orphan]:
    orphans: list[Orphan] = []
    for name in _installed_names(target_root):
        if name in ours or name in external:
            continue
        kind = "retired" if name in retired else "unrecognised"
        note = "link, not touched" if (target_root / name).is_symlink() else ""
        orphans.append(Orphan(name, kind, note))
    return orphans


def _prune(target_root: Path, orphans: list[Orphan]) -> list[str]:
    removed: list[str] = []
    for orphan in orphans:
        path = target_root / orphan.name
        if orphan.kind != "retired" or path.is_symlink() or not path.is_dir():
            continue
        shutil.rmtree(path)
        removed.append(orphan.name)
    return removed


def _sync_index(source: Path, target_root: Path, apply: bool) -> bool:
    src = source / "INDEX.md"
    if not src.is_file():
        return False
    dest = target_root / "INDEX.md"
    if dest.is_symlink():
        raise InstallRefusedError(
            f"{dest} is a link.", remediation="Nothing was changed."
        )
    changed = _differs(src, dest)
    if changed and apply:
        _write_atomic(src, dest)
    return changed


def install_skills(
    target_root: Path,
    *,
    source: Optional[Path] = None,
    apply: bool = True,
    prune: bool = False,
    prune_apply: bool = False,
) -> InstallResult:
    """Plan (``apply=False``) or perform the install of the packaged skills into *target_root*."""
    if prune_apply and not prune:
        raise InstallRefusedError(
            "--prune-apply needs --prune: list what would be removed first.",
            remediation="Run with --prune, read the list, then add --prune-apply.",
        )
    target_root = Path(target_root)
    if target_root.is_symlink():
        raise InstallRefusedError(
            f"the target {target_root} is a link.",
            remediation="Point --target at the real folder; nothing was changed.",
        )
    src_root = Path(source) if source is not None else packaged_skills_dir()
    folders = _skill_folders(src_root)
    actions = [
        _plan_skill(name, folder, target_root) for name, folder in folders.items()
    ]

    result = InstallResult(src_root, target_root, applied=apply, skills=actions)
    if apply:
        target_root.mkdir(parents=True, exist_ok=True)
        for action in actions:
            if action.status in ("new", "updated"):
                _apply_skill(action, folders[action.name], target_root)
    result.index_updated = _sync_index(src_root, target_root, apply)
    result.orphans = _find_orphans(
        target_root, set(folders), _external_names(src_root), retired_names()
    )
    if prune and prune_apply and apply:
        result.pruned = _prune(target_root, result.orphans)
    return result


def packaged_agents_dir() -> Path:
    """The agent adapters shipped with this install: the wheel's ``drunken_agents``, else ``agents/``."""
    try:
        root = Path(str(resources.files("drunken_agents")))
        if root.is_dir():
            return root
    except (ModuleNotFoundError, TypeError):
        pass
    candidate = _SOURCE_TREE / "agents"
    if candidate.is_dir():
        return candidate
    raise InstallRefusedError(
        "no packaged agents were found, and this is not a source checkout.",
        remediation="Reinstall: uv tool install --force <the guild>.",
    )


@dataclass
class AgentsResult:
    source: Path
    target: Path
    applied: bool
    agents: list[SkillAction] = field(default_factory=list)
    index_updated: bool = False
    orphans: list[str] = field(default_factory=list)


def _manifest_roles(source: Path) -> dict[str, str]:
    """{role: skill it needs} from ``_sources.json``; any malformed entry is a refusal, never a skip."""
    path = source / "_sources.json"
    if not path.is_file():
        raise InstallRefusedError(
            f"{path} is missing, so no role's skill dependency can be verified.",
            remediation="Reinstall the package; no agent was installed.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise InstallRefusedError(
            f"{path} cannot be read as JSON: {exc}",
            remediation="No agent was installed.",
        ) from exc
    if not isinstance(data, dict) or not data:
        raise InstallRefusedError(
            f"{path} must be a non-empty JSON object.",
            remediation="No agent was installed.",
        )
    roles: dict[str, str] = {}
    for role, entry in data.items():
        skill = entry.get("skill") if isinstance(entry, dict) else None
        if not isinstance(skill, str) or not skill.strip():
            raise InstallRefusedError(
                f"role {role!r} in {path} names no skill.",
                remediation="No agent was installed.",
            )
        roles[role] = skill.strip()
    return roles


def _adapter_names(source: Path) -> list[str]:
    return sorted(
        p.stem for p in source.glob("*.md") if p.name != "INDEX.md" and p.is_file()
    )


def _agents_problems(
    source: Path, roles: dict[str, str], skills_target: Path
) -> list[str]:
    """Every reason this install must write nothing (all-or-nothing, DG-459)."""
    problems: list[str] = []
    adapters = _adapter_names(source)
    for name in adapters:
        if name not in roles:
            problems.append(f"agent {name!r} has no entry in _sources.json")
    for name in roles:
        if name not in adapters:
            problems.append(
                f"role {name!r} is in _sources.json but has no adapter file"
            )
    for name in adapters:
        skill = roles.get(name)
        if skill is None:
            continue
        skill_md = skills_target / skill / "SKILL.md"
        if not skill_md.is_file():
            problems.append(
                f"agent {name!r} needs the {skill!r} skill, not installed at {skill_md}"
            )
    return problems


def _plan_agent(name: str, src_root: Path, target_root: Path) -> SkillAction:
    dest = target_root / f"{name}.md"
    if dest.is_symlink():
        return SkillAction(name, "refused", reason=f"{dest} is a link")
    if not dest.exists():
        return SkillAction(name, "new", [f"{name}.md"])
    if _differs(src_root / f"{name}.md", dest):
        return SkillAction(name, "updated", [f"{name}.md"])
    return SkillAction(name, "unchanged")


def install_agents(
    target_root: Path,
    skills_target: Path,
    *,
    source: Optional[Path] = None,
    apply: bool = True,
) -> AgentsResult:
    """Plan or perform the install of the packaged agent adapters into *target_root*.

    All-or-nothing: if the manifest is missing or malformed, an adapter and the manifest disagree, or
    a role's skill is not installed under *skills_target*, **nothing is written** and the refusal
    lists every problem (the shell script installed the roles it could and exited 1: DG-459).
    """
    target_root = Path(target_root)
    if target_root.is_symlink():
        raise InstallRefusedError(
            f"the target {target_root} is a link.",
            remediation="Point --agents-target at the real folder; nothing was changed.",
        )
    src_root = Path(source) if source is not None else packaged_agents_dir()
    roles = _manifest_roles(src_root)
    problems = _agents_problems(src_root, roles, Path(skills_target))
    if problems:
        raise InstallRefusedError(
            "refusing to install any agent: " + "; ".join(problems) + ".",
            remediation="Install the skills first (drunken-install skills), then run this again.",
        )

    result = AgentsResult(src_root, target_root, applied=apply)
    result.agents = [
        _plan_agent(n, src_root, target_root) for n in _adapter_names(src_root)
    ]
    if apply:
        target_root.mkdir(parents=True, exist_ok=True)
        for action in result.agents:
            if action.status in ("new", "updated"):
                _write_atomic(
                    src_root / f"{action.name}.md", target_root / f"{action.name}.md"
                )
    result.index_updated = _sync_index(src_root, target_root, apply)
    ours = set(_adapter_names(src_root))
    if target_root.is_dir():
        result.orphans = sorted(
            p.stem
            for p in target_root.glob("*.md")
            if p.name != "INDEX.md" and p.stem not in ours
        )
    return result


@dataclass
class StatusReport:
    skills_changes: list[str] = field(default_factory=list)
    agents_changes: list[str] = field(default_factory=list)
    retired_installed: list[str] = field(default_factory=list)
    changelog_heading: str = ""
    changelog_body: str = ""

    @property
    def up_to_date(self) -> bool:
        return not (self.skills_changes or self.agents_changes)


def changelog_text() -> str:
    """The changelog: the installed data file, else the source tree's."""
    for candidate in (
        Path(sysconfig.get_path("data")) / "share" / "drunken-guild" / "CHANGELOG.md",
        _SOURCE_TREE / "CHANGELOG.md",
    ):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8-sig")
    return ""


def newest_changelog_section(text: str) -> tuple[str, str]:
    """(heading, body) of the first ``## `` section of *text*; empty strings when there is none."""
    match = re.search(r"^## (.+?)[ \t]*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return (match.group(1).strip(), match.group(2).strip()) if match else ("", "")


def status(
    skills_target: Path,
    agents_target: Path,
    *,
    skills_source: Optional[Path] = None,
    agents_source: Optional[Path] = None,
) -> StatusReport:
    """What an update would change, by content. Read-only: writes and creates nothing."""
    skills_src = (
        Path(skills_source) if skills_source is not None else packaged_skills_dir()
    )
    agents_src = (
        Path(agents_source) if agents_source is not None else packaged_agents_dir()
    )
    report = StatusReport()
    folders = _skill_folders(skills_src)
    for name, folder in folders.items():
        action = _plan_skill(name, folder, Path(skills_target))
        if action.status in ("new", "updated"):
            report.skills_changes.append(f"{action.status}: {name}")
        elif action.status == "refused":
            report.skills_changes.append(f"refused: {name} ({action.reason})")
    if _sync_index(skills_src, Path(skills_target), apply=False):
        report.skills_changes.append("changed: INDEX.md")
    for name in _adapter_names(agents_src):
        action = _plan_agent(name, agents_src, Path(agents_target))
        if action.status != "unchanged":
            report.agents_changes.append(f"{action.status}: {name}")
    retired = retired_names()
    report.retired_installed = [
        n
        for n in _installed_names(Path(skills_target))
        if n in retired and n not in folders
    ]
    report.changelog_heading, report.changelog_body = newest_changelog_section(
        changelog_text()
    )
    return report


def default_target() -> Path:
    home = os.environ.get("USERPROFILE") if os.name == "nt" else os.environ.get("HOME")
    if not home or not Path(home).is_absolute():
        try:
            home = str(Path.home())
        except RuntimeError as exc:
            raise InstallRefusedError(
                "the home directory cannot be resolved.",
                remediation="Pass --target <folder>; nothing was changed.",
            ) from exc
    return Path(home) / ".claude" / "skills"


def _print_report(result: InstallResult, *, prune: bool, prune_apply: bool) -> None:
    print(f"source : {result.source}")
    print(f"target : {result.target}")
    labels = {
        "new": "[+] installed",
        "updated": "[*] updated",
        "unchanged": "[=] up to date",
    }
    for action in result.skills:
        if action.status == "refused":
            print(f"[!] refused    : {action.name} — {action.reason}")
        else:
            verb = (
                labels[action.status]
                if result.applied
                else labels[action.status]
                .replace("installed", "would install")
                .replace("updated", "would update")
            )
            print(f"{verb:<16}: {action.name}")
    if result.index_updated:
        print(
            "INDEX.md       : " + ("written" if result.applied else "would be written")
        )
    _print_orphans(result, prune=prune, prune_apply=prune_apply)
    if not result.applied:
        print("dry run        : nothing was written.")


def _print_orphans(result: InstallResult, *, prune: bool, prune_apply: bool) -> None:
    if not result.orphans:
        return
    retired = [o for o in result.orphans if o.kind == "retired"]
    other = [o for o in result.orphans if o.kind != "retired"]
    if prune:
        head = (
            "removed"
            if (prune_apply and result.applied)
            else "would remove (add --prune-apply)"
        )
        print(f"retired, {head}:")
        for orphan in retired:
            print(f"  {result.target / orphan.name} {orphan.note}".rstrip())
        if not retired:
            print("  (none)")
    else:
        print(
            "installed here but not shipped (left in place; --prune lists retired ones):"
        )
        for orphan in result.orphans:
            print(f"  {orphan.name} [{orphan.kind}]")
        return
    if other:
        print("unrecognised, never pruned automatically:")
        for orphan in other:
            print(f"  {orphan.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drunken-install",
        description=(
            "Install or update the guild's skills and agents from this package into ~/.claude. "
            "No clone, no model call."
        ),
    )
    sub = parser.add_subparsers(dest="what", required=True)
    for name, help_text in (
        ("skills", "install or update the skills"),
        ("agents", "install or update the agents (needs their skills installed first)"),
        ("all", "skills, then agents — the usual update"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--target", help="Skills folder. Default: ~/.claude/skills.")
        cmd.add_argument(
            "--agents-target", help="Agents folder. Default: ~/.claude/agents."
        )
        cmd.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change; write nothing.",
        )
        if name != "agents":
            cmd.add_argument(
                "--prune",
                action="store_true",
                help="List retired skills still installed.",
            )
            cmd.add_argument(
                "--prune-apply",
                action="store_true",
                help="With --prune: remove them. Only names on retired_skills.txt are ever removed.",
            )
    stat = sub.add_parser(
        "status", help="say what an update would change, without applying it"
    )
    stat.add_argument("--target", help="Skills folder. Default: ~/.claude/skills.")
    stat.add_argument(
        "--agents-target", help="Agents folder. Default: ~/.claude/agents."
    )
    return parser


def default_agents_target() -> Path:
    return default_target().parent / "agents"


def _targets(args: argparse.Namespace) -> tuple[Path, Path]:
    skills = Path(args.target).expanduser() if args.target else default_target()
    agents = (
        Path(args.agents_target).expanduser()
        if args.agents_target
        else (skills.parent / "agents" if args.target else default_agents_target())
    )
    return skills, agents


def _print_agents(result: AgentsResult) -> None:
    print(f"agents : {result.target}")
    labels = {
        "new": "[+] installed",
        "updated": "[*] updated",
        "unchanged": "[=] up to date",
    }
    for action in result.agents:
        if action.status == "refused":
            print(f"[!] refused    : {action.name} — {action.reason}")
        else:
            print(f"{labels[action.status]:<16}: {action.name}")
    if result.index_updated:
        print(
            "INDEX.md       : " + ("written" if result.applied else "would be written")
        )
    for name in result.orphans:
        print(f"installed here but not shipped (left in place): {name}")
    if not result.applied:
        print("dry run        : nothing was written.")


def _print_status(report: StatusReport) -> None:
    if report.up_to_date:
        print("up to date: the installed skills and agents match this package.")
    else:
        print("an update would change:")
        for line in (*report.skills_changes, *report.agents_changes):
            print(f"  {line}")
        print("apply it with: drunken-install all")
    for name in report.retired_installed:
        print(
            f"retired, still installed: {name} (drunken-install skills --prune lists them)"
        )
    if report.changelog_heading:
        print(f"\nchangelog — {report.changelog_heading}")
        print(report.changelog_body)
    else:
        print("\nchangelog: not found in this install.")


def _run(args: argparse.Namespace) -> int:
    skills_target, agents_target = _targets(args)
    if args.what == "status":
        _print_status(status(skills_target, agents_target))
        return 0
    refused = False
    if args.what in ("skills", "all"):
        result = install_skills(
            skills_target,
            apply=not args.dry_run,
            prune=args.prune,
            prune_apply=args.prune_apply,
        )
        _print_report(result, prune=args.prune, prune_apply=args.prune_apply)
        refused = any(a.status == "refused" for a in result.skills)
    if args.what in ("agents", "all"):
        if args.what == "all":
            print()
        agents = install_agents(agents_target, skills_target, apply=not args.dry_run)
        _print_agents(agents)
        refused = refused or any(a.status == "refused" for a in agents.agents)
    return 1 if refused else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except DrunkenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if exc.remediation:
            print(f"  -> {exc.remediation}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
