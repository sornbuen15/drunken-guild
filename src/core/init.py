"""``drunken-init`` — create the state directory and register a project.

Setting up used to mean running ``drunken-register``, answering six interactive
prompts, and ending up with the Jira token and the Discord bot token written in
plaintext into ``<project>/.agents/`` — inside the repository. It also never
wrote the central registry that the servers actually read, so following the
on-screen instructions could not produce a working install.

This is the replacement, and the constraints follow directly from the four rules
this redesign is built on:

* **Non-interactive.** A setup step that blocks on ``input()`` cannot run in a
  Dockerfile, a CI job, or a provisioning script. Everything is a flag.
* **Never accepts a secret.** ``--jira-credential`` takes a *reference*, and the
  reference is validated before anything is written. There is no flag that
  accepts a token, so a token cannot end up in the file — or in shell history.
* **Idempotent.** Re-running updates in place and leaves unrelated fields alone,
  so it is safe to put in a provisioning script that runs more than once.

``drunken-register`` was kept alongside this for one release, because it also
provisioned Antigravity's dashboard entry. It is gone as of 2.2.0 (S11) and is
no longer declared in ``[project.scripts]``, so anything still naming it — an
error's remediation, a README step — is quoting a command that exits 127.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from . import content_scan, exclude, git_hooks, layer_copy, paths, scaffold, secrets
from .errors import DrunkenError, ValidationError
from .registry import SCHEMA_VERSION, validate_project_id

#: The declared package name of this repository's own ``pyproject.toml`` —
#: see :func:`_target_is_this_repository`.
_THIS_REPOSITORY_PACKAGE_NAME = "drunken-guild"

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


def _validate_credential_reference(reference: str) -> None:
    """Refuse anything that is not a resolvable reference.

    Checked here as well as at resolution time so the mistake is caught while
    the operator is still looking at the terminal, rather than surfacing much
    later as a confusing failure inside a server.
    """
    secrets.parse_ref(reference)


class TrackedInstructionFileConflictError(ValidationError):
    """A project's own git already tracks AGENTS.md/CLAUDE.md (DG-442)."""

    code = "tracked_instruction_file_conflict"


def _resolve_git_root(entry: dict[str, Any], project_root: Path) -> Path:
    """*project_root*'s real git top level, applying the registry's
    ``git_root`` offset the same way :func:`_copy_ai_layer_in` already does —
    one join, reused here rather than duplicated, so the two never drift on
    what "the project's real git root" means.
    """
    git_root = entry.get("git_root")
    return project_root / str(git_root) if git_root else project_root


def _target_is_this_repository(git_root: Path) -> bool:
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
    exact string equality against ``_THIS_REPOSITORY_PACKAGE_NAME``, no
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
            return name == _THIS_REPOSITORY_PACKAGE_NAME
    return False


def _tracked_instruction_files(git_root: Path, project_root: Path) -> list[str]:
    """AGENTS.md/CLAUDE.md already tracked by *git_root*'s own git, named
    relative to *git_root* — empty when *git_root* is not a git repository
    at all (nothing to be tracked by) or when neither file is tracked.

    Reuses :mod:`core.layer_copy`'s own hardened, ``GIT_*``-stripped
    tracked-check (``_is_tracked``, imported rather than reimplemented —
    DG-453 owns that module) instead of
    :func:`core.doctor.tracked_ai_layer_paths`, which runs plain
    ``git ls-files`` with no environment stripped at all and is already
    named in DG-440's own module docstring as the wrong shape for exactly
    this: a leaked ``GIT_INDEX_FILE`` pointing at an empty or alternate index
    answers "not tracked" for a file that is, in fact, committed.
    """
    try:
        exclude.resolve_info_exclude_path(git_root)
    except exclude.NotAGitRepositoryError:
        return []

    git_root_resolved = git_root.resolve()
    tracked: list[str] = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        candidate = (project_root / name).resolve()
        try:
            relative = candidate.relative_to(git_root_resolved).as_posix()
        except ValueError:
            continue
        if layer_copy._is_tracked(git_root_resolved, relative):  # noqa: SLF001
            tracked.append(relative)
    return tracked


