"""``drunken-install extras`` — the drunken-extras plugin's optional skills and agents, DG-512.

The operator order: ``plugins/drunken-extras/`` holds 16 skills and 15 specialist agents that were
never wired into any installer, so no machine with the guild installed could reach them without a
clone — the same gap REQ-022 closed for the core skills and roles, left open here.

``plugins/drunken-extras`` stays the single source of truth; nothing here duplicates its files in
git. They travel inside the wheel as ``drunken_extras`` (added beside ``drunken_skills`` and
``drunken_agents`` in ``pyproject.toml``), and this reads that copy — or, run from a source
checkout, the repository's own ``plugins/drunken-extras``.

* **Plan by default, write only with ``apply=True``.** The CLI wires this to ``--apply``.
* **``only``** narrows the run to named skills/agents; a name that is neither ships nor installs —
  the whole call is refused before anything is written.
* **Never removes anything.** There is no prune here, unlike the core skills installer's
  ``--prune``: these are optional by nature, so "installed but not in this run" is never read as
  "remove it".
* **An existing file that already differs from the packaged one is reported as ``"differs"``, never
  overwritten** — the same rule ``install_agents`` enforces for a role adapter already on disk.
* **Link-safety is reused, not reinvented**: the same ``_is_link``/``_assert_inside``/atomic-write
  helpers ``core.install`` already uses for the core skills and agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from .errors import ValidationError
from .install import (
    InstallRefusedError,
    _differs,
    _is_link,
    _package_dir,
    _skill_folders,
    _write_atomic,
)
from .install import SkillAction as _Action  # re-exported shape, same fields

__all__ = [
    "InstallRefusedError",
    "ExtrasResult",
    "packaged_extras_dir",
    "extras_skill_names",
    "extras_agent_names",
    "plan_extras",
    "install_extras",
    "extras_status",
    "print_report",
]

_SOURCE_TREE = Path(__file__).resolve().parent.parent.parent


@dataclass
class ExtrasResult:
    source: Path
    skills_target: Path
    agents_target: Path
    applied: bool
    skills: list[_Action] = field(default_factory=list)
    agents: list[_Action] = field(default_factory=list)


def packaged_extras_dir() -> Path:
    """The drunken-extras tree: the wheel's ``drunken_extras``, else the repo's own copy."""
    root = _package_dir("drunken_extras")
    if root is not None:
        return root
    candidate = _SOURCE_TREE / "plugins" / "drunken-extras"
    if candidate.is_dir():
        return candidate
    raise InstallRefusedError(
        "no packaged drunken-extras were found, and this is not a source checkout.",
        remediation="Reinstall: uv tool install --force <the guild>.",
    )


def _agent_names(source: Path) -> list[str]:
    agents_dir = source / "agents"
    if not agents_dir.is_dir():
        return []
    return sorted(
        p.stem for p in agents_dir.glob("*.md") if p.name != "INDEX.md" and p.is_file()
    )


def extras_skill_names(source: Optional[Path] = None) -> list[str]:
    src = Path(source) if source is not None else packaged_extras_dir()
    skills_dir = src / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(_skill_folders(skills_dir))


def extras_agent_names(source: Optional[Path] = None) -> list[str]:
    src = Path(source) if source is not None else packaged_extras_dir()
    return _agent_names(src)


def _plan_agent_file(name: str, src_root: Path, target_root: Path) -> _Action:
    dest = target_root / f"{name}.md"
    src = src_root / "agents" / f"{name}.md"
    if _is_link(dest):
        return _Action(name, "refused", reason=f"{dest} is a link, not touched")
    if not dest.exists():
        return _Action(name, "new", [f"{name}.md"])
    if _differs(src, dest):
        return _Action(
            name, "differs", reason=f"{dest} exists and differs; not overwritten"
        )
    return _Action(name, "unchanged")


def _validate_only(
    only: Optional[Sequence[str]],
    skill_names: Sequence[str],
    agent_names: Sequence[str],
) -> Optional[set[str]]:
    if only is None:
        return None
    wanted = set(only)
    known = set(skill_names) | set(agent_names)
    unknown = sorted(wanted - known)
    if unknown:
        raise InstallRefusedError(
            f"unknown extras name(s): {', '.join(unknown)}.",
            remediation=(
                "Check the name against `drunken-install extras` with no --only, "
                "which lists every available skill and agent; nothing was changed."
            ),
        )
    return wanted


def plan_extras(
    skills_target: Path,
    agents_target: Path,
    *,
    source: Optional[Path] = None,
    only: Optional[Sequence[str]] = None,
) -> ExtrasResult:
    """Plan the install: what would be written, skipped, or left alone. Writes nothing."""
    skills_target = Path(skills_target)
    agents_target = Path(agents_target)
    if _is_link(skills_target) or _is_link(agents_target):
        raise InstallRefusedError(
            "a target is a link.",
            remediation="Point --target/--agents-target at the real folders; nothing was changed.",
        )
    src_root = Path(source) if source is not None else packaged_extras_dir()
    skill_folders = (
        _skill_folders(src_root / "skills") if (src_root / "skills").is_dir() else {}
    )
    agent_names = _agent_names(src_root)
    wanted = _validate_only(only, list(skill_folders), agent_names)

    skills = [
        _plan_skill_action(name, folder, skills_target)
        for name, folder in sorted(skill_folders.items())
        if wanted is None or name in wanted
    ]
    agents = [
        _plan_agent_file(name, src_root, agents_target)
        for name in agent_names
        if wanted is None or name in wanted
    ]
    return ExtrasResult(
        src_root,
        skills_target,
        agents_target,
        applied=False,
        skills=skills,
        agents=agents,
    )


def _plan_skill_action(name: str, src: Path, target_root: Path) -> _Action:
    dest = target_root / name
    if _is_link(dest):
        return _Action(name, "refused", reason=f"{dest} is a link, not touched")
    rels = [p.relative_to(src) for p in sorted(src.rglob("*")) if p.is_file()]
    if not dest.exists():
        return _Action(name, "new", [r.as_posix() for r in rels])
    changed = [r.as_posix() for r in rels if _differs(src / r, dest / r)]
    if changed:
        existing_mismatch = any(
            (dest / r).is_file() and _differs(src / r, dest / r) for r in rels
        )
        if existing_mismatch:
            return _Action(
                name, "differs", reason=f"{dest} exists and differs; not overwritten"
            )
    return _Action(name, "unchanged")


def install_extras(
    skills_target: Path,
    agents_target: Path,
    *,
    source: Optional[Path] = None,
    apply: bool = False,
    only: Optional[Sequence[str]] = None,
) -> ExtrasResult:
    """Plan (``apply=False``) or perform the install of the drunken-extras skills and agents.

    A skill or agent already on disk whose content differs from the packaged one is reported as
    ``"differs"`` and left untouched — never overwritten silently. Nothing is ever removed.
    """
    result = plan_extras(skills_target, agents_target, source=source, only=only)
    result.applied = apply
    if not apply:
        return result

    skills_target = Path(skills_target)
    agents_target = Path(agents_target)
    skill_folders = (
        _skill_folders(result.source / "skills")
        if (result.source / "skills").is_dir()
        else {}
    )
    for action in result.skills:
        if action.status != "new":
            continue
        skills_target.mkdir(parents=True, exist_ok=True)
        src_folder = skill_folders[action.name]
        for rel in action.files:
            _write_atomic(
                src_folder / rel, skills_target / action.name / rel, skills_target
            )

    for action in result.agents:
        if action.status != "new":
            continue
        agents_target.mkdir(parents=True, exist_ok=True)
        _write_atomic(
            result.source / "agents" / f"{action.name}.md",
            agents_target / f"{action.name}.md",
            agents_target,
        )
    return result


def extras_status(
    skills_target: Path,
    agents_target: Path,
    *,
    source: Optional[Path] = None,
) -> list[str]:
    """Lines for ``drunken-install status``: one per extra that is missing, differs, or stale.

    Read-only: writes and creates nothing.
    """
    result = plan_extras(skills_target, agents_target, source=source)
    lines: list[str] = []
    for action in (*result.skills, *result.agents):
        if action.status == "new":
            lines.append(f"missing: {action.name}")
        elif action.status == "differs":
            lines.append(f"differs: {action.name} ({action.reason})")
        elif action.status == "refused":
            lines.append(f"refused: {action.name} ({action.reason})")
    return lines


def print_report(result: ExtrasResult) -> None:
    print(f"source       : {result.source}")
    print(f"skills target: {result.skills_target}")
    print(f"agents target: {result.agents_target}")
    labels = {
        "new": "[+] installed" if result.applied else "[+] would install",
        "unchanged": "[=] up to date",
    }
    for action in (*result.skills, *result.agents):
        if action.status == "differs":
            print(f"[!] differs    : {action.name} — {action.reason}")
        elif action.status == "refused":
            print(f"[!] refused    : {action.name} — {action.reason}")
        else:
            print(f"{labels[action.status]:<16}: {action.name}")
    if not result.applied:
        print("dry run      : nothing was written; add --apply to install.")


# Re-exported so callers of this module need not also import core.install.
ValidationError = ValidationError
