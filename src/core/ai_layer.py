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

**`.mcp.json` is in this list, and a project should have none** (REQ-019 Decided
2026-10-10, DG-457). The file holds one line naming a command, and
`drunken-jira-mcp` serves every project because each `jira_*` tool takes the
registry project id as its first argument, so the server is declared once per
machine at the agent's user level (`claude mcp add --scope user`), never in a
project. Listing it here makes `drunken-doctor`'s `layering.tracked` flag a
committed copy and lets init keep a stray one out of git; `core/config_gen.py`
still emits the same shape for a *host* config, which lives in the user's home.

**Naming, for DG-438's implementer**: `core/doctor.py` already has an
`AI_LAYER_ROOTS` — a different concept entirely (where *this repository's
own* skill install, host-side, is compared for drift against `~/.claude`).
This module's `AI_LAYER_PATHS` is a *project's* own AI layer, the REQ-019
sense. Keep the two apart by name; do not let a future edit conflate them.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Optional, Union

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
    ".mcp.json",
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

#: Listed above so that `drunken-doctor` flags a tracked copy and the exclude file hides a stray one,
#: but **never provided by a config repo**: a project carries no `.mcp.json` at all (REQ-019
#: Decided 2026-10-10, DG-457), so the copy-in must not be what puts one there. Root-only, like the
#: entry above.
NEVER_COPIED_IN_FILES: tuple[str, ...] = (".mcp.json",)

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


def is_copied_in_from_config_repo(path: PathLike) -> bool:
    """True when *path* is on the AI-layer list **and** a config repo may provide it.

    The copy-in's own filter (:func:`core.layer_copy.ai_layer_files_under`): the one list, minus
    :data:`NEVER_COPIED_IN_FILES`. Everything else that asks "is this the AI layer" — the doctor,
    the exclude writer, the migration — keeps using :func:`is_ai_layer_path`.
    """
    return is_ai_layer_path(path) and _normalise(path) not in NEVER_COPIED_IN_FILES


def is_content_scan_path(path: PathLike) -> bool:
    """True when *path* should be read for leaked-credential-, identity- or path-shaped content
    (DG-508) — a wider question than :func:`is_ai_layer_path`, which stays exactly as it was and
    keeps deciding ``layering.tracked`` and what the config-repo copy-in provides.

    Every name on :data:`AI_LAYER_ROOT_DIRS` (``.claude``, ``.gemini``) and ``.mcp.json`` match
    here at *any* depth and *any* case — unlike :func:`is_ai_layer_path`, which keeps both
    root-only and case-sensitive. `drunken-doctor`'s content_scan (:mod:`core.doctor`,
    ``_check_project_content_scan``) is the only caller; it is a read-only, second line of
    defence against a leaked secret, not a claim about what an agent loads, so widening it here
    never changes what ``drunken-init``'s copy-in writes into a project or what
    ``layering.tracked`` flags as committed.

    Per-name evidence (DG-508's SCOPE: decide with evidence; where unsure, scan anyway):

    * **A nested `.claude`/`.gemini` directory** (``packages/x/.claude/settings.json``):
      Claude Code's own settings docs
      (https://code.claude.com/docs/en/settings, "Where Claude Code keeps the local file in a
      git repository") say "Claude Code reads the shared `.claude/settings.json` from the
      session's primary working directory" — a session started inside ``packages/x/`` reads
      ``packages/x/.claude/settings.json``, not only a root one. A monorepo subpackage is
      exactly that case, so this is read at any depth for the same reason
      :data:`AI_LAYER_BASENAMES` already treats ``CLAUDE.md``/``AGENTS.md``/``GEMINI.md`` that
      way — :func:`is_ai_layer_path` itself stays root-only, since REQ-019's own citation never
      claimed a nested directory is read the way the root one is; this wider, content-scan-only
      question does not need that same certainty to say "read it anyway."
    * **A differently-cased root directory** (``.Claude/settings.json``): not an agent-behaviour
      citation but a filesystem fact DG-453's tracked-file check already relies on — NTFS and
      APFS (default) are case-insensitive, so ``.Claude/`` and ``.claude/`` are the very same
      on-disk directory there, and a case-sensitive basename comparison alone misses it.
    * **A nested `.mcp.json`**: **no citation found.** Claude Code's own MCP docs
      (https://code.claude.com/docs/en/mcp) say only "a `.mcp.json` file at your project's root
      directory" / "at your project root", and never discuss a nested copy, a monorepo, or
      several `.mcp.json` files. Scanned anyway, on the "where unsure, scan it" side of DG-508's
      SCOPE — a credential sitting there is still a credential whether or not Claude Code reads
      it from that spot. :data:`NEVER_COPIED_IN_FILES` and the copy-in are unaffected: a project
      still never receives a ``.mcp.json`` from the config repo, root or nested (DG-457).

    A real dependency install (``.venv``, ``node_modules``, ``vendor`` — DG-505) is never
    affected by this being wider: that guard runs at the *directory* level, in
    :func:`core.layer_copy.ai_layer_files_under`, before this predicate is ever asked about a
    file inside it, and it keeps asking the narrower :func:`is_copied_in_from_config_repo` for
    "does this directory hold the project's own AI layer" — this function only decides which
    *already-walked* file gets its content read.
    """
    normalised = _normalise(path)
    if not normalised:
        return False
    if is_ai_layer_path(normalised):
        return True

    segments = normalised.split("/")
    basename = segments[-1]
    if basename.casefold() == ".mcp.json":
        return True

    root_dirs_casefold = {name.casefold() for name in AI_LAYER_ROOT_DIRS}
    return any(segment.casefold() in root_dirs_casefold for segment in segments[:-1])


