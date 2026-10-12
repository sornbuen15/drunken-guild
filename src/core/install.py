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
import shlex
import shutil
import subprocess  # nosec B404 - a fixed, self-generated argv, run with shell=False
import sys
import sysconfig
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources as importlib_resources
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Callable, Final, Iterator, Optional, Sequence

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


def _package_dir(name: str) -> Optional[Path]:
    """Where an installed package's files live, found without importing it.

    ``importlib.resources.files`` is not used: ``drunken_skills`` is the repository's ``skills/``
    folder under an importable name and has no ``__init__.py``, so it is a namespace package and
    ``files()`` hands back a multiplexed path that is not a directory (found by installing the
    wheel into a clean venv; tests that run from the source tree never see it).
    """
    try:
        spec = importlib_util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        if Path(location).is_dir():
            return Path(location)
    return None


def packaged_skills_dir() -> Path:
    """The skills shipped with this install: the wheel's ``drunken_skills``, else the repo's ``skills/``."""
    root = _package_dir("drunken_skills")
    if root is not None:
        return root
    candidate = _SOURCE_TREE / "skills"
    if candidate.is_dir():
        return candidate
    raise InstallRefusedError(
        "no packaged skills were found, and this is not a source checkout.",
        remediation="Reinstall: uv tool install --force <the guild>.",
    )


def _plain_name(name: str) -> bool:
    """A single path component: no separators, no drive, not '.' or '..', not empty."""
    return (
        bool(name) and name not in (".", "..") and not any(c in name for c in "/\\:\0")
    )


def retired_names() -> frozenset[str]:
    """The only names ``--prune-apply`` may ever remove (``retired_skills.txt``, minus comments)."""
    candidates: list[Path] = []
    scripts = _package_dir("scripts")
    if scripts is not None:
        candidates.append(scripts / "install" / "retired_skills.txt")
    candidates.append(_SOURCE_TREE / "scripts" / "install" / "retired_skills.txt")
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8-sig")
            return frozenset(
                line.strip()
                for line in text.splitlines()
                if line.strip()
                and not line.lstrip().startswith("#")
                and _plain_name(line.strip())
            )
    return frozenset()


def _extras_skill_names() -> frozenset[str]:
    """Skill names the packaged ``drunken-extras`` plugin ships (DG-514).

    A name here must never be reported or removed as retired or unrecognised: these are shipped by
    this very package, through ``drunken-install extras``, not abandoned. Imported lazily — module
    level would be circular, since ``install_extras`` itself imports from this module. Any failure
    to find the packaged extras (none built, or a stripped-down install) is read as "no extras
    names to exclude", never as a reason to fail the caller.
    """
    from . import install_extras

    try:
        return frozenset(install_extras.extras_skill_names())
    except InstallRefusedError:
        return frozenset()


def _extras_agent_names() -> frozenset[str]:
    """Agent adapter names the packaged ``drunken-extras`` plugin ships (DG-514). See
    :func:`_extras_skill_names` — same reasoning, same fallback."""
    from . import install_extras

    try:
        return frozenset(install_extras.extras_agent_names())
    except InstallRefusedError:
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


