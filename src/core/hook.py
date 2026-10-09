"""PreToolUse hook — the deny floor, and nothing else.

This file used to route the harness's permission prompts to Discord: away mode,
a daemon socket, an approval state machine, and a learned-rules writer that
generalised each 👍 into a standing local rule. All of it is retired (DG-355).
Remote Control is where a session is watched now, and Discord is one-way
notification. What is left is the part that was never about asking anyone.

**A deny rule must hold even when no one can be reached.** That was always the
first step of the old order — evaluated before away mode, before
``bypassPermissions``, before anything — precisely because a remote 👍 must not
be able to authorise ``rm -rf``. With the remote half gone, the floor is the
whole file, and it answers the same three questions it always did:

1. Does a deny rule match this call? Then ``deny``, whatever the mode.
2. Can this call be read at all? A ``Bash`` with no command and a ``Read`` with
   no path match *no* rule — deny rules included — so they are refused rather
   than waved past the floor they were meant to hit (DG-321).
3. Would this call skip or disable the git hooks themselves (DG-465) —
   ``--no-verify`` and its ``-n`` spelling on commit, ``git -c
   core.hooksPath=…`` or ``git config core.hooksPath``, ``SKIP=`` /
   ``DRUNKEN_NO_REGISTERED_PROJECTS=`` on a git command, ``pre-commit
   uninstall``, or removing, moving, chmod-ing or editing ``.git/hooks``
   directly? A settings.json rule matches a command by prefix and never sees
   a flag mid-command, so this one is hardcoded here instead.

Everything else gets **silence**, which is not the same as ``allow``. Exit 0
with no ``permissionDecision`` means "no opinion", and the harness carries on
exactly as it would have. The hook never widens permission: an allowlisted call
gets silence too, because the harness evaluates that same list and a second
authority saying the same thing is only a second thing to disagree.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Final, Optional

from . import permission_rules as pr

#: The tool families that are meaningless without one input key. A ``Bash``
#: with no command and a ``Read`` with no path are not calls this hook can
#: judge -- they are calls it failed to read.
#:
#: Keyed on :func:`~core.permission_rules.canonical_tool`'s output, not on a
#: tool's own spelling. DG-334: the write side was once guarded under ``Write``
#: and stopped being guarded the day the name it arrived under became ``Edit``,
#: because the guard was keyed on a spelling rather than on the family.
UNREADABLE_KEYS: Final = {
    "Bash": ("command",),
    "Read": pr.PATH_KEYS,
    pr.EDIT_TOOL_CANONICAL: pr.PATH_KEYS,
}

DENIED_BY_RULE = (
    "Blocked by a deny rule in .claude/settings.json. Nothing overrides this "
    "one — if it genuinely needs to happen, raise it with the Boss directly."
)

UNREADABLE = (
    "This call carried no command or path, so no rule could be evaluated "
    "against it — including the deny rules. Refused rather than waved through: "
    "a call the hook cannot read is the one case where silence is the most "
    "dangerous answer it could give."
)

HOOK_FLOOR_BYPASS = (
    "Blocked by the hook floor itself, not by a settings.json rule: this call "
    "would skip or disable the git hooks (--no-verify, SKIP=, core.hooksPath, "
    "pre-commit uninstall, or removing/editing .git/hooks). Nothing overrides "
    "this one — raise it with the Boss directly if it genuinely needs to happen."
)

#: Git subcommands whose own `--no-verify` flag skips a hook (DG-465). `-n` is
#: only a `--no-verify` synonym for `commit`; on `push` it means dry-run, which
#: must stay undenied, so it gets its own narrower check below.
_HOOK_SKIPPING_SUBCOMMANDS: Final = (
    "commit",
    "push",
    "merge",
    "rebase",
    "cherry-pick",
    "am",
    "revert",
)

#: The shortest prefix of ``--no-verify`` the real git binary resolves without
#: complaint (verified by hand against git on this host, recorded in
#: ``tests/test_hook.py``): ``--no-ver`` is still ambiguous with
#: ``--no-verbose``, ``--no-veri`` is not. Git's own unambiguous-prefix
#: matching means ``--no-verif`` skips the hook exactly like the full
#: spelling, so a settings-shaped exact-string rule could never catch it --
#: this has to walk the same prefix rule git does.
_NO_VERIFY_SHORTEST_PREFIX: Final = "--no-veri"
_NO_VERIFY_FULL: Final = "--no-verify"

#: Verbs that overwrite, replace or relocate a file or directory in place,
#: beyond `rm`/`mv`/`chmod`: adversarial review (DG-465 follow-up) found a
#: hook file can be silently defused by any of these too, with `.git/hooks`
#: as the destination rather than an argument `rm` et al. take directly.
#: Round 2 adds the Windows-native verbs (`cmd.exe`'s `del`/`erase`/`rd`/
#: `rmdir`/`ren`/`move`/`copy`/`xcopy`/`mklink`) and the PowerShell cmdlets
#: an operator on this platform would actually reach for -- the first pass
#: only covered POSIX. All compared case-insensitively via `_has_word`, so
#: `Remove-Item` and `remove-item` are the same check.
_HOOKS_DIR_MUTATING_VERBS: Final = (
    "rm",
    "mv",
    "cp",
    "chmod",
    "ln",
    "tee",
    "install",
    "rsync",
    "truncate",
    "del",
    "erase",
    "rd",
    "rmdir",
    "ren",
    "move",
    "copy",
    "xcopy",
    "mklink",
    "remove-item",
    "move-item",
    "rename-item",
    "copy-item",
    "set-content",
    "add-content",
    "out-file",
    "new-item",
    "clear-content",
)

#: Interpreters whose `-c`/one-liner form can rewrite a file without ever
#: naming `rm`/`cp`/etc. Gated on a write-signal token too (below), not on
#: presence alone -- `python -c "print(1+1)"` must stay undenied even though
#: `python` is an interpreter.
_INTERPRETER_WORDS: Final = ("python", "python3", "ruby", "node", "perl", "awk")

#: A write, open-for-write or unlink call inside an interpreter one-liner.
_INTERPRETER_WRITE_SIGNAL: Final = re.compile(
    r"open\s*\([^)]*[\"'][waxWAX]|os\.(remove|unlink)|\.unlink\(|\.write\(|truncate\(",
)

#: Env vars that make `pre-commit` or the registry guard stand aside for one
#: invocation. Matched only when a `git` command rides along in the same
#: shell segment -- see the module docstring on why that scope is the point.
#: Compared case-insensitively: Windows environment variable names are
#: case-insensitive, so `skip=x` disables the same hook `SKIP=x` does there.
_HOOK_SKIPPING_ENV_VARS: Final = ("SKIP", "DRUNKEN_NO_REGISTERED_PROJECTS")

#: `.git/hooks` or `.git\hooks`, any case, matched in a path or a shell
#: argument. Windows spells the separator with a backslash and is
#: case-insensitive on its filesystem, so both have to be caught here rather
#: than assumed away as "the same thing someone else normalises".
_HOOKS_DIR_PATTERN: Final = re.compile(r"\.git[\\/]+hooks", re.IGNORECASE)

#: `.git/config` (or `.git\config`), any case -- where `core.hooksPath` is
#: actually stored, so an in-place edit of the file is the same bypass as
#: `git config core.hooksPath` without ever naming git.
_GIT_CONFIG_FILE_PATTERN: Final = re.compile(r"\.git[\\/]+config", re.IGNORECASE)


def _has_word(segment: str, word: str) -> bool:
    """Whether *word* appears in *segment* as its own token.

    Greedy on purpose, matching the module's own deny philosophy: a prefix
    or suffix of word/hyphen characters would make this a different word
    (``push`` inside ``pushing``, ``-n`` inside ``-name``), so those are
    excluded; everything else -- quotes, surrounding punctuation, position in
    the string -- is not, because a false positive here costs a prompt and a
    false negative costs the floor.
    """
    pattern = rf"(?<![\w-]){re.escape(word)}(?![\w-])"
    return re.search(pattern, segment, re.IGNORECASE) is not None


def _consume_inside_quotes(
    segment: str, i: int, quote: str
) -> tuple[int, Optional[str], bool]:
    """Advance past one unit of *segment* while inside *quote*, starting at
    *i*. Returns ``(new_i, literal_to_append, quote_just_ended)`` --
    *literal_to_append* is ``None`` for a line continuation or the closing
    quote itself, neither of which becomes part of the token's text.

    Split out of :func:`_tokenize_shell_words` to keep that function's own
    branching under the project's complexity limit; the two line-
    continuation and double-quote-escape checks live here instead of inline.
    """
    n = len(segment)
    char = segment[i]
    if quote == '"':
        span = pr.line_continuation_length(segment, i)
        if span:
            return i + span, None, False
        if char == "\\" and i + 1 < n:
            return i + 2, segment[i + 1], False
    if char == quote:
        return i + 1, None, True
    return i + 1, char, False


def _consume_quoted_token_char(
    segment: str, i: int, quote: str, current: list[str]
) -> tuple[int, Optional[str]]:
    """:func:`_consume_inside_quotes`, applied -- appends to *current* in
    place and returns ``(new_i, still_the_same_quote_or_None)``. Folds that
    function's three-part result into the two things
    :func:`_tokenize_shell_words`'s own loop needs, keeping its branching
    under the project's complexity limit.
    """
    new_i, literal, ended = _consume_inside_quotes(segment, i, quote)
    if literal is not None:
        current.append(literal)
    return new_i, (None if ended else quote)


def _tokenize_shell_words(segment: str) -> list[str]:
    """Split *segment* into words the way a real shell hands them to argv:
    quotes group characters into one token and are then removed, rather
    than creating a word boundary or disappearing the token altogether.

    DG-465 round 3, twice over. The first version of this masked quoted
    spans to *spaces* for tokenising, which made ``" ".split()`` drop a
    quoted ``-C``/``-c`` argument as a token entirely -- ``git -C "."
    commit --no-verify`` then mis-walked past ``commit`` itself looking for
    the global option's value, and the whole check missed. Masking to a
    non-space filler fixed that, but still could not tell ``"git"`` (quoted,
    but still naming the real git binary) from quoted *content* -- a
    property check (quote every argument of an already-denied command and
    confirm it is still denied) caught that masking can never distinguish
    the two by text alone. Real tokenising does: ``"git"`` becomes the
    token ``git``, exactly as `_git_subcommand` expects, because that is
    exactly what the shell would actually run.

    The one case this must *not* resolve literally is a flag-taking value
    -- ``-m "x -n"`` must keep ``x -n`` as inert text, not a ``-n`` flag.
    That is handled by position, not by quoting: see
    :func:`_tokens_eligible_for_flag_matching`.

    A backslash line continuation
    (:func:`~core.permission_rules.line_continuation_length`) vanishes
    entirely rather than being read as an escaped newline, both unquoted and
    inside double quotes -- ``--no-ver`` + a continuation + ``ify`` is one
    token, ``--no-verify``, split across two physical lines exactly as
    git's own command line would see it. Single quotes are unaffected: a
    backslash has no special meaning there at all, so both the backslash
    and the newline stay in the token literally, inert.
    """
    tokens: list[str] = []
    current: list[str] = []
    in_token = False
    quote: Optional[str] = None
    i = 0
    n = len(segment)
    while i < n:
        char = segment[i]
        if quote is not None:
            i, quote = _consume_quoted_token_char(segment, i, quote, current)
            continue
        span = pr.line_continuation_length(segment, i)
        if span:
            i += span
            continue
        if char.isspace():
            if in_token:
                tokens.append("".join(current))
                current = []
                in_token = False
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            in_token = True
            i += 1
            continue
        if char == "\\" and i + 1 < n:
            current.append(segment[i + 1])
            in_token = True
            i += 2
            continue
        current.append(char)
        in_token = True
        i += 1
    if in_token:
        tokens.append("".join(current))
    return tokens


#: Flags whose very next token is opaque content, never a flag, regardless
#: of what it contains -- `-m "x -n"` passes the commit message `x -n`, not
#: a `-n` flag, whether or not that message happens to be quoted.
_MESSAGE_VALUE_FLAGS: Final = ("-m", "--message")


def _tokens_eligible_for_flag_matching(tokens: list[str]) -> list[str]:
    """*tokens* with the value following each :data:`_MESSAGE_VALUE_FLAGS`
    flag removed, so it is never read as a flag of its own."""
    eligible: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        eligible.append(tok)
        if tok in _MESSAGE_VALUE_FLAGS:
            skip_next = True
    return eligible


#: A short-flag cluster: one dash, then only letters -- `-an`, `-nm`, `-am`.
#: Deliberately excludes `--` long options and anything with `=`, so it never
#: collides with the long-flag check below.
_SHORT_FLAG_CLUSTER: Final = re.compile(r"^-[A-Za-z]+$")

#: git's own global options that consume a separate following token --
#: `-C <dir>`, `-c <key=val>`, and the long spellings when given as two
#: words rather than `--opt=value` (which is already one self-contained
#: token and needs no special handling). Needed to walk past them when
#: finding the actual subcommand; see :func:`_git_subcommand`.
_GIT_GLOBAL_OPTS_WITH_SEPARATE_ARG: Final = (
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
)


def _git_subcommand(tokens: list[str]) -> Optional[str]:
    """The git subcommand *tokens* actually invokes -- the first non-option
    token after ``git`` and git's own global options.

    DG-465 round 2: matching ``commit`` or ``-n`` anywhere in the segment
    denied ``git log --grep=commit -n 1``, an ordinary read-only log command
    that only happens to mention the word "commit" and take a `-n` count.
    Deny rules cannot be overridden, so a false positive here is not a
    prompt -- it is a lockout, and this is the fix: find the real
    subcommand rather than scanning the whole segment for the word.

    A git global option not in :data:`_GIT_GLOBAL_OPTS_WITH_SEPARATE_ARG`
    (``--no-pager``, or even a nonsense one) is assumed to take no separate
    argument and is skipped on its own -- greedy on purpose, same as the
    rest of this module: skipping too much costs a missed subcommand
    (silence), skipping too little costs a prompt.
    """
    try:
        idx = next(i for i, tok in enumerate(tokens) if tok.lower() == "git")
    except StopIteration:
        return None
    i = idx + 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in _GIT_GLOBAL_OPTS_WITH_SEPARATE_ARG:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        return tok
    return None


def _is_no_verify_long_flag(token: str) -> bool:
    """Whether *token* is ``--no-verify`` or an unambiguous prefix of it that
    the real git binary accepts (see :data:`_NO_VERIFY_SHORTEST_PREFIX`)."""
    lowered = token.lower()
    if len(lowered) < len(_NO_VERIFY_SHORTEST_PREFIX):
        return False
    return _NO_VERIFY_FULL.startswith(lowered)


def _denies_no_verify(segment: str) -> bool:
    """``--no-verify`` (or its unambiguous prefix) on commit/push/merge/
    rebase/cherry-pick/am/revert, or `-n` -- alone or bundled into a short-
    flag cluster like ``-an``/``-nm``/``-anm`` -- on ``commit`` specifically.

    Gated on the *actual* git subcommand (see :func:`_git_subcommand`), not
    on the word appearing anywhere in the segment -- `git tag -n`, `git
    branch -n` and `git log -n 3` all take a `-n` that has nothing to do
    with `--no-verify` and must stay undenied. Tokenised the way a real
    shell would (:func:`_tokenize_shell_words`), so quoting any argument --
    including the word ``git`` itself -- changes nothing; the one value
    this must not read literally, a `-m` message, is excluded by position
    rather than by quoting (:func:`_tokens_eligible_for_flag_matching`), so
    `-m "x -n"` stays an ordinary commit either way.
    """
    tokens = _tokenize_shell_words(segment)
    subcommand = _git_subcommand(tokens)
    if subcommand is None:
        return False
    subcommand_lower = subcommand.lower()
    if subcommand_lower not in _HOOK_SKIPPING_SUBCOMMANDS:
        return False

    scan_tokens = _tokens_eligible_for_flag_matching(tokens)
    if any(_is_no_verify_long_flag(tok) for tok in scan_tokens):
        return True
    if subcommand_lower != "commit":
        return False
    return any(
        _SHORT_FLAG_CLUSTER.match(tok) and "n" in tok[1:].lower() for tok in scan_tokens
    )


def _denies_hooks_path_config(segment: str) -> bool:
    """``git -c core.hooksPath=…`` or ``git config [--global] core.hooksPath``,
    or editing ``core.hooksPath`` out of ``.git/config`` directly -- a ``sed
    -i`` targeting the file never has to spell ``core.``, so a bare
    ``hooksPath`` is enough when the same segment targets ``.git/config``.

    Greedy about read vs. write on purpose: a bare ``git config --get
    core.hooksPath`` is denied too rather than carved out as an exemption --
    the deny side of this module always trades a possible extra prompt for
    not missing a real bypass.
    """
    lowered = segment.lower()
    if "core.hookspath" in lowered and _has_word(segment, "git"):
        return True
    return "hookspath" in lowered and bool(_GIT_CONFIG_FILE_PATTERN.search(segment))


#: Matches the run of ``VAR=value`` assignments a shell allows before the
#: command they apply to -- the only place an env-var-on-a-git-command can
#: actually take effect. Anchored to the start of the segment on purpose: a
#: commit message that happens to contain the text ``SKIP=`` is not a bypass
#: attempt, and matching the whole segment indiscriminately would deny it.
#: ``env VAR=value cmd`` and a leading ``export VAR=value;`` both put the
#: assignment in the same place a shell does: right before the command it
#: applies to, so both are covered by allowing `env`/`export` to lead it.
_ENV_ASSIGNMENT_PREFIX: Final = re.compile(
    r"^(?:(?:env|export)\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*"
)


def _denies_env_skip(segment: str) -> bool:
    """``SKIP=`` or ``DRUNKEN_NO_REGISTERED_PROJECTS=`` on a git command,
    plain, via ``env``, or via a leading ``export`` -- compared
    case-insensitively, since Windows environment variable names are."""
    if not _has_word(segment, "git"):
        return False
    prefix = _ENV_ASSIGNMENT_PREFIX.match(segment)
    leading = (prefix.group(0) if prefix else "").lower()
    return any(f"{var.lower()}=" in leading for var in _HOOK_SKIPPING_ENV_VARS)


def _denies_precommit_uninstall(segment: str) -> bool:
    return re.search(r"pre-commit\s+uninstall", segment, re.IGNORECASE) is not None


#: Output redirected into the hooks dir: `>`, `>>`, or `dd`'s `of=`. Not tied
#: to any particular command -- `echo`, `cat`, `printf`, anything -- because
#: the redirection operator is what writes, not the command in front of it.
_HOOKS_DIR_REDIRECT_PATTERN: Final = re.compile(
    r">>?\s*[\"']?\S*\.git[\\/]+hooks", re.IGNORECASE
)
_HOOKS_DIR_DD_OF_PATTERN: Final = re.compile(
    r"\bof=[\"']?\S*\.git[\\/]+hooks", re.IGNORECASE
)


def _denies_hooks_dir_mutation(segment: str) -> bool:
    """Any shape that overwrites, relocates or defuses `.git/hooks` or a file
    in it: the verbs in :data:`_HOOKS_DIR_MUTATING_VERBS` (POSIX, Windows-
    native, and PowerShell) with the path as an argument -- including inside
    a `powershell -Command "..."`/`pwsh -c`/`cmd /c "..."` wrapper, since this
    check is deliberately quote-blind -- output redirected (`>`, `>>`, `dd
    of=`) into it, `sed -i`/`perl -pi`/`awk -i inplace` editing a file under
    it in place, or an interpreter one-liner (`python -c "..."`) that opens,
    writes or unlinks a path under it. A read -- `cat .git/hooks/pre-commit`,
    `ls .git/hooks`, `Get-Content .git/hooks/pre-commit`, `type
    .git\\hooks\\pre-commit` -- matches none of these and stays undenied.
    """
    if _HOOKS_DIR_REDIRECT_PATTERN.search(segment):
        return True
    if _HOOKS_DIR_DD_OF_PATTERN.search(segment):
        return True
    if not _HOOKS_DIR_PATTERN.search(segment):
        return False
    if _has_word(segment, "sed") and re.search(r"-i\b", segment):
        return True
    if _has_word(segment, "perl") and re.search(r"-\w*i\b", segment):
        return True
    if _has_word(segment, "awk") and _has_word(segment, "inplace"):
        return True
    if any(_has_word(segment, word) for word in _INTERPRETER_WORDS) and (
        _INTERPRETER_WRITE_SIGNAL.search(segment)
    ):
        return True
    return any(_has_word(segment, verb) for verb in _HOOKS_DIR_MUTATING_VERBS)


#: ``export VAR=value`` as its own segment, rather than leading a command
#: it shares a segment with. `export SKIP=ruff; git commit` is two segments
#: once `split_command` sees the `;` -- the assignment outlives it in a real
#: shell, so this is tracked across segments rather than within one.
_EXPORTED_HOOK_SKIP_VAR: Final = re.compile(
    r"^export\s+(?:" + "|".join(_HOOK_SKIPPING_ENV_VARS) + r")=",
    re.IGNORECASE,
)


#: ``cd .git/hooks`` (or the Windows-path spelling) as its own segment.
#: Matched on the whole segment, not just a word -- the point is that this
#: segment's only job is to change directory into the hooks dir.
_CD_INTO_HOOKS_DIR: Final = re.compile(
    r"^cd\s+[\"']?\S*\.git[\\/]+hooks[\"']?/?$", re.IGNORECASE
)

#: A `cd` (any destination) or `popd` as its own segment -- the only two
#: words that change (or restore) the shell's working directory, so the
#: only two that are allowed to *reset* `cwd_is_hooks_dir` in
#: :func:`_bypasses_hook_floor_bash`.
_CD_OR_POPD: Final = re.compile(r"^(?:cd|popd)\b", re.IGNORECASE)


def _bypasses_hook_floor_bash(command: str) -> bool:
    """Scan every segment a Bash call will actually run.

    :func:`~core.permission_rules.segments_with_leading_operator` is
    quote-aware and splits on ``&&``, ``;``, ``|``, ``(``/``)`` and command
    substitution, same as :func:`~core.permission_rules.is_denied` relies on
    -- so a bypass hidden after an operator or inside a subshell is scanned
    the same as one typed on its own. DG-474: this used to be a second copy
    of that same scan, kept here only because this check needs the operator
    that joined each segment and the shared module's public shape used to
    throw it away -- the operator now rides along in the one, shared
    function instead of a second implementation of the scan itself.

    Three kinds of state are carried *across* segments rather than found in
    one, each scoped no wider than the real shell semantics it is standing
    in for:

    - An ``export`` outlives the `;` that follows it (unscoped -- a real
      shell carries it for the rest of the session, not just one segment).
    - A `cd` into the hooks dir changes the working directory for every
      later segment *until the next `cd`/`popd`* -- so `cwd_is_hooks_dir` is
      reset, not just set, by any `cd`/`popd` that is not back into the
      hooks dir (DG-465 round 3: it previously was never reset, so `cd
      .git/hooks && cd .. && mv a b` -- which never touches the hooks dir at
      all -- was wrongly denied).
    - A hooks-dir path echoed into a pipe only reaches the *next* segment,
      not every later one -- `echo .git/hooks | xargs rm -rf` is a real
      bypass, but `cat .git/hooks/pre-commit; find . | xargs mv x y` is an
      unrelated read followed by an unrelated pipe, and round 3's first
      version denied it anyway because the flag was never scoped to the
      `|` that actually carries the value forward.

    A true variable indirection (``H=.git/hooks; mv $H /tmp/``) is not
    attempted here -- see the PR body's out-of-scope list.
    """
    segment_pairs = pr.segments_with_leading_operator(command) or [("", command)]
    exported_skip_var = False
    cwd_is_hooks_dir = False
    pending_hooks_path = False
    for operator, segment in segment_pairs:
        stripped = segment.strip()
        piped_from_hooks_path = pending_hooks_path and operator == "|"
        pending_hooks_path = False

        if _EXPORTED_HOOK_SKIP_VAR.match(stripped):
            exported_skip_var = True
        if (
            _denies_no_verify(segment)
            or _denies_hooks_path_config(segment)
            or _denies_env_skip(segment)
            or (exported_skip_var and _has_word(segment, "git"))
            or _denies_precommit_uninstall(segment)
            or _denies_hooks_dir_mutation(segment)
        ):
            return True
        if cwd_is_hooks_dir and any(
            _has_word(segment, verb) for verb in _HOOKS_DIR_MUTATING_VERBS
        ):
            return True
        if (
            piped_from_hooks_path
            and _has_word(segment, "xargs")
            and any(_has_word(segment, verb) for verb in _HOOKS_DIR_MUTATING_VERBS)
        ):
            return True

        if _CD_OR_POPD.match(stripped):
            cwd_is_hooks_dir = bool(_CD_INTO_HOOKS_DIR.match(stripped))
        if _HOOKS_DIR_PATTERN.search(segment):
            pending_hooks_path = True
    return False


def _bypasses_hook_floor_edit(tool_input: dict[str, Any]) -> bool:
    """A Write/Edit/MultiEdit/NotebookEdit call targeting ``.git/hooks``."""
    return any(
        isinstance(tool_input.get(key), str)
        and _HOOKS_DIR_PATTERN.search(tool_input[key])
        for key in pr.PATH_KEYS
    )


def _bypasses_hook_floor(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """DG-465, the floor's third rule: the shapes that disable a hook rather
    than going around it honestly. Hardcoded here, not read from
    ``settings.json`` -- a settings rule matches a command by prefix and
    cannot see a flag mid-command, which is exactly the shape every one of
    these takes."""
    canonical = pr.canonical_tool(tool_name)
    if canonical == "Bash":
        return _bypasses_hook_floor_bash(str(tool_input.get("command", "")))
    if canonical == pr.EDIT_TOOL_CANONICAL:
        return _bypasses_hook_floor_edit(tool_input)
    return False


@dataclass(frozen=True)
class Decision:
    """``None`` means "no opinion" — the harness carries on as usual."""

    permission: Optional[str]
    reason: str = ""


def _is_unreadable(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Whether a call arrived without the one field that gives it meaning.

    DG-321. A call whose command or path is missing is not just noise:
    ``.get(name, "")`` yields an empty string, and an empty string matches no
    rule at all. Deny rules are rules. ``is_denied("Bash", {"command": ""},
    rules.deny)`` is ``False``, so the call would fall straight past the floor
    it was meant to hit.

    Narrow on purpose. Only the three tool families in :data:`UNREADABLE_KEYS`
    are checked; a tool that legitimately carries neither a command nor a path
    is not the hook's business, and denying it would break every session to
    close a hole that is not there.
    """
    keys = UNREADABLE_KEYS.get(pr.canonical_tool(tool_name))
    if keys is None:
        return False
    return not any(str(tool_input.get(key, "")).strip() for key in keys)