def _refuse_if_already_tracked(git_root: Path, project_root: Path) -> None:
    """Refuse outright, before anything is written, when *project_root*'s
    own git already tracks AGENTS.md/CLAUDE.md (DG-442, REQ-019/020).

    The migration for an existing project that already tracks these files is
    an open PRD question and is not attempted here — drunken-init surfaces
    the conflict instead of silently proceeding as though the project's own
    git did not already own them.
    """
    tracked = _tracked_instruction_files(git_root, project_root)
    if tracked:
        raise TrackedInstructionFileConflictError(
            f"{project_root} already tracks {', '.join(tracked)} in its own "
            "git; drunken-init no longer writes a project's "
            "AGENTS.md/CLAUDE.md as a tracked file (REQ-019/REQ-020).",
            remediation=(
                "Untrack it first (`git rm --cached <path>`) if it should "
                "come from the AI layer instead. The migration itself is an "
                "open PRD question and is not performed by drunken-init."
            ),
        )


def _build_jira_block(args: argparse.Namespace) -> Optional[dict[str, str]]:
    supplied = {
        "url": args.jira_url,
        "email": args.jira_email,
        "project_key": args.jira_project_key,
        "credential": args.jira_credential,
    }
    if not any(supplied.values()):
        return None

    missing = [name for name, value in supplied.items() if not value]
    if missing:
        raise ValidationError(
            f"Incomplete Jira options: missing --jira-{'/--jira-'.join(m.replace('_', '-') for m in missing)}.",
            remediation="Provide all four Jira options together, or none of them.",
        )

    _validate_credential_reference(supplied["credential"])
    return {key: str(value) for key, value in supplied.items()}