def _walk_no_links(root: Path) -> Iterator[Path]:
    """Every path under *root*, depth-first, never descending into a link.

    ``Path.rglob`` does not know a Windows junction from an ordinary folder: a junction is a
    reparse point, but ``Path.is_symlink()`` (and ``os.path.islink``) is False for one — see
    ``_is_link`` below, confirmed on this build. ``rglob`` therefore follows a junction wherever
    it leads, and a folder planted back into its own tree — one junction suffices to go deep,
    two cross-referencing ones make the walk double in size every level — turns the walk
    exponential: measured, two such junctions produced 20000 entries in 6s and kept climbing
    (DG-510). The caller's own ``_is_link`` check still refuses the junction itself; this only
    stops the walk from ever stepping through it.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            yield entry
            if entry.is_dir() and not _is_link(entry):
                stack.append(entry)


def _skill_folders(source: Path) -> dict[str, Path]:
    """{install name: source folder} for every folder that holds a SKILL.md; duplicates refuse."""
    found: dict[str, Path] = {}
    skill_mds = (p for p in _walk_no_links(source) if p.name == "SKILL.md")
    for skill_md in sorted(skill_mds):
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
    for path in sorted(_walk_no_links(folder)):
        if _is_link(path):
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


#: Windows marks symlinks, junctions and every other reparse point with this attribute bit.
_REPARSE_POINT = 0x400


def _is_link(path: Path) -> bool:
    """True for a symlink, and on Windows for a junction or any other reparse point.

    ``Path.is_symlink()`` is False for a junction (checked on this Windows/Python build), and a
    junction used as the install target was written straight through (review of #186). A reparse
    point is treated as a link here, the conservative direction: the tool refuses and says so.
    """
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _REPARSE_POINT)


def _behind_a_link(target_root: Path, path: Path) -> Optional[Path]:
    """The first link on the way from *target_root* (exclusive) down to *path*, if any."""
    current = path
    while current != target_root and target_root in current.parents:
        if _is_link(current):
            return current
        current = current.parent
    return None


def _plan_skill(name: str, src: Path, target_root: Path) -> SkillAction:
    dest = target_root / name
    rels = _files_in(src)
    if _is_link(dest):
        return SkillAction(name, "refused", reason=f"{dest} is a link, not touched")
    for rel in rels:
        link = _behind_a_link(target_root, dest / rel)
        if link is not None:
            return SkillAction(name, "refused", reason=f"{link} is a link, not touched")
    changed = [rel.as_posix() for rel in rels if _differs(src / rel, dest / rel)]
    if not dest.exists():
        return SkillAction(name, "new", changed)
    return SkillAction(name, "updated" if changed else "unchanged", changed)


def _assert_inside(root: Path, target: Path) -> None:
    """Refuse to write *target* unless nothing between *root* and it is a link and it stays inside *root*.

    Checked again here, at write time, not only while planning: a link planted between the plan and
    the write (review of #186, reproduced) would otherwise be followed. The root itself counts: a
    link planted AS the root makes every path below it resolve "inside" it.
    """
    if _is_link(root):
        raise InstallRefusedError(
            f"{root} became a link while installing; refusing to write through it.",
            remediation="Nothing more was written; check what changed the target and run this again.",
        )
    link = _behind_a_link(root, target)
    if link is not None:
        raise InstallRefusedError(
            f"{link} became a link while installing; refusing to write through it.",
            remediation="Nothing more was written; check what changed the target and run this again.",
        )
    resolved_root = root.resolve()
    resolved_parent = target.parent.resolve()
    if (
        resolved_root != resolved_parent
        and resolved_root not in resolved_parent.parents
    ):
        raise InstallRefusedError(
            f"{target} resolves outside {root}; refusing to write it.",
            remediation="Nothing more was written.",
        )


def _write_atomic(source: Path, target: Path, root: Path) -> None:
    _assert_inside(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_inside(root, target)
    if _is_link(target):
        raise InstallRefusedError(
            f"{target} is a link.", remediation="Nothing more was written."
        )
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
        _write_atomic(src / rel, target_root / action.name / rel, target_root)


def _installed_names(target_root: Path) -> list[str]:
    if not target_root.is_dir():
        return []
    names = []
    for entry in sorted(target_root.iterdir()):
        if _is_link(entry) or (entry.is_dir() and (entry / "SKILL.md").is_file()):
            names.append(entry.name)
    return names


def _find_orphans(
    target_root: Path,
    ours: set[str],
    external: frozenset[str],
    retired: frozenset[str],
    extras: frozenset[str] = frozenset(),
) -> list[Orphan]:
    """Everything installed under *target_root* that this install did not just write.

    A name the packaged ``drunken-extras`` plugin ships (*extras*) is never reported here at all —
    not "retired", not "unrecognised" — because ``drunken-install extras`` put it there on
    purpose, and a name can be on ``retired_skills.txt`` *and* shipped today under
    ``drunken-extras`` at the same time (DG-514): "currently shipped elsewhere" must win over "on
    the retired list", the same rule ``install_skills.sh``/``.ps1`` and ``doctor.py`` already
    apply — this was the one place in the Python installer that had never been taught it.
    """
    orphans: list[Orphan] = []
    for name in _installed_names(target_root):
        if name in ours or name in external or name in extras:
            continue
        kind = "retired" if name in retired else "unrecognised"
        note = "link, not touched" if _is_link((target_root / name)) else ""
        orphans.append(Orphan(name, kind, note))
    return orphans


def _prune(target_root: Path, orphans: list[Orphan]) -> list[str]:
    removed: list[str] = []
    for orphan in orphans:
        path = target_root / orphan.name
        if orphan.kind != "retired" or not _plain_name(orphan.name):
            continue
        if _is_link(path) or not path.is_dir():
            continue
        shutil.rmtree(path)
        removed.append(orphan.name)
    return removed


def _sync_index(source: Path, target_root: Path, apply: bool) -> bool:
    src = source / "INDEX.md"
    if not src.is_file():
        return False
    dest = target_root / "INDEX.md"
    if _is_link(dest):
        raise InstallRefusedError(
            f"{dest} is a link.", remediation="Nothing was changed."
        )
    changed = _differs(src, dest)
    if changed and apply:
        _write_atomic(src, dest, target_root)
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
    if _is_link(target_root):
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
        target_root,
        set(folders),
        _external_names(src_root),
        retired_names(),
        _extras_skill_names(),
    )
    if prune and prune_apply and apply:
        result.pruned = _prune(target_root, result.orphans)
    return result


def packaged_agents_dir() -> Path:
    """The agent adapters shipped with this install: the wheel's ``drunken_agents``, else ``agents/``."""
    root = _package_dir("drunken_agents")
    if root is not None:
        return root
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
                    src_root / f"{action.name}.md",
                    target_root / f"{action.name}.md",
                    target_root,
                )
    result.index_updated = _sync_index(src_root, target_root, apply)
    # A name the packaged drunken-extras plugin ships as an agent is not "not shipped" (DG-514) —
    # `drunken-install extras` put it here on purpose, same reasoning as `_find_orphans` above.
    ours = set(_adapter_names(src_root)) | _extras_agent_names()
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
    # DG-512: extras is optional, so it is never folded into up_to_date — a missing extra is
    # expected unless the operator has asked for it.
    extras_changes: list[str] = field(default_factory=list)
    #: How many extras exist and how many are not fully missing (installed, partial or differing).
    #: Reviewer round 2: printing all 31 "missing: <name>" lines on a machine with none of them
    #: installed is noise, not status — a count covers that case, and the per-name lines are kept
    #: for when there is actually something to look at (installed, partial, or differing).
    extras_total: int = 0
    extras_installed: int = 0

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
    """(heading, body) of the first ``## `` section of *text*; a ``## `` inside a code fence is text.

    Empty strings when there is no section.
    """
    heading = ""
    body: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            if heading:
                break
            heading = line[3:].strip()
            continue
        if heading:
            body.append(line)
    return heading, "\n".join(body).strip()


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
    # A name shipped today under plugins/drunken-extras/skills/ is not "retired, still installed"
    # (DG-514) — `drunken-install extras` put it there on purpose, same exclusion `_find_orphans`
    # applies for `install_skills`'s own prune plan.
    extras_skills = _extras_skill_names()
    report.retired_installed = [
        n
        for n in _installed_names(Path(skills_target))
        if n in retired and n not in folders and n not in extras_skills
    ]
    report.changelog_heading, report.changelog_body = newest_changelog_section(
        changelog_text()
    )
    from . import install_extras

    try:
        report.extras_total, report.extras_installed, report.extras_changes = (
            install_extras.extras_overview(skills_target, agents_target)
        )
    except InstallRefusedError:
        pass
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

    ctx = sub.add_parser(
        "context",
        help="print the SessionStart routing context as one JSON object (for a hook's stdout)",
    )
    ctx.add_argument("--target", help="Skills folder. Default: ~/.claude/skills.")
    ctx.add_argument(
        "--agents-target", help="Agents folder. Default: ~/.claude/agents."
    )

    hook = sub.add_parser(
        "hook",
        help=(
            "manage the SessionStart hook ('drunken-install context') and the "
            "UserPromptSubmit hook ('drunken-install route'), merged together"
        ),
    )
    hook.add_argument(
        "--settings", help="Claude settings file. Default: ~/.claude/settings.json."
    )
    hook.add_argument(
        "--apply", action="store_true", help="Write the change. Default: plan only."
    )
    hook.add_argument(
        "--remove",
        action="store_true",
        help="Remove the guild's hook entries instead of adding them.",
    )

    # DG-515: a UserPromptSubmit hook, read a prompt from stdin, print which installed
    # skill/agent to call for it (Thai and English) — or nothing, on no match.
    route = sub.add_parser(
        "route",
        help=(
            "read a UserPromptSubmit JSON from stdin, print a routing nudge naming "
            "installed skills/agents (for a hook's stdout; prints nothing on no match)"
        ),
    )
    route.add_argument("--target", help="Skills folder. Default: ~/.claude/skills.")
    route.add_argument(
        "--agents-target", help="Agents folder. Default: ~/.claude/agents."
    )

    # DG-512: the drunken-extras plugin's optional skills and agents — plan by default, never prunes.
    extras = sub.add_parser(
        "extras",
        help="plan or install the optional drunken-extras skills and agents (plan by default)",
    )
    extras.add_argument("--target", help="Skills folder. Default: ~/.claude/skills.")
    extras.add_argument(
        "--agents-target", help="Agents folder. Default: ~/.claude/agents."
    )
    extras.add_argument(
        "--apply", action="store_true", help="Write the files; the default only plans."
    )
    extras.add_argument(
        "--only", help="Comma-separated names to install; unknown names are refused."
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
    if report.extras_total:
        if report.extras_installed == 0:
            print(
                f"\nextras: {report.extras_total} available, 0 installed "
                "(drunken-install extras --apply)"
            )
        else:
            print("\nextras (optional, drunken-install extras --apply):")
            for line in report.extras_changes:
                print(f"  {line}")
    if report.changelog_heading:
        print(f"\nchangelog — {report.changelog_heading}")
        print(report.changelog_body)
    else:
        print("\nchangelog: not found in this install.")


#: DG-session-routing: a session calls no skill and no agent when nothing at
#: session start tells it to — a project's own ``AGENTS.md`` may be absent (a
#: fresh ``git worktree``), and there is no ``SessionStart`` hook anywhere.
#: ``drunken-install context`` is the fix that depends on neither: it is the
#: command a host's ``SessionStart`` hook runs, and it prints the routing
#: rule plus what this machine actually has installed, so an agent is told
#: once, every session, rather than relying on a file that may not exist or a
#: model that may not remember.
ROUTING_RULE: Final = (
    "Guild routing, read before doing the work yourself: a new project or a "
    "requirement that changed -> run /prd, then /clarify, /ddd, /breakdown, in "
    "that order. A ticket that is ready to build -> run /build, carried out by "
    "the worker agent; its pull request is read by the reviewer agent before "
    "the Boss merges it. Planning or breaking work into tickets -> use the "
    "manager agent. A Jira ticket to write, read or move -> use /jira-tickets. "
    "Git: branch, commit, PR, merge strategy -> use /git-workflow. End of day "
    "or closing a session -> run /audit. Call the skill or agent with the "
    "Skill or Agent tool instead of doing the work yourself. When the project "
    "already has an example of what is asked, follow it and do not ask the "
    "Boss which option to choose."
)

#: The bare command, used only when nothing resolves to an absolute path
#: (:func:`resolve_hook_command`) — a last resort, not the usual case.
GUILD_HOOK_FALLBACK: Final = "drunken-install context"

#: The two program basenames :func:`_is_guild_command` accepts, casefolded.
#: Not a substring/regex match (round 2 of DG-513's review): an unanchored
#: pattern accepted ``evil-drunken-install.exe context`` and
#: ``"not-drunken-install.exe" context`` as our own entry, and the doctor
#: check would then *execute* whatever that command actually was.
_GUILD_PROGRAM_BASENAMES: Final = frozenset({"drunken-install", "drunken-install.exe"})

#: Hard cap on the text handed to a host every single session (REQ/DG-513
#: item 5): the first real measurement on a real machine came to 3,624
#: characters (~900 tokens) with per-item descriptions, and a second plugin's
#: worth of extras would roughly double that. The routing rule itself is
#: never cut; only the installed-names list is, with a marker saying so.
CONTEXT_CHAR_LIMIT: Final = 2500

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _frontmatter(text: str) -> dict[str, str]:
    """``{key: value}`` from a ``SKILL.md``/agent ``.md``'s YAML frontmatter.

    Deliberately not a YAML parser — PyYAML is not a declared runtime
    dependency of this package — just enough to read a flat ``key: value`` or
    a folded (``>``) block scalar, which is every form this repository's own
    files use.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    values: dict[str, str] = {}
    key: Optional[str] = None
    buf: list[str] = []

    def flush() -> None:
        if key is not None:
            values[key] = " ".join(part for part in buf if part).strip()

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line[:1] not in ("", " ", "\t") and ":" in line:
            flush()
            name, _, rest = line.partition(":")
            key = name.strip()
            rest = rest.strip()
            buf = [rest] if rest not in ("", ">", "|", ">-", "|-") else []
        elif key is not None:
            buf.append(line.strip())
    flush()
    return values


def _truncate_sentence(description: str, limit: int = 160) -> str:
    """The first sentence of *description*, hard-capped at *limit* characters.

    The marker is the ASCII ``...``, not U+2026 — the single-character
    ellipsis is dropped by :func:`_scrub`'s ASCII encode, which made a
    truncated description read as merely cut off with no sign it had been
    (DG-513 item 4: the review that found it, by inspection, not a test).
    """
    description = description.strip()
    if not description:
        return ""
    match = _SENTENCE_END.search(description)
    first = description[: match.start() + 1] if match else description
    if len(first) > limit:
        first = first[: limit - 3].rstrip() + "..."
    return first


def _scrub(text: str) -> str:
    """Force ASCII.

    Round 2 of DG-513's review: this used to also strip anything that
    looked like a per-machine home path, but `render_context` has not
    passed a description through here since item 5 switched to
    names-only — nothing it is ever called on can contain one, so that
    half of the function (and its two tests) was asserting against dead
    code. Names alone could in principle be unusual, which is the only
    reason this still exists at all.
    """
    return text.encode("ascii", "ignore").decode("ascii")


def _skill_entries(skills_target: Path) -> list[tuple[str, str]]:
    """{name: first sentence of its description} for every skill actually installed."""
    out: list[tuple[str, str]] = []
    if not skills_target.is_dir():
        return out
    for entry in sorted(skills_target.iterdir()):
        skill_md = entry / "SKILL.md"
        if not entry.is_dir() or not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        description = _frontmatter(text).get("description", "")
        if description:
            out.append((entry.name, _truncate_sentence(description)))
    return out


def _agent_entries(agents_target: Path) -> list[tuple[str, str]]:
    """{name: first sentence of its description} for every agent actually installed."""
    out: list[tuple[str, str]] = []
    if not agents_target.is_dir():
        return out
    for md in sorted(agents_target.glob("*.md")):
        if md.name == "INDEX.md" or not md.is_file():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        description = _frontmatter(text).get("description", "")
        if description:
            out.append((md.stem, _truncate_sentence(description)))
    return out


def _routing_names(skills_target: Path, agents_target: Path) -> list[str]:
    """Every installed skill and agent name, deduplicated, sorted.

    Names only, deliberately (DG-513 item 5): a role such as ``worker``
    installs as both a skill folder (``roles/worker``) and an agent adapter,
    and the fixed routing rule above already names every flow skill and role
    with its own short clause — repeating each one's full description here
    is what made the real measurement 3,624 characters for a single
    machine's worth of skills, before a second plugin's extras even enter.
    """
    try:
        skills = [name for name, _ in _skill_entries(Path(skills_target))]
    except OSError:
        skills = []
    try:
        agents = [name for name, _ in _agent_entries(Path(agents_target))]
    except OSError:
        agents = []
    seen: list[str] = []
    for name in (*skills, *agents):
        if name not in seen:
            seen.append(name)
    return sorted(seen)


def render_context(skills_target: Path, agents_target: Path) -> str:
    """The routing rule, which is never cut, plus a capped list of what is installed.

    Never raises. The names list is truncated before :data:`CONTEXT_CHAR_LIMIT`
    is reached, with a marker saying how many more there are — the routing
    rule itself is built first and is always short enough on its own that
    truncating it is never in question.
    """
    try:
        names = _routing_names(Path(skills_target), Path(agents_target))
    except OSError:
        names = []
    text = ROUTING_RULE
    if names:
        prefix = " Installed: "
        # Reserved unconditionally, not only once a marker turns out to be
        # needed: computing "would this list plus a marker still fit?" after
        # already committing to a longer list is how a cap gets missed by a
        # few characters on the one run that is exactly on the edge.
        marker_reserve = len(" (+9999 more, see drunken-install status)")
        budget = (
            CONTEXT_CHAR_LIMIT - len(text) - len(prefix) - len(".") - marker_reserve
        )
        kept: list[str] = []
        used = 0
        for name in names:
            piece = name if not kept else f", {name}"
            if used + len(piece) > budget:
                break
            kept.append(name)
            used += len(piece)
        remaining = len(names) - len(kept)
        marker = (
            f" (+{remaining} more, see drunken-install status)" if remaining else ""
        )
        text = text + prefix + ", ".join(kept) + marker + "."
    return _scrub(text)


def context_json(skills_target: Path, agents_target: Path) -> str:
    """One JSON object on a line, for a ``SessionStart`` hook's stdout.

    Must never raise and must never be slow: on any error this prints the
    minimal routing rule rather than propagate, because a hook that fails
    noisily at every session start is worse than one that says less.
    """
    try:
        text = render_context(skills_target, agents_target)
    except Exception:  # noqa: BLE001 - a hook's stdout must never be a traceback
        text = ROUTING_RULE
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    try:
        return json.dumps(payload, ensure_ascii=True)
    except (TypeError, ValueError):
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": ROUTING_RULE,
                }
            },
            ensure_ascii=True,
        )


#: DG-515: a ``SessionStart`` hook speaks once, at the top of a session. A later prompt on an
#: existing project — "add a test", "fix this bug", "ทำหน้า login ให้หน่อย" — gets no routing
#: nudge at all: the FINDING measured 0 Skill calls in 24 runs under the guild block, the
#: ``SessionStart`` hook, installed extras and a wider routing table alone. ``drunken-install
#: route`` is the ``UserPromptSubmit`` hook that reads a prompt and says which skill or agent to
#: call before the model starts the work itself.
#:
#: Hard cap, matching ACCEPTANCE: a short nudge, not a second routing rule's worth of text.
ROUTE_PROMPT_CHAR_LIMIT: Final = 600

#: The bare command, used only when nothing resolves to an absolute path — see
#: :func:`resolve_route_hook_command`, the ``route`` twin of :data:`GUILD_HOOK_FALLBACK`.
GUILD_ROUTE_FALLBACK: Final = "drunken-install route"

_ROUTE_PREFIX: Final = (
    "Guild routing for this prompt: before doing the work, call the Skill or Agent tool for "
    "each of: "
)
_ROUTE_SUFFIX: Final = ". Do this first, then follow what it says."


def _route_table_path() -> Path:
    """Where the keyword table lives: the installed package's own copy, else the source tree's.

    One data file, Thai and English, per SCOPE — never duplicated into the router logic itself,
    so adding a keyword or a language never touches this module.
    """
    packaged = importlib_resources.files("core").joinpath("data/route_keywords.json")
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    return _SOURCE_TREE / "src" / "core" / "data" / "route_keywords.json"


def _load_route_table() -> list[dict[str, Any]]:
    """The keyword table as ``[{"category", "keywords", "names"}, ...]``.

    Never raises: a missing or malformed table is read as "no rows", the same "say less, not
    wrong" reasoning :func:`context_json` already applies to the SessionStart hook.
    """
    try:
        text = _route_table_path().read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


#: A Latin keyword this short is a real word on its own ("ui", "ux", "api", "pr") and a
#: substring of something unrelated often enough to misfire as a bare `in` check — "build"
#: contains "ui", "required" contains "ui", "rapid" contains "api", "print"/"approve" contain
#: "pr" (DG-515 follow-up, found by the lead running the built exe against real prompts). Above
#: this length a Latin keyword is treated as a phrase and a plain substring check is kept.
_WORD_BOUNDARY_MAX_LEN: Final = 3

#: Thai combining tone marks (ไม้เอก ไม้โท ไม้ตรี ไม้จัตวา) — stripped from both the keyword
#: table and the prompt before comparing, so a real user's "บั๊ก" and this table's "บัก" compare
#: equal (DG-515 follow-up item 3) instead of silently missing each other.
_THAI_TONE_MARKS: Final = str.maketrans("", "", "่้๊๋")

_WORD_BOUNDARY_CHARS = "a-z0-9"


def _normalize_for_match(text: str) -> str:
    """Lowercase (so ASCII matching is case-insensitive) with Thai tone marks stripped (so a
    tone-mark spelling variant compares equal) — applied to the prompt once, and to each
    keyword before comparing against it."""
    return text.lower().translate(_THAI_TONE_MARKS)


def _keyword_hits(keyword: str, normalized_prompt: str) -> bool:
    """Does *keyword* appear in *normalized_prompt* (already run through
    :func:`_normalize_for_match`)? A short, bare Latin keyword matches only on a word boundary;
    everything else — a longer Latin phrase, any Thai keyword — stays a plain substring check,
    since Thai has no word-boundary convention to anchor on."""
    normalized_keyword = _normalize_for_match(keyword)
    compact = normalized_keyword.replace(" ", "")
    if (
        compact.isascii()
        and compact.isalnum()
        and len(compact) <= _WORD_BOUNDARY_MAX_LEN
    ):
        pattern = (
            f"(?<![{_WORD_BOUNDARY_CHARS}])"
            + re.escape(normalized_keyword)
            + f"(?![{_WORD_BOUNDARY_CHARS}])"
        )
        return re.search(pattern, normalized_prompt) is not None
    return normalized_keyword in normalized_prompt


def _matched_names(prompt: str, table: list[dict[str, Any]]) -> list[str]:
    """Every candidate skill/agent name whose row's keyword appears in *prompt*, in table order,
    deduplicated — before the installed-only filter is applied."""
    normalized_prompt = _normalize_for_match(prompt)
    names: list[str] = []
    for row in table:
        keywords = row.get("keywords")
        row_names = row.get("names")
        if not isinstance(keywords, list) or not isinstance(row_names, list):
            continue
        if not any(
            isinstance(k, str) and _keyword_hits(k, normalized_prompt) for k in keywords
        ):
            continue
        for name in row_names:
            if isinstance(name, str) and name not in names:
                names.append(name)
    return names


def route_text(prompt: str, skills_target: Path, agents_target: Path) -> str:
    """The short routing nudge for *prompt*, or ``""`` for no match.

    Only ever names a skill or agent actually installed under *skills_target*/*agents_target*
    (ACCEPTANCE: "names of uninstalled skills are never emitted") and is hard-capped at
    :data:`ROUTE_PROMPT_CHAR_LIMIT` characters by trimming names, never by cutting mid-sentence.
    """
    if not isinstance(prompt, str) or not prompt:
        return ""
    candidates = _matched_names(prompt, _load_route_table())
    if not candidates:
        return ""
    try:
        installed = set(_routing_names(Path(skills_target), Path(agents_target)))
    except OSError:
        installed = set()
    names = [n for n in candidates if n in installed]
    if not names:
        return ""
    while names:
        text = _ROUTE_PREFIX + ", ".join(names) + _ROUTE_SUFFIX
        if len(text) <= ROUTE_PROMPT_CHAR_LIMIT:
            return text
        names.pop()
    return ""


def route_json(prompt: str, skills_target: Path, agents_target: Path) -> str:
    """One JSON object (the ``UserPromptSubmit`` hook shape), or ``""`` to print nothing.

    Never raises: a hook's stdout must never be a traceback, the same rule :func:`context_json`
    follows for ``SessionStart``.
    """
    try:
        text = route_text(prompt, skills_target, agents_target)
    except Exception:  # noqa: BLE001 - a hook's stdout must never be a traceback
        return ""
    if not text:
        return ""
    try:
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": text,
                }
            },
            ensure_ascii=True,
        )
    except (TypeError, ValueError):
        return ""


@dataclass
class HookPlan:
    """What ``drunken-install hook`` found, and what it would do about it."""

    settings_path: Path
    action: str  # "add" | "already-present" | "remove" | "not-present" | "refused"
    reason: str = ""
    #: The command that would be written (for "add"), or the one already
    #: there (for "already-present"/"remove"). Empty for "not-present"/"refused".
    command: str = ""
    #: False only for "add" when nothing resolved to an absolute path and
    #: *command* is the bare :data:`GUILD_HOOK_FALLBACK` instead (DG-513 item
    #: 1) — true otherwise, including when nothing is being added at all.
    resolved: bool = True


def default_settings_path() -> Path:
    """``~/.claude/settings.json`` — the same home resolution as :func:`default_target`."""
    return default_target().parent / "settings.json"


def _quote_path_for_command(path: str) -> str:
    """*path* as one token, always double-quoted.

    Not "only when it has a space": a bare, unquoted Windows path fed back
    through :func:`_split_hook_command`'s ``shlex.split(..., posix=True)``
    has every backslash treated as an escape character and stripped —
    found by the doctor check's own end-to-end test failing on exactly the
    no-spaces-in-the-path case, the common one. Quoting unconditionally
    means parsing it back is the one case already proven to round-trip.
    """
    if os.name == "nt":
        return f'"{path}"'
    return shlex.quote(path)


#: The two basenames a ``drunken-install`` program may legitimately have,
#: compared casefolded — see :func:`_running_drunken_install`.
_DRUNKEN_INSTALL_NAMES: Final = ("drunken-install", "drunken-install.exe")


def _running_drunken_install() -> Optional[str]:
    """``sys.argv[0]``, if this process IS a ``drunken-install`` run (DG-514 blocker B).

    Confirmed by reproduction, both through a plain ``uv tool install`` and through a fresh venv
    built from a release-candidate wheel: a Windows console-script launcher's ``sys.argv[0]`` is
    the path the launcher was actually invoked as — not ``sys.executable`` (that is always the
    venv's own ``python.exe``, embedded in the launcher at install time) — but with the ``.exe``
    suffix stripped relative to the file that is actually on disk. ``os.path.isfile(argv[0])`` is
    therefore False for the bare name and True only once ``.exe`` is appended back; both forms are
    tried here before giving up on this candidate. On a non-Windows launcher argv[0] already
    matches the real file, so the plain form alone succeeds there.

    Deliberately ``os.path``, never ``pathlib.Path``: a test exercising this module's Windows
    formatting monkeypatches ``os.name`` to ``"nt"`` while actually running on POSIX (there is no
    other way to exercise that branch on a POSIX CI runner) — ``pathlib.Path()`` reads ``os.name``
    at *construction* time and raises ``NotImplementedError`` building a ``WindowsPath`` on a real
    POSIX system, while ``os.path`` stays bound to the real platform's implementation, decided
    once when ``os`` itself was imported.
    """
    if not sys.argv or not sys.argv[0]:
        return None
    raw = sys.argv[0]
    candidates = [raw]
    if os.name == "nt" and not raw.casefold().endswith(".exe"):
        candidates.append(raw + ".exe")
    for candidate in candidates:
        basename = os.path.basename(candidate).casefold()
        if basename in _DRUNKEN_INSTALL_NAMES and os.path.isfile(candidate):
            # Absolute: the hook runs later from another cwd (DG-514 review).
            return os.path.abspath(candidate)
    return None


def resolve_hook_command() -> tuple[str, bool]:
    """The command the SessionStart hook should run, and whether it resolved.

    DG-513 item 1: the bare command ``drunken-install context`` fails
    *silently* when the directory running the hook does not have it on
    PATH — exit 127, no context, no visible error, the exact failure mode
    this feature exists to end. An absolute path removes PATH from the
    question entirely.

    Tried in order (DG-514 blocker B changed this order — see
    :func:`_running_drunken_install`'s docstring for the reproduction that found it):

    1. **The installation actually running this call** — confirmed by reproduction to be the one
       that matters: running ``drunken-install hook --apply`` from a venv's own executable
       recorded a DIFFERENT, older installation that merely happened to be first on PATH, because
       ``shutil.which`` used to be tried first. Whoever is running the hook setup is who the hook
       should run later.
    2. **The console script that should sit next to the running interpreter** (covers a venv
       whose ``Scripts``/``bin`` is not on PATH — exactly how a project's own ``.venv`` is
       normally *not* on PATH, and argv[0] does not help there since it is often just the bare
       command name typed on a shell already on PATH).
    3. ``drunken-install`` on PATH (covers a ``uv tool install`` reached some other way — a shim,
       a symlink, anything argv[0]/sys.executable did not already resolve).

    The bare fallback is returned, with ``resolved=False``, only when none of the three exist;
    the caller is responsible for surfacing that.
    """
    return _resolve_drunken_install_command("context", GUILD_HOOK_FALLBACK)


def _resolve_drunken_install_command(
    subcommand: str, fallback: str
) -> tuple[str, bool]:
    """The shared three-tier search behind :func:`resolve_hook_command` and
    :func:`resolve_route_hook_command` (DG-515) — only the trailing subcommand and the bare
    fallback differ between a ``SessionStart`` hook and a ``UserPromptSubmit`` one."""
    found = _running_drunken_install()
    if not found:
        # os.path, not pathlib.Path -- see _running_drunken_install's docstring for why.
        name = "drunken-install.exe" if os.name == "nt" else "drunken-install"
        candidate = os.path.abspath(os.path.join(os.path.dirname(sys.executable), name))
        if os.path.isfile(candidate):
            found = candidate
    if not found:
        found = shutil.which("drunken-install")
    if found:
        return f"{_quote_path_for_command(found)} {subcommand}", True
    return fallback, False


def resolve_route_hook_command() -> tuple[str, bool]:
    """The command the UserPromptSubmit (``route``) hook should run, and whether it resolved.

    The ``route`` twin of :func:`resolve_hook_command` (DG-515) — same reasoning, same
    three-tier search, through :func:`_resolve_drunken_install_command`.
    """
    return _resolve_drunken_install_command("route", GUILD_ROUTE_FALLBACK)


def _load_settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise InstallRefusedError(
            f"{path} is not valid JSON: {exc}",
            remediation="Fix the file by hand; nothing here was changed.",
        ) from exc
    if not isinstance(data, dict):
        raise InstallRefusedError(
            f"{path} must contain a JSON object at the top level.",
            remediation="Nothing here was changed.",
        )
    hooks = data.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise InstallRefusedError(
            f"{path}: 'hooks' is not an object.",
            remediation="Fix 'hooks' by hand; nothing here was changed.",
        )
    return data


def _is_guild_command(command: Any) -> bool:
    """Is *command* exactly ``<drunken-install> context`` — nothing else?

    Exactly two tokens after splitting (:func:`_split_hook_command`, the
    same splitter :func:`verify_hook_command` runs it through): a program
    whose basename, casefolded, is ``drunken-install`` or
    ``drunken-install.exe``, and a second token that is exactly
    ``"context"``. Anything with extra arguments, a shell operator as a
    literal token, or a program name that merely *contains* ``drunken-
    install`` is not ours — identification, not execution-time trust; see
    :func:`is_trusted_hook_command` for the second layer.
    """
    if not isinstance(command, str):
        return False
    try:
        argv = _split_hook_command(command)
    except ValueError:
        return False
    if len(argv) != 2 or argv[1] != "context":
        return False
    return Path(argv[0]).name.casefold() in _GUILD_PROGRAM_BASENAMES


def _is_guild_entry(hook_entry: Any) -> bool:
    if not isinstance(hook_entry, dict):
        return False
    return any(
        isinstance(h, dict) and _is_guild_command(h.get("command"))
        for h in hook_entry.get("hooks") or []
    )


def _guild_command_in(settings: dict[str, Any]) -> Optional[str]:
    """The command of the guild's own SessionStart entry, if one is there."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return None
    session_start = hooks.get("SessionStart")
    if not isinstance(session_start, list):
        return None
    for entry in session_start:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks") or []:
            if isinstance(h, dict) and _is_guild_command(h.get("command")):
                return str(h.get("command"))
    return None


def _is_guild_route_command(command: Any) -> bool:
    """The ``UserPromptSubmit`` twin of :func:`_is_guild_command`: exactly
    ``<drunken-install> route`` — nothing else. Same reasoning, same two-token shape, swapping
    only the trailing subcommand."""
    if not isinstance(command, str):
        return False
    try:
        argv = _split_hook_command(command)
    except ValueError:
        return False
    if len(argv) != 2 or argv[1] != "route":
        return False
    return Path(argv[0]).name.casefold() in _GUILD_PROGRAM_BASENAMES


def _is_guild_route_entry(hook_entry: Any) -> bool:
    if not isinstance(hook_entry, dict):
        return False
    return any(
        isinstance(h, dict) and _is_guild_route_command(h.get("command"))
        for h in hook_entry.get("hooks") or []
    )


def _guild_route_command_in(settings: dict[str, Any]) -> Optional[str]:
    """The command of the guild's own UserPromptSubmit entry, if one is there."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return None
    prompt_submit = hooks.get("UserPromptSubmit")
    if not isinstance(prompt_submit, list):
        return None
    for entry in prompt_submit:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks") or []:
            if isinstance(h, dict) and _is_guild_route_command(h.get("command")):
                return str(h.get("command"))
    return None


def _unresolved_warning() -> str:
    return (
        "could not resolve an absolute path to drunken-install; using the bare "
        "command, which fails silently (no context, no visible error) if it is "
        "not on PATH when the hook runs"
    )


#: ``()`` -> ``(command, resolved)`` — the shape of :func:`resolve_hook_command` and
#: :func:`resolve_route_hook_command`.
_Resolver = Callable[[], tuple[str, bool]]
#: ``settings`` -> the guild's own command in some event array, if present — the shape of
#: :func:`_guild_command_in` and :func:`_guild_route_command_in`.
_FindCommand = Callable[[dict[str, Any]], Optional[str]]


def _plan_add(
    settings_path: Path,
    *,
    file_will_be_created: bool,
    resolver: _Resolver = resolve_hook_command,
) -> HookPlan:
    command, resolved = resolver()
    notes = []
    if file_will_be_created:
        notes.append("the settings file does not exist yet; it would be created")
    if not resolved:
        notes.append(_unresolved_warning())
    return HookPlan(
        settings_path, "add", reason=" ".join(notes), command=command, resolved=resolved
    )


def _plan_hook_generic(
    settings_path: Path,
    *,
    remove: bool,
    find_command: _FindCommand,
    resolver: _Resolver,
) -> HookPlan:
    """Shared shape behind :func:`plan_hook` (SessionStart) and :func:`plan_route_hook`
    (UserPromptSubmit) — DG-515: the second event needs exactly the same plan-first, read-only
    reasoning the first one already has, so this is the one place it is written."""
    settings_path = Path(settings_path)
    if not settings_path.is_file():
        if remove:
            return HookPlan(settings_path, "not-present")
        return _plan_add(settings_path, file_will_be_created=True, resolver=resolver)
    try:
        settings = _load_settings(settings_path)
    except InstallRefusedError as exc:
        return HookPlan(settings_path, "refused", str(exc))
    existing = find_command(settings)
    if remove:
        return HookPlan(
            settings_path,
            "remove" if existing else "not-present",
            command=existing or "",
        )
    if existing:
        return HookPlan(settings_path, "already-present", command=existing)
    return _plan_add(settings_path, file_will_be_created=False, resolver=resolver)


def plan_hook(settings_path: Path, *, remove: bool = False) -> HookPlan:
    """What applying (or removing) the guild's SessionStart hook would do. Read-only."""
    return _plan_hook_generic(
        settings_path,
        remove=remove,
        find_command=_guild_command_in,
        resolver=resolve_hook_command,
    )


def plan_route_hook(settings_path: Path, *, remove: bool = False) -> HookPlan:
    """What applying (or removing) the guild's UserPromptSubmit (``route``) hook would do.
    Read-only — the ``route`` twin of :func:`plan_hook` (DG-515)."""
    return _plan_hook_generic(
        settings_path,
        remove=remove,
        find_command=_guild_route_command_in,
        resolver=resolve_route_hook_command,
    )


def _merge_add(settings: dict[str, Any], command: str) -> dict[str, Any]:
    new_settings = dict(settings)
    hooks = dict(settings.get("hooks") or {})
    session_start = list(hooks.get("SessionStart") or [])
    session_start.append(
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": command}],
        }
    )
    hooks["SessionStart"] = session_start
    new_settings["hooks"] = hooks
    return new_settings


def _merge_remove(settings: dict[str, Any]) -> dict[str, Any]:
    new_settings = dict(settings)
    hooks = dict(settings.get("hooks") or {})
    session_start = [
        e for e in (hooks.get("SessionStart") or []) if not _is_guild_entry(e)
    ]
    if session_start:
        hooks["SessionStart"] = session_start
    else:
        hooks.pop("SessionStart", None)
    if hooks:
        new_settings["hooks"] = hooks
    else:
        new_settings.pop("hooks", None)
    return new_settings


def _merge_add_route(settings: dict[str, Any], command: str) -> dict[str, Any]:
    """The ``route`` twin of :func:`_merge_add` — same shape, the ``UserPromptSubmit`` array
    (DG-515)."""
    new_settings = dict(settings)
    hooks = dict(settings.get("hooks") or {})
    prompt_submit = list(hooks.get("UserPromptSubmit") or [])
    prompt_submit.append(
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": command}],
        }
    )
    hooks["UserPromptSubmit"] = prompt_submit
    new_settings["hooks"] = hooks
    return new_settings


def _merge_remove_route(settings: dict[str, Any]) -> dict[str, Any]:
    """The ``route`` twin of :func:`_merge_remove`."""
    new_settings = dict(settings)
    hooks = dict(settings.get("hooks") or {})
    prompt_submit = [
        e for e in (hooks.get("UserPromptSubmit") or []) if not _is_guild_route_entry(e)
    ]
    if prompt_submit:
        hooks["UserPromptSubmit"] = prompt_submit
    else:
        hooks.pop("UserPromptSubmit", None)
    if hooks:
        new_settings["hooks"] = hooks
    else:
        new_settings.pop("hooks", None)
    return new_settings


def _backup(path: Path) -> Path:
    """Copy *path* to a sibling ``<name>.bak-<UTC stamp>``, created exclusively."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = 0
    while True:
        name = f"{path.name}.bak-{stamp}" + (f"-{suffix}" if suffix else "")
        candidate = path.with_name(name)
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            suffix += 1
            continue
        break
    with os.fdopen(fd, "wb") as handle:
        handle.write(path.read_bytes())
    return candidate


def _write_json_atomic(path: Path, data: dict[str, Any], root: Path) -> None:
    _assert_inside(root, path)
    if _is_link(path):
        raise InstallRefusedError(
            f"{path} is a link.", remediation="Nothing was written."
        )
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".drunken-install-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


#: ``(settings_path, remove=...)`` -> plan — the shape of :func:`plan_hook` and
#: :func:`plan_route_hook`.
_PlanFn = Callable[..., HookPlan]
#: ``(settings, command)`` -> new settings — the shape of :func:`_merge_add` and
#: :func:`_merge_add_route`.
_MergeAdd = Callable[[dict[str, Any], str], dict[str, Any]]
#: ``(settings)`` -> new settings — the shape of :func:`_merge_remove` and
#: :func:`_merge_remove_route`.
_MergeRemove = Callable[[dict[str, Any]], dict[str, Any]]


def _apply_hook_generic(
    settings_path: Path,
    *,
    apply: bool,
    remove: bool,
    plan_fn: _PlanFn,
    merge_add: _MergeAdd,
    merge_remove: _MergeRemove,
) -> HookPlan:
    """Shared shape behind :func:`apply_hook` (SessionStart) and :func:`apply_route_hook`
    (UserPromptSubmit) — DG-515, same safety as the SessionStart merge (plan first, backup,
    idempotent, abort on a concurrent edit) for the second event too, written once."""
    settings_path = Path(settings_path)
    plan = plan_fn(settings_path, remove=remove)
    if plan.action == "refused":
        if apply:
            raise InstallRefusedError(plan.reason, remediation="Nothing was changed.")
        return plan
    if not apply or plan.action in ("already-present", "not-present"):
        return plan

    root = settings_path.parent
    if _is_link(settings_path) or _is_link(root):
        raise InstallRefusedError(
            f"{settings_path} sits behind a link.",
            remediation="Nothing was changed.",
        )
    existed = settings_path.is_file()
    original_bytes = settings_path.read_bytes() if existed else None
    settings = _load_settings(settings_path) if existed else {}
    root.mkdir(parents=True, exist_ok=True)
    if existed:
        _backup(settings_path)
    new_settings = (
        merge_remove(settings) if remove else merge_add(settings, plan.command)
    )
    if existed:
        # DG-513 item 6: re-read immediately before writing, not only once at
        # the top — a second writer between the first read and now must
        # abort rather than have its edit silently overwritten. NTFS ACL
        # entries set directly on this file are not preserved across the
        # atomic replace below; see GETTING_STARTED.md.
        current_bytes = settings_path.read_bytes() if settings_path.is_file() else None
        if current_bytes != original_bytes:
            raise InstallRefusedError(
                f"{settings_path} changed on disk since it was read; "
                "refusing to overwrite a concurrent edit.",
                remediation="Nothing was written. Run this again.",
            )
    _write_json_atomic(settings_path, new_settings, root)
    return plan


def apply_hook(
    settings_path: Path, *, apply: bool = False, remove: bool = False
) -> HookPlan:
    """Plan (``apply=False``) or perform adding/removing the guild's SessionStart hook."""
    return _apply_hook_generic(
        settings_path,
        apply=apply,
        remove=remove,
        plan_fn=plan_hook,
        merge_add=_merge_add,
        merge_remove=_merge_remove,
    )


def apply_route_hook(
    settings_path: Path, *, apply: bool = False, remove: bool = False
) -> HookPlan:
    """Plan (``apply=False``) or perform adding/removing the guild's UserPromptSubmit
    (``route``) hook. The ``route`` twin of :func:`apply_hook` (DG-515)."""
    return _apply_hook_generic(
        settings_path,
        apply=apply,
        remove=remove,
        plan_fn=plan_route_hook,
        merge_add=_merge_add_route,
        merge_remove=_merge_remove_route,
    )


def _split_hook_command(command: str) -> list[str]:
    """``[program, *args]`` for a command this tool itself generated.

    ``shlex.split(..., posix=True)`` is used deliberately *always*, even on
    Windows: it strips the double quotes :func:`resolve_hook_command` wraps
    an absolute path in, and a bare backslash in a Windows path (``C:\\Users
    \\...``) is not a POSIX escape character unless it precedes a quote or
    another backslash, so a plain path survives unchanged. ``posix=False``
    was tried first and rejected — it leaves the quote characters inside the
    token, which breaks the quoted-path case this exists for.
    """
    try:
        return shlex.split(command.strip(), posix=True)
    except ValueError:
        # An unterminated quote, say — fall back to the crudest possible
        # split rather than raise out of a doctor check.
        return command.split()


def _real_path(raw: str) -> str:
    """A path's canonical form for comparing two commands' programs.

    ``os.path.normcase`` lower-cases on Windows (filesystem paths there are
    case-insensitive) and is a no-op on POSIX; ``os.path.realpath`` resolves
    ``..``/symlinks. Comparing this, not the raw strings, is what makes two
    different-looking paths to the same file compare equal — and two
    same-named files in different directories compare *unequal*, which is
    the whole point.
    """
    return os.path.normcase(os.path.realpath(raw))


def is_trusted_hook_command(command: str) -> bool:
    """Does *command*'s program resolve to **this installation's own**
    ``drunken-install`` — not merely a file of the right name?

    DG-513 round 2, layer (b): identification (:func:`_is_guild_command`)
    only checks the *shape* of the command — a program named exactly
    ``drunken-install.exe`` sitting in an attacker-controlled directory
    passes it. This is the check the doctor runs before actually executing
    anything: the program must resolve to the same file as what
    :func:`resolve_hook_command` would produce right now, or to
    ``shutil.which("drunken-install")`` — both describe *this machine's*
    real installation, never the command recorded in a settings file.
    """
    argv = _split_hook_command(command)
    if not argv:
        return False
    candidate = _real_path(argv[0])

    current_command, resolved = resolve_hook_command()
    if resolved:
        current_argv = _split_hook_command(current_command)
        if current_argv and _real_path(current_argv[0]) == candidate:
            return True

    found = shutil.which("drunken-install")
    if found and _real_path(found) == candidate:
        return True
    return False


def is_trusted_route_hook_command(command: str) -> bool:
    """The ``route`` twin of :func:`is_trusted_hook_command` (DG-515) — same reasoning, checked
    against :func:`resolve_route_hook_command` instead."""
    argv = _split_hook_command(command)
    if not argv:
        return False
    candidate = _real_path(argv[0])

    current_command, resolved = resolve_route_hook_command()
    if resolved:
        current_argv = _split_hook_command(current_command)
        if current_argv and _real_path(current_argv[0]) == candidate:
            return True

    found = shutil.which("drunken-install")
    if found and _real_path(found) == candidate:
        return True
    return False


def verify_hook_command(command: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    """Actually run *command* and check it behaves like our own hook (DG-513 item 1).

    Presence of an entry in ``settings.json`` is not the same as it working:
    the recorded program can be missing (uninstalled, moved, a stale venv),
    or too old to have the ``context`` subcommand at all. Both fail with no
    visible error at session start, which is exactly the silent failure this
    whole feature exists to end — so the doctor runs the real command,
    briefly, rather than trust the file.
    """
    if not command:
        return False, "no command is configured"
    argv = _split_hook_command(command)
    if not argv or not argv[0]:
        return False, "the configured command has no program to run"
    try:
        proc = subprocess.run(  # nosec B603 - no shell, argv built above, fixed tail
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        return (
            False,
            f"{argv[0]!r} was not found (not on PATH, or moved since it was recorded)",
        )
    except subprocess.TimeoutExpired:
        return False, f"did not finish within {timeout}s"
    except OSError as exc:
        return False, f"could not be run: {exc}"
    if proc.returncode != 0:
        return False, (
            f"exited with code {proc.returncode} (an older drunken-install without "
            "'context', perhaps)"
        )
    try:
        payload = json.loads(proc.stdout)
        event = payload["hookSpecificOutput"]["hookEventName"]
    except (ValueError, KeyError, TypeError):
        return False, "ran, but did not print the expected SessionStart JSON"
    if event != "SessionStart":
        return False, "ran, but hookEventName was not 'SessionStart'"
    return True, ""


#: A prompt guaranteed to match the ``git`` row of the shipped keyword table (DG-515): any
#: core install always ships the `git-workflow` skill, so a working ``route`` command must
#: print the UserPromptSubmit JSON naming it for this prompt — "no match" would mean broken,
#: not quiet, for this specific probe.
_ROUTE_PROBE_PROMPT: Final = "please help with this git commit and open a pull request"


def verify_route_hook_command(
    command: str, *, timeout: float = 5.0
) -> tuple[bool, str]:
    """Actually run *command* with a known-to-match prompt on stdin and check it behaves like
    our own ``route`` hook (the ``route`` twin of :func:`verify_hook_command`, DG-515).

    Presence in ``settings.json`` is not the same as it working, same reasoning as the
    SessionStart check: the recorded program can be missing, moved, or too old to have the
    ``route`` subcommand at all — and an empty stdout is ambiguous between "no match" (by
    design) and "broken", so this sends a prompt the shipped table always matches
    (``git-workflow`` is a core skill, never optional) and insists on real output.
    """
    if not command:
        return False, "no command is configured"
    argv = _split_hook_command(command)
    if not argv or not argv[0]:
        return False, "the configured command has no program to run"
    probe = json.dumps({"prompt": _ROUTE_PROBE_PROMPT})
    try:
        proc = subprocess.run(  # nosec B603 - no shell, argv built above, fixed tail
            argv,
            input=probe,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        return (
            False,
            f"{argv[0]!r} was not found (not on PATH, or moved since it was recorded)",
        )
    except subprocess.TimeoutExpired:
        return False, f"did not finish within {timeout}s"
    except OSError as exc:
        return False, f"could not be run: {exc}"
    if proc.returncode != 0:
        return False, (
            f"exited with code {proc.returncode} (an older drunken-install without "
            "'route', perhaps)"
        )
    out = proc.stdout.strip()
    if not out:
        return (
            False,
            "ran, but printed nothing for a prompt the shipped table always matches",
        )
    try:
        payload = json.loads(out)
        event = payload["hookSpecificOutput"]["hookEventName"]
    except (ValueError, KeyError, TypeError):
        return False, "ran, but did not print the expected UserPromptSubmit JSON"
    if event != "UserPromptSubmit":
        return False, "ran, but hookEventName was not 'UserPromptSubmit'"
    return True, ""


def _print_hook_plan(
    plan: HookPlan,
    *,
    apply: bool,
    event: str = "SessionStart",
    fallback: str = GUILD_HOOK_FALLBACK,
    print_settings_line: bool = True,
) -> None:
    if print_settings_line:
        print(f"settings : {plan.settings_path}")
    labels = {
        "add": "would add" if not apply else "added",
        "already-present": "already present",
        "remove": "would remove" if not apply else "removed",
        "not-present": "not present (nothing to remove)",
        "refused": f"refused — {plan.reason}",
    }
    command = plan.command or fallback
    print(f"{event} hook ({command}): {labels[plan.action]}")
    if plan.action == "add" and not plan.resolved:
        print(f"  WARNING: {_unresolved_warning()}")
    elif plan.action == "add" and plan.reason and not apply:
        print(f"  {plan.reason}")
    if not apply and plan.action in ("add", "remove"):
        print("dry run  : nothing was written. Add --apply to write it.")


def _run_context(args: argparse.Namespace) -> int:
    try:
        skills_target, agents_target = _targets(args)
        print(context_json(skills_target, agents_target))
    except Exception:  # noqa: BLE001 - a hook's stdout must never be a traceback
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": ROUTING_RULE,
                    }
                },
                ensure_ascii=True,
            )
        )
    return 0


def _run_hook(args: argparse.Namespace) -> int:
    """``drunken-install hook``: the SessionStart hook (``context``) and the UserPromptSubmit
    hook (``route``) are merged together by one ``--apply``/``--remove`` — one settings file,
    one command, same plan-first/backup/idempotent safety for both (DG-515 SCOPE: "hook --apply
    also merges the UserPromptSubmit entry")."""
    settings_path = (
        Path(args.settings).expanduser() if args.settings else default_settings_path()
    )
    session_plan = apply_hook(settings_path, apply=args.apply, remove=args.remove)
    _print_hook_plan(
        session_plan,
        apply=args.apply,
        event="SessionStart",
        fallback=GUILD_HOOK_FALLBACK,
    )
    route_plan = apply_route_hook(settings_path, apply=args.apply, remove=args.remove)
    _print_hook_plan(
        route_plan,
        apply=args.apply,
        event="UserPromptSubmit",
        fallback=GUILD_ROUTE_FALLBACK,
        print_settings_line=False,
    )
    return 1 if "refused" in (session_plan.action, route_plan.action) else 0


def _prompt_from_stdin() -> str:
    """The ``"prompt"`` field of a UserPromptSubmit JSON payload on stdin, or ``""`` for
    anything that is not exactly that — malformed JSON, no stdin, the wrong shape."""
    try:
        raw = sys.stdin.read()
        payload_in = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 - a hook's stdout must never be a traceback
        return ""
    if not isinstance(payload_in, dict):
        return ""
    candidate = payload_in.get("prompt", "")
    return candidate if isinstance(candidate, str) else ""


def _run_route(args: argparse.Namespace) -> int:
    skills_target, agents_target = _targets(args)
    out = route_json(_prompt_from_stdin(), skills_target, agents_target)
    if out:
        print(out)
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.what == "context":
        return _run_context(args)
    if args.what == "hook":
        return _run_hook(args)
    if args.what == "route":
        return _run_route(args)
    skills_target, agents_target = _targets(args)
    if args.what == "status":
        _print_status(status(skills_target, agents_target))
        return 0
    if args.what == "extras":
        from . import install_extras

        only = (
            [n.strip() for n in args.only.split(",") if n.strip()]
            if args.only
            else None
        )
        extras_result = install_extras.install_extras(
            skills_target, agents_target, apply=args.apply, only=only
        )
        install_extras.print_report(extras_result)
        return (
            1
            if any(
                a.status == "refused"
                for a in (*extras_result.skills, *extras_result.agents)
            )
            else 0
        )
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
