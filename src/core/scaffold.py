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

from .errors import ValidationError

#: The whole of the Claude adapter. Anything more would be a second surface.
CLAUDE_ADAPTER = "@AGENTS.md\n"

#: DG-408. These bracket the pointer table in the packaged template, and in
#: any AGENTS.md that started life from it — the only text `--guild-block`
#: is allowed to touch.
GUILD_BLOCK_START = "<!-- guild-block:start -->"
GUILD_BLOCK_END = "<!-- guild-block:end -->"

#: UTF-8 BOM, left decoded as a literal character by the ``"utf-8"`` codec
#: (unlike ``"utf-8-sig"``, which would strip it) — exactly what lets it be
#: carried through untouched at byte 0 while the heading search skips it.
_BOM = "﻿"


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


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _locate_markers(agents_path: Path, text: str) -> tuple[list[int], list[int]]:
    """Every start/end marker position, or raise on anything that is not
    either zero markers (insert) or exactly one well-formed pair (replace).

    A file this cannot reason about is refused rather than spliced: a start
    with no end, an end before its start, or more than one of either would
    make "replace only the text between the markers" a guess, not a fact.
    """
    starts = [m.start() for m in re.finditer(re.escape(GUILD_BLOCK_START), text)]
    ends = [m.start() for m in re.finditer(re.escape(GUILD_BLOCK_END), text)]

    problem: str | None = None
    if len(starts) > 1:
        problem = (
            f"more than one guild-block:start marker — a second one at "
            f"line {_line_of(text, starts[1])}"
        )
    elif len(ends) > 1:
        problem = (
            f"more than one guild-block:end marker — a second one at "
            f"line {_line_of(text, ends[1])}"
        )
    elif len(starts) == 1 and len(ends) == 0:
        problem = (
            f"guild-block:start marker at line {_line_of(text, starts[0])} "
            "has no matching guild-block:end marker"
        )
    elif len(starts) == 0 and len(ends) == 1:
        problem = (
            f"guild-block:end marker at line {_line_of(text, ends[0])} "
            "has no matching guild-block:start marker"
        )
    elif len(starts) == 1 and len(ends) == 1 and ends[0] < starts[0]:
        problem = (
            f"guild-block:end marker at line {_line_of(text, ends[0])} "
            f"appears before its guild-block:start marker at line "
            f"{_line_of(text, starts[0])}"
        )

    if problem:
        raise ValidationError(
            f"{agents_path} has a malformed guild block: {problem}.",
            remediation=(
                "Fix the markers by hand so there is exactly one matched "
                "pair, or remove them entirely so --guild-block can insert "
                "a fresh one."
            ),
        )
    return starts, ends


def merge_guild_block(agents_path: Path) -> str:
    """Insert or refresh the guild block in an *existing* AGENTS.md.

    No block yet: insert right after the first heading, skipping a leading
    UTF-8 BOM if there is one. An older well-formed block: replace only the
    text between its markers. Everything else — every byte outside the
    markers, the BOM included — is untouched, so a second run changes
    nothing.

    Refuses rather than guessing: *agents_path itself* being a symlink, or
    carrying markers it cannot make sense of. This does not catch every way
    AGENTS.md could point somewhere unexpected — a hard link to a file
    outside the project looks like an ordinary file and is written through
    like one, and a `--path` that is itself a junction or sits under a
    symlinked parent directory is the operator's own choice, not something
    this function can second-guess from the leaf name alone.
    """
    if agents_path.is_symlink():
        raise ValidationError(
            f"{agents_path} is a symlink; refusing to merge the guild block "
            "through it.",
            remediation=(
                "Point --path at the project whose own AGENTS.md you want to "
                "update, or replace the symlink with a regular file."
            ),
        )

    # newline="" on read too: Path.read_text() translates CRLF to LF, which
    # would make an untouched CRLF byte outside the markers look touched.
    with open(agents_path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    block = _guild_block_text()

    starts, ends = _locate_markers(agents_path, text)

    if starts and ends:
        start, end = starts[0], ends[0] + len(GUILD_BLOCK_END)
        new_text = text[:start] + block + text[end:]
    else:
        bom = _BOM if text.startswith(_BOM) else ""
        body = text[len(bom) :]
        heading = re.search(r"^#.*(?:\n|\Z)", body, re.MULTILINE)
        insert_at = len(bom) + (heading.end() if heading else 0)
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