def _ensure_registry_document(registry_file: str) -> dict[str, Any]:
    if not os.path.exists(registry_file):
        return {"version": SCHEMA_VERSION, "projects": {}}

    try:
        with open(registry_file, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except UnicodeDecodeError as exc:
        # DG-475: a registry an operator hand-edited, copied or otherwise
        # left in another encoding used to raise UnicodeDecodeError here
        # with no try/except at all -- a raw traceback instead of the
        # typed refusal every other malformed-registry shape already
        # gets below. The file's own bytes never reach this message: only
        # its path and the codec's own (byte, position) description do,
        # neither of which is file content. Nothing has been written by
        # this point, so a refusal here leaves the registry untouched,
        # same as every other branch in this function.
        raise ValidationError(
            f"{registry_file} is not valid UTF-8: {exc}",
            remediation=(
                "Fix its encoding (re-save as UTF-8) or remove the file, "
                "then run drunken-init again. Nothing has been written."
            ),
        ) from exc

    if not isinstance(document, dict):
        raise ValidationError(
            f"{registry_file} is not a JSON object.",
            remediation="Fix or remove the file, then run drunken-init again.",
        )

    if "projects" in document and isinstance(document["projects"], dict):
        return document

    # A v1 file: the document *is* the project map. Wrapping it is a real
    # migration, so it happens only here, where the operator asked for it.
    return {"version": SCHEMA_VERSION, "projects": document}


def _apply_project(document: dict[str, Any], args: argparse.Namespace) -> str:
    project_id = validate_project_id(args.project)
    entry: dict[str, Any] = dict(document["projects"].get(project_id, {}))

    if args.path:
        path = os.path.abspath(os.path.expanduser(args.path))
        if not os.path.isdir(path):
            raise ValidationError(
                f"Path does not exist: {path}",
                remediation=(
                    "Point --path at an existing directory. Omit it entirely for a "
                    "project that only talks to Jira or Discord — a containerised "
                    "server has no host checkout."
                ),
            )
        entry["path"] = path

    if args.git_root:
        entry["git_root"] = args.git_root
    if args.description:
        entry["description"] = args.description

    jira = _build_jira_block(args)
    if jira:
        entry["jira"] = jira
    if args.discord_webhook:
        # Validated the same way as the Jira credential: a webhook URL pasted
        # here instead of a reference would be written straight into a file
        # meant to be readable and shareable — and anyone holding that URL can
        # post as the bot.
        _validate_credential_reference(args.discord_webhook)
        entry["discord"] = {"webhook": str(args.discord_webhook)}
    if args.board_dir:
        entry["board"] = {"dir": args.board_dir}

    document["projects"][project_id] = entry
    return project_id


def _write(registry_file: str, document: dict[str, Any]) -> None:
    directory = os.path.dirname(registry_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(registry_file, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=4)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drunken-init",
        description=(
            "Create the drunken-guild state directory and register a project. "
            "Non-interactive and idempotent, so it can run in a Dockerfile or a "
            "provisioning script."
        ),
        epilog=(
            "Credentials are referenced, never stored: --jira-credential takes "
            "env://VAR, file://path#key.path, op://vault/item/field or "
            "keyring://service/user. There is deliberately no flag that accepts "
            "a token."
        ),
    )
    parser.add_argument("--project", help="Project id to add or update.")
    parser.add_argument("--path", help="Absolute path to the checkout (optional).")
    parser.add_argument(
        "--git-root",
        help=(
            "Relative offset from --path to the actual git repository top "
            "level, joined as --path/--git-root and never resolved by this "
            "flag itself. Two shapes: a SUBDIRECTORY when --path is an "
            "outer workspace and the repo is nested inside it (e.g. "
            "'backend'); or '..' (or '../..') to ASCEND when --path is "
            "itself registered at a subfolder of a larger repository (a "
            "monorepo package, say) and the real top level is an ancestor "
            "directory instead. Either way, exclude writing (--config-repo) "
            "always targets the resolved git top level, never --path."
        ),
    )
    parser.add_argument("--description", help="Human-readable description.")
    parser.add_argument("--jira-url", help="e.g. https://your-domain.atlassian.net")
    parser.add_argument("--jira-email", help="Account the credential belongs to.")
    parser.add_argument("--jira-project-key", help="e.g. ALPHA")
    parser.add_argument(
        "--jira-credential",
        help="Secret REFERENCE, not a token. e.g. env://JIRA_TOKEN_ALPHA",
    )
    parser.add_argument(
        "--discord-webhook",
        help=(
            "Secret REFERENCE to a Discord webhook URL, not the URL itself. "
            "Notifications are one-way and optional."
        ),
    )
    parser.add_argument("--board-dir", help="Board directory relative to the checkout.")
    parser.add_argument(
        "--guild-block",
        action="store_true",
        help=(
            "Merge the guild block into an EXISTING AGENTS.md (requires --path). "
            "No block yet: inserted after the first heading. An older block: only "
            "the text between its markers is replaced; everything else is "
            "untouched. Idempotent — a second run changes nothing."
        ),
    )
    parser.add_argument(
        "--config-repo",
        help=(
            "Path to a LOCAL clone of the private config repo (REQ-020). With "
            "--project, copies that project's AI-layer folder (named by its "
            "registered id) into its registered path, then excludes the "
            "copied files from the project's own git. No network access: "
            "the Boss clones the config repo; this only reads a path."
        ),
    )
    parser.add_argument(
        "--overwrite-ai-layer",
        action="store_true",
        help=(
            "Allow --config-repo to replace an existing, untracked AI-layer "
            "file in the project. Without it, an existing file is skipped "
            "and reported, never overwritten. A file the project's own git "
            "already tracks is always refused outright, with or without "
            "this flag."
        ),
    )
    parser.add_argument(
        "--registry", help="Registry file to write instead of the resolved default."
    )
    parser.add_argument(
        "--install-git-hooks",
        action="store_true",
        help=(
            "Install the native pre-push privacy-scan hook (DG-479/DG-480) "
            "into the current checkout's git hooks directory. Honours "
            "core.hooksPath and a linked worktree's shared hooks dir; "
            "refuses rather than overwrites or deletes a pre-push hook it "
            "did not write itself. Independent of --project: runs against "
            "--path if given, else the current working directory."
        ),
    )
    return parser


def _resolve_copy_targets(
    document: dict[str, Any], project_id: Optional[str]
) -> tuple[Path, Path]:
    """*project_id*'s registered ``path`` and resolved git root, or raise —
    shared by :func:`_validate_config_repo_content` and
    :func:`_copy_ai_layer_in` so the two can never resolve "where does the
    AI layer land" differently.

    Independent of whether ``--path`` was passed *this* run: a project
    registered earlier already has a ``path`` in the document, and
    ``--config-repo`` should work against it on a later, idempotent call —
    the same shape every other ``drunken-init`` flag already has.
    """
    if not project_id:
        raise ValidationError(
            "--config-repo requires --project.",
            remediation="Pass --project <id> together with --config-repo.",
        )

    entry = document["projects"][project_id]
    if not entry.get("path"):
        raise ValidationError(
            f"Project {project_id!r} has no registered path to copy its AI layer into.",
            remediation=(
                "Pass --path (this run or an earlier one) before --config-repo."
            ),
        )

    project_root = Path(entry["path"]).expanduser()
    git_root = _resolve_git_root(entry, project_root)
    return project_root, git_root


_JIRA_FRAGMENT_FILENAME = "jira.json"

#: The only keys `jira.json` (DG-443) may hold. No ``email``: the Boss's
#: rule is "no credential, no identity, no real path" in the config repo,
#: and an account's e-mail is an identity — it stays machine-local, read
#: from ``--jira-email`` / an already-registered entry, same as today.
_JIRA_FRAGMENT_ALLOWED_KEYS = frozenset({"url", "project_key", "credential"})


def _read_jira_fragment(project_folder: Path) -> Optional[dict[str, str]]:
    """``<project_folder>/jira.json`` (DG-443), read, scanned and validated
    — or ``None`` when there is no fragment at all, which is not an error:
    a project under the guild need not source its Jira block from the
    config repo.

    Scanned exactly like any other AI-layer file's content (token, userinfo,
    path, e-mail) even though it is never copied into a project and never on
    :mod:`core.ai_layer`'s list — the Boss's content rule does not stop at
    the files that get copied. ``email`` is refused by key, not only by
    shape: a value that is not itself e-mail-*shaped* would otherwise slip
    past the scanner's pattern while still being exactly the identity this
    ticket's rule names.
    """
    path = project_folder / _JIRA_FRAGMENT_FILENAME
    if not path.is_file():
        return None

    findings = content_scan.scan_file(path, _JIRA_FRAGMENT_FILENAME)
    if findings:
        detail = "; ".join(finding.describe() for finding in findings)
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} has {len(findings)} finding(s), "
            f"refusing before any write: {detail}",
            remediation=(
                "Replace the value with a reference (env://, file://, "
                "op://, keyring://), or remove it from the config repo."
            ),
        )

    try:
        raw = path.read_text(encoding="utf-8-sig")
        data: Any = json.loads(raw)
    except UnicodeDecodeError as exc:
        # DG-475: content_scan.scan_file above already turns most
        # undecodable content into a non-empty finding and refuses
        # earlier for the same reason, but this line's own
        # try/except caught only OSError and json.JSONDecodeError --
        # neither of which UnicodeDecodeError is -- so a narrow TOCTOU
        # (the file changing between that scan and this read) still
        # raised a raw traceback instead of this same typed refusal.
        # Only the path and the codec's own description reach the
        # message; the file's own bytes never do.
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} is not valid UTF-8: {exc}",
            remediation=f"Fix {path}'s encoding (re-save as UTF-8), or remove the file.",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} is not valid JSON: {exc}",
            remediation=f"Fix {path}'s JSON syntax, or remove the file.",
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} is not a JSON object.",
            remediation=f"Fix {path} to hold a single JSON object.",
        )

    if "email" in data:
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} holds an 'email' key, which is not "
            "allowed — the Jira account e-mail is an identity and stays "
            "machine-local, never in the config repo.",
            remediation=(
                "Remove 'email' from jira.json; set it locally instead with "
                "--jira-email (it is kept across runs once registered)."
            ),
        )

    missing = _JIRA_FRAGMENT_ALLOWED_KEYS - data.keys()
    if missing:
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} is missing: {', '.join(sorted(missing))}.",
            remediation=(
                f"Add all of {', '.join(sorted(_JIRA_FRAGMENT_ALLOWED_KEYS))} "
                f"to {path}, or remove the file entirely."
            ),
        )
    extra = set(data.keys()) - _JIRA_FRAGMENT_ALLOWED_KEYS
    if extra:
        raise ValidationError(
            f"{_JIRA_FRAGMENT_FILENAME} has unexpected key(s): "
            f"{', '.join(sorted(extra))}.",
            remediation=(
                f"Only {', '.join(sorted(_JIRA_FRAGMENT_ALLOWED_KEYS))} are "
                f"allowed in {path}."
            ),
        )

    _validate_credential_reference(str(data["credential"]))
    return {key: str(data[key]) for key in _JIRA_FRAGMENT_ALLOWED_KEYS}


