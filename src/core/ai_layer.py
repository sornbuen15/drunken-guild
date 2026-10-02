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
that is committed on purpose.

**`.mcp.json` is deliberately not in this list, and the exclusion is pending a
decision the Boss has not made.** REQ-019's own wording ("Jira configuration")
could be read to reach it, but `core/config_gen.py` (DG-228) treats a
repository's `.mcp.json` as vendor-neutral and meant to be committed and
shared — names commands, never paths. Two ways to resolve this: **(A)** keep
it excluded — `drunken-doctor` stays silent on it, `config_gen`/DG-228 keep
writing a tracked, shared file; **(B)** include it — matches the REQ-019 text
more literally, but then every project's already-committed `.mcp.json` needs
a migration through init/exclude, not just a doctor warning. Nothing is built
on either answer yet; see the DG-437 ticket comment and the PR for the
question as put to the Boss.

**Naming, for DG-438's implementer**: `core/doctor.py` already has an
`AI_LAYER_ROOTS` — a different concept entirely (where *this repository's
own* skill install, host-side, is compared for drift against `~/.claude`).
This module's `AI_LAYER_PATHS` is a *project's* own AI layer, the REQ-019
sense. Keep the two apart by name; do not let a future edit conflate them.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Union

#: Basenames recognised at *any* depth: a project's AI layer is not only at
#: the repository root for these three — a monorepo may carry
#: `packages/x/CLAUDE.md` or `sub/dir/AGENTS.md` alongside the root one, and
#: Claude Code, Gemini CLI and Antigravity all read an instruction file next
#: to the code it describes, not only at the top. Matched on the file's own
#: name (`PurePosixPath(path).name`), so a similarly named file that is not
#: actually one of these — `docs/CLAUDE.md.bak`, `my-AGENTS.md` — does not
#: match: the comparison is the whole basename, never a substring.
#:
#: Case-sensitive, deliberately: this checks a path on a tracked, case
#: sensitive git index, where `agents.md` is a different blob from
#: `AGENTS.md` and would need its own row the moment a project actually had
#: one — nothing here claims that case varies in practice.
AI_LAYER_BASENAMES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
)

#: Files recognised at the repository root only. `CONVENTIONS.md` and
#: `.aider.conf.yml` are a pair — Aider's own template
#: (`templates/.aider.conf.yml`) loads `CONVENTIONS.md` and `CLAUDE.md` into
#: every session, and `templates/CONVENTIONS.md` describes itself as living
#: "beside `.aider.conf.yml`" in the project root, not at any depth.
#: `CLAUDE.local.md` is Claude Code's personal, per-checkout override next to
#: `CLAUDE.md` — **not verified against Claude Code's live docs**, carried
#: over from the reviewer's instruction as-is; say so rather than implying a
#: citation that was not actually checked.
AI_LAYER_ROOT_FILES: tuple[str, ...] = (
    ".aider.conf.yml",
    "CONVENTIONS.md",
    "CLAUDE.local.md",
)

#: Directories recognised at the repository root only, and everything under
#: them. **Root-only, on purpose**: the only citable source in this
#: repository for how Claude Code loads project configuration is REQ-015's
#: own evidence (`.ai/PRD.md`, https://code.claude.com/docs/en/memory), which
#: speaks to `CLAUDE.md`/`AGENTS.md` imports, not to a *nested*
#: `packages/x/.claude/` being read the way the top-level `.claude/` is. Not
#: finding that citation here is why this stays root-only rather than
#: matching `.claude/` and `.gemini/` at any depth the way the three
#: instruction-file basenames above do.
AI_LAYER_ROOT_DIRS: tuple[str, ...] = (
    ".claude",
    ".gemini",
)

PathLike = Union[str, "PurePosixPath"]


def _normalise(path: PathLike) -> str:
    """*path* as repo-relative, forward-slashed segments.

    A caller may pass a Windows-style path (backslashes) or a leading
    ``./`` — both are normalised away before comparing against the lists
    above, themselves written forward-slashed. ``..`` is never resolved
    here: that is the caller's own path, lexical or not, and not something
    this function second-guesses from the string alone.
    """
    text = str(path).replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def is_ai_layer_path(path: PathLike) -> bool:
    """True when *path*, repo-relative, is part of the project's AI layer.

    `AI_LAYER_BASENAMES` matches at any depth, by the file's own name;
    `AI_LAYER_ROOT_FILES` and `AI_LAYER_ROOT_DIRS` match only at the
    repository root, by the first path segment — see each tuple's own
    docstring for why.
    """
    normalised = _normalise(path)
    if not normalised:
        return False

    basename = normalised.rsplit("/", 1)[-1]
    if basename in AI_LAYER_BASENAMES:
        return True

    first_segment = normalised.split("/", 1)[0]
    if first_segment in AI_LAYER_ROOT_DIRS:
        return True
    if normalised == first_segment and normalised in AI_LAYER_ROOT_FILES:
        return True
    return False
