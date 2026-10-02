"""The one list of what makes up a project's AI layer — REQ-019 (DG-437).

REQ-019 says a project's own git tracks none of its AI layer. Nothing said
what the AI layer *is*: init, doctor and the exclude writer would each grow
their own list and drift, which is the failure this guild keeps meeting (see
`skills/git-workflow` on `git-workflow` itself drifting to 73 lines against
196). This module is the one list every one of them reads instead.

**In scope**: how the AI works on the project — the instruction files and the
per-agent settings directories the supported agents (Claude Code, Antigravity,
Aider, Gemini CLI) read from a project's own checkout. **Out of scope**: the
work itself — code, `README.md`, `.ai/PRD.md`, `.ai/DOMAIN.md` — and anything
that is committed on purpose, such as a repository's own `.mcp.json`
(vendor-neutral, names commands rather than paths, meant to be shared).

Nothing in this project imports this module yet (DG-437's own scope); DG-438's
doctor check is the first caller.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Union

#: Repo-relative patterns that make up a project's AI layer. A name with no
#: trailing slash matches exactly that file at the repository root; a name
#: ending in "/" matches that directory at the repository root, and
#: everything under it. Every supported agent is represented: `AGENTS.md` is
#: the shared instruction file every agent is pointed at (REQ-007, REQ-011);
#: `CLAUDE.md` and `.claude/` are Claude Code's adapter and settings
#: (REQ-015, `.claude/settings.json`, `.claude/settings.local.json`,
#: `.claude/rules/`); `GEMINI.md` and `.gemini/` are Gemini CLI's and
#: Antigravity's own instruction file and settings directory, the same shape
#: as Claude Code's; `.aider.conf.yml` is Aider's project config, which
#: REQ-003 has read AGENTS.md and every skill description at session start.
#:
#: Deliberately absent: a project's own `.mcp.json`. It is vendor-neutral,
#: names commands rather than paths, and is meant to be committed and shared
#: (`core/config_gen.py`) — it is not an agent-specific instruction or
#: settings file, and REQ-019 does not reach it.
AI_LAYER_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".aider.conf.yml",
    ".claude/",
    ".gemini/",
)

PathLike = Union[str, "PurePosixPath"]


def _normalise(path: PathLike) -> str:
    """*path* as repo-relative, forward-slashed segments.

    A caller may pass a Windows-style path (backslashes) or a leading
    ``./`` — both are normalised away before comparing against
    `AI_LAYER_PATHS`, which is itself written forward-slashed. ``..`` is
    never resolved here: that is the caller's own path, lexical or not, and
    not something this function second-guesses from the string alone.
    """
    text = str(path).replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def is_ai_layer_path(path: PathLike) -> bool:
    """True when *path*, repo-relative, is part of the project's AI layer.

    Matched at the repository root only, by the first path segment: a
    project's own subdirectory that happens to be named like one of these
    (there is no such case among the supported agents today) is not what
    this guards against — the list names top-level agent files and
    directories, the shape every supported agent actually uses.
    """
    normalised = _normalise(path)
    if not normalised:
        return False
    first_segment = normalised.split("/", 1)[0]

    for pattern in AI_LAYER_PATHS:
        if pattern.endswith("/"):
            if first_segment == pattern[:-1]:
                return True
        elif normalised == pattern:
            return True
    return False