def _validate_config_repo_content(
    document: dict[str, Any], project_id: Optional[str], args: argparse.Namespace
) -> Optional[dict[str, str]]:
    """Everything about ``--config-repo``'s own content that must be
    checked **before any write** (DG-443 review, decision 4): every
    AI-layer file's text, and ``jira.json``. Returns the Jira block to
    merge into the registry, or ``None`` when there is no fragment.

    Writes nothing: :func:`core.layer_copy.validate_ai_layer_copy` and
    :func:`_read_jira_fragment` are both read-only by construction. Called
    from ``main()`` strictly before ``_write()``, so a refusal here leaves
    the registry exactly as it found it — absent, for a brand-new project.
    """
    project_root, git_root = _resolve_copy_targets(document, project_id)
    config_repo = Path(args.config_repo).expanduser()

    validated = layer_copy.validate_ai_layer_copy(
        config_repo=config_repo,
        project_id=str(project_id),
        project_root=project_root,
        git_root=git_root,
    )
    return _read_jira_fragment(validated.project_folder)


def _copy_ai_layer_in(
    document: dict[str, Any], project_id: Optional[str], args: argparse.Namespace
) -> tuple[list[str], bool]:
    """DG-441 (REQ-019/020). Wire :func:`core.layer_copy.copy_ai_layer_in`.

    Returns the stdout report lines, and whether any file was skipped
    because it already exists *and differs* from the config repo — the
    second value is what ``main()`` turns into a non-zero exit. An
    identical existing file is "unchanged" and never drift.

    DG-442 moved AGENTS.md/CLAUDE.md generation (for a project under the
    guild) into the config repo's own working copy, generated *before* this
    runs in the same call — so this sees them exactly like any other
    AI-layer file already sitting in the project folder, never as a
    checkout-side collision the way they could when ``scaffold.instruction_
    files()`` used to write them straight into the checkout.

    DG-443: by the time this runs, ``main()`` has already called
    :func:`_validate_config_repo_content` once — this re-validates
    (``copy_ai_layer_in`` always does, on its own) rather than trusting a
    result computed before the registry write, which is cheap and keeps
    this function usable on its own, the way every existing test for it
    already calls it.
    """
    project_root, git_root = _resolve_copy_targets(document, project_id)

    result = layer_copy.copy_ai_layer_in(
        config_repo=Path(args.config_repo).expanduser(),
        project_id=str(project_id),
        project_root=project_root,
        git_root=git_root,
        overwrite=bool(args.overwrite_ai_layer),
    )

    lines = [f"ai layer        : copied, {path}" for path in result.copied]
    lines.extend(
        f"ai layer        : skipped, {skip.relative} ({skip.reason})"
        for skip in result.skipped
    )
    if result.excluded.added:
        lines.append(
            f"ai layer        : excluded {len(result.excluded.added)} "
            f"pattern(s) in {result.excluded.exclude_path}"
        )

    drifted = [skip for skip in result.skipped if not skip.identical]
    for skip in drifted:
        print(
            f"error: {project_root / skip.relative} already exists and "
            "differs from the config repo; not overwritten.",
            file=sys.stderr,
        )
        print(
            "  -> Reconcile it by hand, then re-run with --overwrite-ai-layer "
            "to take the config repo's copy, or leave it and wait for DG-442 "
            "(init stops writing a tracked AGENTS.md/CLAUDE.md on its own).",
            file=sys.stderr,
        )

    return lines, bool(drifted)


