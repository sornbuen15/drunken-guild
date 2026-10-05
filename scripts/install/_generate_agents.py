#!/usr/bin/env python3
"""Generate agents/<role>.md from skills/roles/<role>/SKILL.md + agents/_sources.json.

DG-402. Roles (manager, worker, reviewer) are written once, as skills, under
``skills/roles/``. ``agents/<role>.md`` is a *generated* adapter: Claude Code's own
subagent frontmatter supports a ``skills:`` field that preloads the named skill's
full content into the subagent's context at startup
(https://code.claude.com/docs/en/subagents — "Skills to preload into the subagent's
context at startup. The full skill content is injected, not only the description.").
That is the mechanism this generator relies on: the adapter carries the
Claude-specific plumbing (``model``, ``tools``, ``skills:``) and nothing else, so the
role's own rules live in exactly one place.

No PyYAML, deliberately — this runs under the bare system ``python3`` an operator's
machine has, the same contract ``_truncate.py`` already relies on (see its own
docstring), not the project's own `uv` environment. ``agents/_sources.json`` is read
with the standard library's ``json`` module; each skill's frontmatter is parsed with
the same small hand-written scan ``_truncate.py``'s siblings use elsewhere in this
project, not a YAML parser.

Byte-determinism is the whole point of a generated-and-committed file (DG-280,
DG-378, DG-380): UTF-8, no BOM, LF only, no trailing whitespace on any line, exactly
one trailing newline. Both ``install_agents.sh`` and ``install_agents.ps1`` call this
one script rather than re-implementing the generation twice, which is what let the
two platform installers disagree before.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_DESC_INLINE = re.compile(r"^description:\s*(.*)$")
_DESC_BLOCK_START = re.compile(r"^description:\s*[>|]")


def skill_description(skill_md: Path) -> str:
    """The frontmatter ``description:`` field of a ``SKILL.md``, folded to one line.

    Handles a plain inline value and a YAML block scalar (``>`` or ``|``) indented on
    the lines that follow — the only two shapes any skill in this repository uses.
    Multi-line block scalars are joined with a single space, mirroring how the
    folded description reads in prose.

    Read with ``utf-8-sig``, not ``utf-8`` (DG-402 review, LOW): a leading BOM is
    invisible in most editors and some tools write one by default on Windows, and
    with plain ``utf-8`` it survives as a ``\\ufeff`` character glued onto ``---``,
    so ``text.startswith("---")`` below is false and a BOM-prefixed file refused
    outright rather than being read. ``utf-8-sig`` strips a BOM if present and is
    otherwise identical to ``utf-8``, so a file with no BOM is read exactly the same
    either way.
    """
    text = skill_md.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        raise ValueError(f"{skill_md}: no frontmatter delimiter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{skill_md}: frontmatter is not closed")

    lines = parts[1].splitlines()
    collecting = False
    collected: list[str] = []
    for line in lines:
        if collecting:
            if line.strip() and (line.startswith(" ") or line.startswith("\t")):
                collected.append(line.strip())
                continue
            break
        if _DESC_BLOCK_START.match(line.strip()):
            collecting = True
            continue
        match = _DESC_INLINE.match(line.strip())
        if match and match.group(1):
            return match.group(1).strip().strip('"')
    return " ".join(collected).strip()


def load_manifest(sources_json: Path) -> dict[str, dict[str, object]]:
    data = json.loads(sources_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{sources_json}: expected a non-empty JSON object")
    return data


def resolve_skill_dir(skills_root: Path, skill_name: str) -> Path:
    """The skill directory matching *skill_name* under any category of
    *skills_root*, matched case-sensitively — a case-only mismatch
    (``Manager`` vs ``manager``) must not silently resolve on a
    case-insensitive filesystem (Windows, macOS default)."""
    candidates = [
        p.parent for p in skills_root.rglob("SKILL.md") if p.parent.name == skill_name
    ]
    exact = [c for c in candidates if c.name == skill_name]
    if not exact:
        raise ValueError(
            f"no skill directory named exactly {skill_name!r} under {skills_root} "
            "(a case-only or spelling mismatch does not count as a match)"
        )
    return exact[0]


def render_adapter(name: str, entry: dict[str, object], description: str) -> str:
    tools = ", ".join(entry["tools"])  # type: ignore[arg-type]
    skill = entry["skill"]
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"model: {entry['model']}",
        f"tools: {tools}",
        "skills:",
        f"  - {skill}",
        "---",
        "",
        f"Loads the `{skill}` role skill (preloaded above via the `skills:` "
        "frontmatter field) for the full role definition. See "
        f"`skills/roles/{skill}/SKILL.md`. Do not edit this file by hand; it is "
        "generated by `scripts/install/install_agents` from that skill.",
        "",
    ]
    return "\n".join(lines)


def generate(agents_dir: Path, skills_root: Path, sources_json: Path) -> list[Path]:
    manifest = load_manifest(sources_json)
    agents_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in sorted(manifest):
        entry = manifest[name]
        skill_name = str(entry["skill"])
        skill_dir = resolve_skill_dir(skills_root, skill_name)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            raise ValueError(f"{skill_dir}: no SKILL.md")
        description = skill_description(skill_md)
        if not description:
            raise ValueError(
                f"{skill_md}: empty description -- refusing to generate an "
                "adapter with a blank description"
            )
        content = render_adapter(name, entry, description)
        target = agents_dir / f"{name}.md"
        target.write_text(content, encoding="utf-8", newline="\n")
        written.append(target)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            f"usage: {argv[0]} <agents_dir> <skills_root> <sources_json>",
            file=sys.stderr,
        )
        return 2
    agents_dir, skills_root, sources_json = (Path(a) for a in argv[1:4])
    try:
        written = generate(agents_dir, skills_root, sources_json)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"{argv[0]}: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"generated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