#: The declared package name of this repository's own ``pyproject.toml`` —
#: see :func:`target_is_this_repository`.
THIS_REPOSITORY_PACKAGE_NAME = "drunken-guild"

#: A TOML string value at the start of a line's remainder after ``=``:
#: either quote style, capturing only what is between the matching pair and
#: deliberately not anchored at the end — so ``"drunken-guild"  # comment``
#: still matches the value alone, the trailing comment included. This is
#: not a general TOML parser (no escape handling); it only has to recognise
#: the one line shape ``name = "..."`` already relied on elsewhere in this
#: codebase (``core.doctor.declared_version``), slightly hardened against
#: the one false negative DG-442 review found: a trailing comment.
_TOML_STRING_VALUE_RE = re.compile(r"""^\s*(?:"([^"]*)"|'([^']*)')""")


def _parse_toml_string_value(raw_value: str) -> Optional[str]:
    """The quoted value at the start of *raw_value*, or ``None`` when it
    does not open with a quote at all (unquoted, or empty)."""
    match = _TOML_STRING_VALUE_RE.match(raw_value)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def target_is_this_repository(git_root: Path) -> bool:
    """Whether *git_root* is this repository's own checkout (DG-442 review).

    Read from *git_root*'s own ``pyproject.toml`` — ``[project] name =
    "drunken-guild"`` — never from ``__file__``. A ``__file__``-based signal
    (``core.doctor.source_tree_root()``) answers the wrong question here: it
    asks "where did *this running copy of the code* come from", which is
    ``None`` for the installed CLI (``uv tool install`` resolves inside a
    virtualenv with no ``skills/`` to find) — exactly the only case that
    matters for a real run. This asks "what does *the target* declare",
    which is answerable (or not) regardless of how drunken-init itself was
    started.

    ``pyproject.toml`` over a new marker file: it is already tracked by this
    repository on purpose (CLAUDE.md: "the AI layer stays in git,
    deliberately" — and so does the rest of the source tree), it is already
    the one canonical "what package is this" file, and it is already read
    this same line-scanned way (``[project]`` section, no TOML dependency)
    by :func:`core.doctor.declared_version` for the sibling question "what
    version does this source tree declare" — reusing that shape rather than
    inventing a second one that every real clone would need to carry too.

    DG-442 review: a leading UTF-8 BOM and an unquoted trailing ``#``
    comment on the ``name =`` line both used to read as a false negative
    (misclassifying this repository itself as "a project under the
    guild"). ``"utf-8-sig"`` quietly strips a BOM when present and is
    byte-identical to ``"utf-8"`` when there is none, so every file is
    still read exactly once either way. The value itself is parsed with
    :func:`_parse_toml_string_value` rather than a bare ``strip('"')``,
    which only strips from the two ends and left a trailing comment's text
    fused onto the value. Every false-*positive* guard already in place —
    exact string equality against ``THIS_REPOSITORY_PACKAGE_NAME``, no
    fuzzy or substring matching, no match at all on an unquoted value — is
    unchanged.
    """
    pyproject = git_root / "pyproject.toml"
    try:
        lines = pyproject.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        # DG-456: a pyproject.toml that is not decodable as UTF-8 (a BOM-
        # less UTF-16 file, stray Latin-1 bytes, ...) used to raise
        # UnicodeDecodeError straight out of drunken-init — a traceback
        # instead of a normal run. The safe direction is the same one
        # already taken for an unreadable or missing file: treat the
        # target as "not this repository" and say nothing alarming.
        # Nothing is read from the file again once this is caught, so no
        # file content ever reaches an error message or stdout.
        return False

    in_project = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if in_project:
                break
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("name") and "=" in stripped:
            name = _parse_toml_string_value(stripped.split("=", 1)[1])
            return name == THIS_REPOSITORY_PACKAGE_NAME
    return False