def _config_repo_project_folder(
    args: argparse.Namespace, project_id: str
) -> Optional[Path]:
    """``--config-repo``'s project folder for *project_id*, or ``None`` when
    ``--config-repo`` was not passed at all — kept separate from "that
    folder does not exist yet" (checked by the caller via ``is_dir()``) so
    the two can be told apart in an error message (DG-442 review)."""
    if not args.config_repo:
        return None
    return Path(args.config_repo).expanduser() / str(project_id)


def _resolve_instructions_dir(
    document: dict[str, Any],
    project_id: str,
    project_root: Path,
    args: argparse.Namespace,
) -> Optional[Path]:
    """Where AGENTS.md/CLAUDE.md should be generated for *project_id*, or
    ``None`` when there is nowhere to write them yet (DG-442).

    This repository's own checkout: *project_root* itself, unchanged,
    tracked. Any other project (a project under the guild): refuses outright
    if it already tracks either file (``_refuse_if_already_tracked``); else
    the config repo's own ``<project_id>`` folder, but only once that folder
    already exists — generation never creates one on its own, see
    :func:`_copy_ai_layer_in`'s own ``ConfigRepoProjectNotFoundError``.
    """
    entry = document["projects"][project_id]
    git_root = _resolve_git_root(entry, project_root)
    if _target_is_this_repository(git_root):
        return project_root

    _refuse_if_already_tracked(git_root, project_root)
    candidate = _config_repo_project_folder(args, project_id)
    return candidate if candidate is not None and candidate.is_dir() else None


