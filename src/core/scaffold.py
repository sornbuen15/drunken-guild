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

import re
from importlib import resources
from pathlib import Path
from typing import List

#: The whole of the Claude adapter. Anything more would be a second surface.
CLAUDE_ADAPTER = "@AGENTS.md\n"

#: DG-408. These bracket the pointer table in the packaged template, and in
#: any AGENTS.md that started life from it — the only text `--guild-block`
#: is allowed to touch.
GUILD_BLOCK_START = "<!-- guild-block:start -->"
GUILD_BLOCK_END = "<!-- guild-block:end -->"


def _guild_block_text() -> str:
    """The current guild block, markers included, read from the packaged
    template — the same source `agents_md()` uses for a fresh file."""
    template = (
        resources.files("core")
        .joinpath("templates/AGENTS.md")
        .read_text(encoding="utf-8")
    )
    start = template.index(GUILD_BLOCK_START)
    end = template.index(GUILD_BLOCK_END, start) + len(GUILD_BLOCK_END)
    return template[start:end]


def merge_guild_block(agents_path: Path) -> str:
    """Insert or refresh the guild block in an *existing* AGENTS.md.

    No block yet: insert right after the first heading. An older block:
    replace only the text between its markers. Everything else — every byte
    outside the markers — is untouched, so a second run changes nothing.
    """
    # newline="" on read too: Path.read_text() translates CRLF to LF, which
    # would make an untouched CRLF byte outside the markers look touched.
    with open(agents_path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    block = _guild_block_text()

    if GUILD_BLOCK_START in text and GUILD_BLOCK_END in text:
        start = text.index(GUILD_BLOCK_START)
        end = text.index(GUILD_BLOCK_END) + len(GUILD_BLOCK_END)
        new_text = text[:start] + block + text[end:]
    else:
        heading = re.search(r"^#.*(?:\n|\Z)", text, re.MULTILINE)
        insert_at = heading.end() if heading else 0
        new_text = text[:insert_at] + "\n" + block + "\n" + text[insert_at:]

    if new_text == text:
        return "unchanged"

    # newline="" keeps LF for what we write, same as the rest of init; any
    # CRLF already in the untouched parts of the file is carried through
    # verbatim because it was never decoded away.
    with open(agents_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(new_text)
    return "merged"


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
