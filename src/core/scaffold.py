"""A project's instruction file, written once — DG-392 (REQ-007, REQ-015).

Skills, the jira-mcp project-id error and the docs all send a project's agents to
its ``AGENTS.md``, and nothing ever created one, so the map every flow step reads
did not exist. ``drunken-init --path`` now writes it, plus a ``CLAUDE.md`` that
is only ``@AGENTS.md``: Claude Code before v2.1.277, and any session that cannot
fetch its feature flags, reads CLAUDE.md alone, and the import is how AGENTS.md
reaches it there.

Both files belong to the project the moment they exist. Nothing here overwrites
one, and a CLAUDE.md that does not import AGENTS.md is reported, not edited.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import List

#: The whole of the Claude adapter. Anything more would be a second surface.
CLAUDE_ADAPTER = "@AGENTS.md\n"


def _write_new(path: Path, text: str) -> None:
    # newline="" keeps LF on Windows: these files are meant to be committed.
    with open(path, "x", encoding="utf-8", newline="") as handle:
        handle.write(text)


def agents_md(project: str, jira_key: str | None) -> str:
    template = resources.files("core").joinpath("templates/AGENTS.md")
    return template.read_text(encoding="utf-8").format(
        project=project,
        jira_key=f"`{jira_key}`"
        if jira_key
        else "not set — `drunken-init --jira-project-key`",
    )


def instruction_files(checkout: Path, project: str, jira_key: str | None) -> List[str]:
    """Write what is missing in *checkout*; return one report line per file."""
    lines: List[str] = []

    agents = checkout / "AGENTS.md"
    if agents.exists():
        lines.append(f"AGENTS.md       : kept, {agents} already exists")
    else:
        _write_new(agents, agents_md(project, jira_key))
        lines.append(f"AGENTS.md       : written, {agents}")

    claude = [
        p
        for p in (checkout / "CLAUDE.md", checkout / ".claude" / "CLAUDE.md")
        if p.exists()
    ]
    if not claude:
        _write_new(checkout / "CLAUDE.md", CLAUDE_ADAPTER)
        lines.append(
            f"CLAUDE.md       : written, {checkout / 'CLAUDE.md'} (@AGENTS.md)"
        )
    else:
        text = claude[0].read_text(encoding="utf-8", errors="replace")
        if "@AGENTS.md" in text:
            lines.append(f"CLAUDE.md       : kept, {claude[0]} imports AGENTS.md")
        else:
            lines.append(
                f"CLAUDE.md       : kept, {claude[0]} does not import AGENTS.md. "
                "Add a line `@AGENTS.md`, or Claude Code will not read it."
            )
    return lines