def _generate_instruction_files(
    document: dict[str, Any],
    project_id: str,
    instructions_dir: Optional[Path],
    args: argparse.Namespace,
) -> list[str]:
    """The report lines for generating (or skipping) AGENTS.md/CLAUDE.md."""
    if instructions_dir is not None:
        jira_key = document["projects"][project_id].get("jira", {}).get("project_key")
        return scaffold.instruction_files(instructions_dir, project_id, jira_key)
    if args.config_repo:
        return [
            f"AGENTS.md       : skipped, no {project_id!r} folder yet "
            "in the config repo"
        ]
    return [
        "AGENTS.md       : skipped, pass --config-repo to generate it "
        "into the AI layer (REQ-019)"
    ]


def _apply_guild_block(
    instructions_dir: Optional[Path],
    existed_before: bool,
    args: argparse.Namespace,
    project_id: str,
) -> str:
    """Merge (or report the fresh creation of) the guild block, or refuse
    when there is nowhere to merge it into yet.

    DG-442 review: the refusal names the *actual* reason instead of a single
    generic "requires --config-repo" for both — ``--config-repo`` missing
    entirely is a different problem from ``--config-repo`` given but that
    project's folder not existing there yet, and an operator trying to fix
    the second by re-checking a flag that was already correct gets nowhere.
    """
    if instructions_dir is None:
        candidate = _config_repo_project_folder(args, project_id)
        if candidate is None:
            raise ValidationError(
                "--guild-block for a project under the guild requires --config-repo.",
                remediation=(
                    "Pass --config-repo together with --guild-block — it "
                    "merges into the config repo's own copy of AGENTS.md, "
                    "never the checkout directly — or omit --guild-block."
                ),
            )
        raise ValidationError(
            f"--guild-block needs the config repo's {project_id!r} folder, "
            f"which does not exist yet at {candidate}.",
            remediation=(
                f"Create {candidate} in the config repo (see --config-repo's "
                "own help), or omit --guild-block."
            ),
        )
    agents_path = instructions_dir / "AGENTS.md"
    if existed_before:
        status = scaffold.merge_guild_block(agents_path)
        return f"guild block     : {status}, {agents_path}"
    # instruction_files() just wrote a fresh AGENTS.md from the template,
    # which already opens with the current block — nothing to merge, but
    # say so rather than letting it read as "unchanged" next to a file that
    # did not exist a moment ago.
    return f"guild block     : created with the block, {agents_path}"


def _install_git_hooks(args: argparse.Namespace) -> str:
    """``--install-git-hooks``'s own report line — a single call straight
    through to :func:`core.git_hooks.install_pre_push_hook`."""
    hooks_target = Path(args.path).expanduser() if args.path else Path.cwd()
    return f"git hooks       : {git_hooks.install_pre_push_hook(hooks_target)}"