def decide(payload: dict[str, Any], rules: pr.Rules) -> Decision:
    """Resolve one tool call. Pure.

    Order matters and is asserted in the tests: the floor first, then silence.
    """
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    # 1. Deny, before anything else and regardless of mode.
    if pr.is_denied(tool_name, tool_input, rules.deny):
        return Decision("deny", DENIED_BY_RULE)

    # 2. A call that cannot be read cannot have been checked against the deny
    # list above, so it gets the same treatment rather than the benefit of the
    # doubt. Before `bypassPermissions` for the same reason step 1 is: that mode
    # turns off prompting, not the floor.
    if _is_unreadable(tool_name, tool_input):
        return Decision("deny", UNREADABLE)

    # 3. DG-465: the floor's own rule, not a settings.json one. Disabling the
    # gate is exactly the one thing a settings rule cannot be trusted to deny
    # for itself -- it matches by prefix and never sees a flag mid-command.
    if _bypasses_hook_floor(tool_name, tool_input):
        return Decision("deny", HOOK_FLOOR_BYPASS)

    # 4. Everything else is the harness's own business. Silence, not `allow`:
    # the hook has a floor to enforce and no authority to widen anything.
    return Decision(None)


def render(decision: Decision) -> str:
    """Serialise to the documented PreToolUse output shape.

    A ``permissionDecision`` of ``null`` is not silence -- it is an opinion
    the harness has to interpret. When there is no decision the key is absent
    entirely, and only the reason rides along as a system message.
    """
    specific: dict[str, Any] = {"hookEventName": "PreToolUse"}
    if decision.permission is not None:
        specific["permissionDecision"] = decision.permission
        specific["permissionDecisionReason"] = decision.reason
    claude_out: dict[str, Any] = {"hookSpecificOutput": specific}
    if decision.permission is None and decision.reason:
        claude_out["systemMessage"] = decision.reason
    return json.dumps(claude_out)


def main(stdin_text: Optional[str] = None) -> int:
    """Read one hook event, print at most one decision, always exit 0.

    Exit 0 even on failure, deliberately. Exit 2 would block the tool call, and
    a hook that crashes on an input it did not expect must not take an
    unrelated tool call down with it -- principle 8, in the place where
    failing loudly would be worst. Anything this function cannot understand
    becomes silence, and the harness prompts exactly as it did before.
    """
    try:
        raw = sys.stdin.read() if stdin_text is None else stdin_text
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hook payload was not a JSON object")

        cwd = payload.get("cwd") or os.getcwd()
        decision = decide(payload, pr.load_layered_rules(cwd))
    except Exception as exc:  # noqa: BLE001 - see docstring
        decision = Decision(None, f"permission hook stood aside: {exc}")

    print(render(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