def _build_written_report(
    document: dict[str, Any],
    project_id: Optional[str],
    project_root: Optional[Path],
    instructions_dir: Optional[Path],
    existed_before: bool,
    args: argparse.Namespace,
) -> tuple[list[str], bool]:
    """Every ``written`` report line ``main()`` prints, plus whether the
    config-repo copy-in found drift — factored out purely to keep ``main``
    itself under ruff's own complexity budget (C901); each branch here is
    unchanged from what used to be inline in ``main``.
    """
    written: list[str] = []
    if project_id and args.path and project_root is not None:
        written = _generate_instruction_files(
            document, project_id, instructions_dir, args
        )

    if args.guild_block and project_root is not None and project_id is not None:
        written.append(
            _apply_guild_block(instructions_dir, existed_before, args, project_id)
        )

    config_repo_drifted = False
    if args.config_repo:
        layer_lines, config_repo_drifted = _copy_ai_layer_in(document, project_id, args)
        written.extend(layer_lines)

    if args.install_git_hooks:
        written.append(_install_git_hooks(args))

    return written, config_repo_drifted


def main() -> int:
    """Entry point for ``drunken-init``."""
    args = build_parser().parse_args()

    config_repo_drifted = False

    try:
        registry_file = args.registry or str(paths.registry_path())

        document = _ensure_registry_document(registry_file)
        project_id = _apply_project(document, args) if args.project else None

        project_root = (
            Path(document["projects"][project_id]["path"])
            if project_id and args.path
            else None
        )

        # DG-442 review: the tracked-file refusal (inside
        # _resolve_instructions_dir -> _refuse_if_already_tracked) must run
        # before ANYTHING is written — the state directory, the registry,
        # instruction files, the guild block, the config-repo copy-in, the
        # exclude file — so a refused run leaves every one of those exactly
        # as it found them. A reviewer reproduced the opposite: the registry
        # used to be written first, so a refused run still gained a
        # registry entry. This now runs strictly before `paths.ensure_home()`
        # and `_write()` below, both pure reads/computations until this
        # point.
        #
        # Where the generated AGENTS.md/CLAUDE.md actually land depends on
        # whether *project_root* is this repository's own checkout
        # (unchanged: written straight into the checkout, tracked) or a
        # project under the guild (generated into the config repo's working
        # copy, requires --config-repo, never written as a tracked file
        # into the project). See `_target_is_this_repository`.
        instructions_dir: Optional[Path] = (
            _resolve_instructions_dir(document, project_id, project_root, args)
            if project_root is not None and project_id is not None
            else None
        )

        # DG-443 review (comment 11482, decision 4): the config repo's own
        # content — every AI-layer file's text, and jira.json — is checked
        # the same way, and just as strictly before `_write()` below: a
        # refusal here must leave the registry exactly as it found it
        # (absent, for a brand-new project), not merely the project
        # checkout. `layer_copy.validate_ai_layer_copy` writes nothing by
        # construction; `_read_jira_fragment` only reads and validates.
        jira_fragment = (
            _validate_config_repo_content(document, project_id, args)
            if args.config_repo
            else None
        )
        if jira_fragment and project_id:
            document["projects"][project_id]["jira"] = jira_fragment

        home = paths.ensure_home()
        _write(registry_file, document)

        agents_path = instructions_dir / "AGENTS.md" if instructions_dir else None
        existed_before = bool(agents_path and agents_path.exists())

        written, config_repo_drifted = _build_written_report(
            document, project_id, project_root, instructions_dir, existed_before, args
        )
    except DrunkenError as exc:
        print(f"error: {exc}")
        if exc.remediation:
            print(f"  -> {exc.remediation}")
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 1

    print(f"state directory : {home}  (mode {oct(paths.HOME_MODE)[2:]})")
    print(f"registry        : {registry_file}  (schema v{document['version']})")
    if project_id:
        print(f"registered      : {project_id}")
    for line in written:
        print(line)
    print(
        f"projects        : {', '.join(sorted(document['projects'])) or '(none yet)'}"
    )
    print()
    print("Next: drunken-doctor")
    return 1 if config_repo_drifted else 0


if __name__ == "__main__":
    raise SystemExit(main())
