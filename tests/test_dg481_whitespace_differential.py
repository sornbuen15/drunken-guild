# mypy: ignore-errors
"""DG-481, acceptance (b): a differential run of the OLD matcher against the
NEW one, over a few hundred varied commands, must show differing verdicts
only where unquoted inter-word whitespace was the difference.

``_old_segments_with_leading_operator`` is a frozen copy of
``permission_rules.segments_with_leading_operator`` exactly as it read
immediately before this ticket's change -- DG-467's continuation handling
and DG-474's quote-aware operator splitting, no whitespace collapsing.

For `hook.decide` specifically, the old side is produced by monkeypatching
that one function back onto the real, shared module for the duration of one
call -- `hook.py` reads `pr.segments_with_leading_operator` through the same
module object `split_command` and `is_denied` do, so the patched call
exercises hook.py's *real* bypass-scan code path (DG-465's `--no-verify`,
`core.hooksPath`, `.git/hooks` checks and all), not a hand-written stand-in
for it.
"""

from __future__ import annotations

import itertools
import re
from typing import Final, Optional

import pytest

from core import hook
from core import permission_rules as pr

# ---------------------------------------------------------------------------
# The old implementation, frozen.
# ---------------------------------------------------------------------------

_OLD_TWO_CHAR_OPERATORS = ("&&", "||", "$(")
_OLD_ONE_CHAR_OPERATORS = (";", "|", "&", "\n", "`", "(", ")")


def _old_consume_quoted_char(command: str, i: int, quote: str, current: list) -> tuple:
    char = command[i]
    if quote == '"':
        span = pr.line_continuation_length(command, i)
        if span:
            return i + span, quote
        if char == "\\" and i + 1 < len(command):
            current.append(char)
            current.append(command[i + 1])
            return i + 2, quote
    current.append(char)
    return i + 1, (None if char == quote else quote)


def _old_segments_with_leading_operator(command: str) -> list:
    pairs: list = []
    current: list = []
    operator = ""
    quote: Optional[str] = None
    i = 0
    while i < len(command):
        char = command[i]

        if quote is not None:
            i, quote = _old_consume_quoted_char(command, i, quote, current)
            continue

        span = pr.line_continuation_length(command, i)
        if span:
            i += span
            continue

        if char == "\\" and i + 1 < len(command):
            current.append(char)
            current.append(command[i + 1])
            i += 2
            continue

        if char in ("'", '"'):
            quote = char
            current.append(char)
            i += 1
            continue

        pair = command[i : i + 2]
        if pair in _OLD_TWO_CHAR_OPERATORS:
            pairs.append((operator, "".join(current)))
            current = []
            operator = pair
            i += 2
            continue

        if char in _OLD_ONE_CHAR_OPERATORS:
            pairs.append((operator, "".join(current)))
            current = []
            operator = char
            i += 1
            continue

        current.append(char)
        i += 1

    pairs.append((operator, "".join(current)))
    return [(op, seg.strip()) for op, seg in pairs if seg.strip()]


def _old_split_command(command: str) -> list[str]:
    return [seg for _, seg in _old_segments_with_leading_operator(command)]


def _old_is_denied(tool_name: str, tool_input: dict, rules) -> bool:
    if tool_name != "Bash":
        segments = [tool_input]
    else:
        parts = _old_split_command(str(tool_input.get("command", "")))
        segments = (
            [{**tool_input, "command": p} for p in parts] if parts else [tool_input]
        )
    return any(
        rule.matches(tool_name, segment, strict=False)
        for segment in segments
        for rule in rules
    )


def _old_hook_decide(payload: dict, rules: pr.Rules, monkeypatch) -> "hook.Decision":
    """`hook.decide` with the shared splitter patched back to its pre-DG-481
    form for exactly this one call -- so every real code path inside
    `hook.decide` (the settings deny check *and* the DG-465 bypass scan)
    runs the old splitting logic, not a hand-written approximation of it."""
    with monkeypatch.context() as m:
        m.setattr(
            pr, "segments_with_leading_operator", _old_segments_with_leading_operator
        )
        return hook.decide(payload, rules)


# ---------------------------------------------------------------------------
# Corpus.
# ---------------------------------------------------------------------------

#: The five settings.json deny rules, unspliced.
_SETTINGS_DENY_RULES: Final = [
    pr.Rule.parse("Bash(git push --force:*)"),
    pr.Rule.parse("Bash(git push -f:*)"),
    pr.Rule.parse("Bash(git reset --hard:*)"),
    pr.Rule.parse("Bash(git clean -fd:*)"),
    pr.Rule.parse("Bash(rm -rf:*)"),
]

#: Base commands: the denied shapes, DG-465 bypass shapes, and ordinary,
#: harmless commands -- a mix wide enough that "only whitespace differs"
#: has something to prove.
_BASE_COMMANDS: Final = [
    "git push --force origin main",
    "git push -f origin main",
    "git reset --hard HEAD~1",
    "git clean -fd",
    "rm -rf /tmp/x",
    "git status",
    "git commit -m x",
    "git log --oneline -5",
    "echo hi && rm -rf /tmp/y",
    "git commit --no-verify -m x",
    "git -c core.hooksPath=x commit -m x",
    "SKIP=ruff git commit -m x",
    "cd .git/hooks && rm pre-commit",
    "grep 'a && b' file",
    'git commit -m "a  b"',
    "pre-commit uninstall",
    "ls -la",
    "cat .git/hooks/pre-commit",
]

#: Whitespace fills: each collapses to one plain space under the new code.
#: Round 2 (adversarial) moved NBSP from "must not collapse" to "must
#: collapse" -- see the docstring on `permission_rules._UNICODE_SPACE_SEPARATORS`
#: -- so it is a normalising fill now; a lone CR is still the only one that
#: must not collapse.
_NORMALISING_FILLS: Final = [
    "\t",
    "\f",
    "\v",
    "  ",
    "\t\t",
    " \t ",
    "\xa0",
    " ",
    "　",
]
_NON_NORMALISING_FILLS: Final = ["\r"]


def _variants(command: str) -> list[str]:
    out = [command]
    for fill in _NORMALISING_FILLS + _NON_NORMALISING_FILLS:
        if " " in command:
            out.append(command.replace(" ", fill, 1))
    return out


_CORPUS: Final = list(
    itertools.chain.from_iterable(_variants(c) for c in _BASE_COMMANDS)
)
_UNIQUE_CORPUS: Final = sorted(set(_CORPUS))


#: Round 1's tab/form-feed/vertical-tab plus round 2's NBSP and other
#: Unicode space separators -- imported from the real production set rather
#: than re-typed, so this test can never quietly drift from what the code
#: actually collapses.
_NORMALISING_CHARS: Final = frozenset(("\t", "\f", "\v")) | frozenset(
    pr._UNICODE_SPACE_SEPARATORS
)


def _has_unquoted_normalising_whitespace(command: str) -> bool:
    """Whether *command* contains a tab, form feed, vertical tab, a Unicode
    space separator (NBSP and friends -- round 2), or a run of
    two-or-more plain spaces, outside any quoted span -- the only things the
    new code treats differently from the old one."""
    quote: Optional[str] = None
    i = 0
    n = len(command)
    while i < n:
        char = command[i]
        if quote is not None:
            if char == quote:
                quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            i += 1
            continue
        if char in _NORMALISING_CHARS:
            return True
        if char == " " and i + 1 < n and command[i + 1] == " ":
            return True
        i += 1
    return False


@pytest.mark.parametrize("command", _UNIQUE_CORPUS)
def test_old_and_new_split_command_differ_only_on_normalising_whitespace(
    command: str,
) -> None:
    old = _old_split_command(command)
    new = pr.split_command(command)
    if old != new:
        assert _has_unquoted_normalising_whitespace(command), (
            f"split_command changed for {command!r} without any unquoted "
            "tab/form-feed/vertical-tab/double-space present"
        )


@pytest.mark.parametrize("command", _UNIQUE_CORPUS)
def test_old_and_new_is_denied_differ_only_on_normalising_whitespace(
    command: str,
) -> None:
    old = _old_is_denied("Bash", {"command": command}, _SETTINGS_DENY_RULES)
    new = pr.is_denied("Bash", {"command": command}, _SETTINGS_DENY_RULES)
    if old != new:
        assert _has_unquoted_normalising_whitespace(command), (
            f"is_denied verdict changed for {command!r} without any unquoted "
            "tab/form-feed/vertical-tab/double-space present"
        )


@pytest.mark.parametrize("command", _UNIQUE_CORPUS)
def test_old_and_new_hook_decide_differ_only_on_normalising_whitespace(
    command: str, monkeypatch
) -> None:
    rules = pr.Rules(deny=_SETTINGS_DENY_RULES)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    old = _old_hook_decide(payload, rules, monkeypatch).permission == "deny"
    new = hook.decide(payload, rules).permission == "deny"
    if old != new:
        assert _has_unquoted_normalising_whitespace(command), (
            f"hook.decide verdict changed for {command!r} without any unquoted "
            "tab/form-feed/vertical-tab/double-space present"
        )


def test_the_corpus_actually_exercises_the_fix() -> None:
    """A differential test that never finds a difference proves nothing --
    pin down that the corpus does contain commands the fix changes, so the
    tests above are not vacuously true."""
    changed = [
        c for c in _UNIQUE_CORPUS if _old_split_command(c) != pr.split_command(c)
    ]
    assert len(changed) >= 5, changed


def test_corpus_has_a_few_hundred_commands() -> None:
    assert len(_CORPUS) >= 100, len(_CORPUS)


# ---------------------------------------------------------------------------
# DG-481 round 2 (adversarial): `>|` is one operator, not `>` then a `|`
# pipe. A *separate* differential corpus and check, deliberately -- `>|` is
# not a whitespace difference at all, so mixing it into the corpus above
# would make `_has_unquoted_normalising_whitespace` responsible for
# explaining something it was never about.
# ---------------------------------------------------------------------------

_NOCLOBBER_CORPUS: Final = [
    "echo bad >| pre-commit",
    "cd .git/hooks && echo bad >| pre-commit",
    "echo bad > pre-commit",
    "echo bad >> pre-commit",
    "cat file | grep x",
    "echo x > file || true",
    "git status",
    "rm -rf /tmp/x",
    "echo x >| /tmp/y && rm -rf /tmp/z",
]


def _has_noclobber_redirect(command: str) -> bool:
    """Whether *command* contains `>|` outside quotes -- the one shape this
    round's splitter fix changes."""
    quote: Optional[str] = None
    i = 0
    n = len(command)
    while i < n:
        char = command[i]
        if quote is not None:
            if char == quote:
                quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            i += 1
            continue
        if char == "|" and i > 0 and command[i - 1] == ">":
            return True
        i += 1
    return False


@pytest.mark.parametrize("command", _NOCLOBBER_CORPUS)
def test_old_and_new_split_command_differ_only_on_noclobber_redirect(
    command: str,
) -> None:
    old = _old_split_command(command)
    new = pr.split_command(command)
    if old != new:
        assert _has_noclobber_redirect(command), (
            f"split_command changed for {command!r} without a `>|` present"
        )


def test_the_noclobber_corpus_actually_exercises_the_fix() -> None:
    changed = [
        c for c in _NOCLOBBER_CORPUS if _old_split_command(c) != pr.split_command(c)
    ]
    assert len(changed) >= 2, changed


# ---------------------------------------------------------------------------
# DG-476 round 3 (adversarial): the redirect-operator grammar.
# `hook._HOOKS_DIR_REDIRECT_PATTERN`/`_RELATIVE_REDIRECT_PATTERN` (round 2's
# regex pair) vs `hook._writing_redirect_targets` (round 3's deterministic
# scan) -- over every operator x gap x target combination the reviewer
# named, both against the direct-path question (does some target contain
# `.git/hooks`?) and the cwd-scoped one (is some target relative?).
# ---------------------------------------------------------------------------

_ROUND2_WRITING_REDIRECT_OPERATOR = r">{1,2}"
_ROUND2_HOOKS_DIR_REDIRECT_PATTERN = re.compile(
    rf"{_ROUND2_WRITING_REDIRECT_OPERATOR}(?!&)\s*[\"']?\S*\.git[\\/]+hooks",
    re.IGNORECASE,
)
_ROUND2_RELATIVE_REDIRECT_PATTERN = re.compile(
    rf"{_ROUND2_WRITING_REDIRECT_OPERATOR}(?!&)\s*[\"']?(?!/|~|[A-Za-z]:[\\/])\S"
)


def _old_denies_hooks_dir_redirect(segment: str) -> bool:
    return bool(_ROUND2_HOOKS_DIR_REDIRECT_PATTERN.search(segment))


def _old_denies_relative_redirect(segment: str) -> bool:
    return bool(_ROUND2_RELATIVE_REDIRECT_PATTERN.search(segment))


def _new_denies_hooks_dir_redirect(segment: str) -> bool:
    return any(
        hook._HOOKS_DIR_PATTERN.search(t)
        for t in hook._writing_redirect_targets(segment)
    )


def _new_denies_relative_redirect(segment: str) -> bool:
    return any(
        hook._is_relative_target(t) for t in hook._writing_redirect_targets(segment)
    )


_ROUND3_OPERATORS: Final = [">", ">>", ">|", "1>", "2>", "2>>", "&>", "&>>", "<>"]
_ROUND3_GAPS: Final = ["", " ", "  ", "\t"]
_ROUND3_RELATIVE_TARGETS: Final = [
    "pre-commit",
    ".git/hooks/pre-commit",
    "./.git/hooks/pre-commit",
    ".git\\hooks\\pre-commit",
    '".git/hooks/pre-commit"',
]
_ROUND3_ABSOLUTE_TARGETS: Final = ["/tmp/out", "/repo/.git/hooks/pre-commit"]

#: ``(command, operator, gap)`` -- the operator and gap are kept alongside
#: the command text so the test below can tell "a shape round 3 was meant
#: to change" (any gap, or an operator round 1/2 never saw: `>|`, a digit
#: or `&` prefix) from the one control case (`>` with no gap at all) that
#: must still agree with the old code, same as before this round.
_ROUND3_CORPUS: Final = [
    (f"echo bad {op}{gap}{target}", op, gap)
    for op in _ROUND3_OPERATORS
    for gap in _ROUND3_GAPS
    for target in _ROUND3_RELATIVE_TARGETS + _ROUND3_ABSOLUTE_TARGETS
]


def _is_round3_shape(operator: str, gap: str) -> bool:
    return gap != "" or operator != ">"


@pytest.mark.parametrize("command,operator,gap", _ROUND3_CORPUS)
def test_old_and_new_hooks_dir_redirect_differ_only_on_round3_shapes(
    command: str, operator: str, gap: str
) -> None:
    old = _old_denies_hooks_dir_redirect(command)
    new = _new_denies_hooks_dir_redirect(command)
    if old != new:
        assert _is_round3_shape(operator, gap), (
            f"{command!r} (operator={operator!r}, gap={gap!r}) changed "
            "verdict without a round-3 shape present"
        )


@pytest.mark.parametrize("command,operator,gap", _ROUND3_CORPUS)
def test_old_and_new_relative_redirect_differ_only_on_round3_shapes(
    command: str, operator: str, gap: str
) -> None:
    old = _old_denies_relative_redirect(command)
    new = _new_denies_relative_redirect(command)
    if old != new:
        assert _is_round3_shape(operator, gap), (
            f"{command!r} (operator={operator!r}, gap={gap!r}) changed "
            "verdict without a round-3 shape present"
        )


def test_round3_corpus_has_a_few_hundred_commands() -> None:
    assert len(_ROUND3_CORPUS) >= 200, len(_ROUND3_CORPUS)


def test_round3_corpus_actually_exercises_both_fixes() -> None:
    """Pin down that the corpus contains commands each check's old and new
    code actually disagree on -- a differential that never disagrees
    proves nothing."""
    hooks_dir_changed = [
        c
        for c, _, _ in _ROUND3_CORPUS
        if _old_denies_hooks_dir_redirect(c) != _new_denies_hooks_dir_redirect(c)
    ]
    relative_changed = [
        c
        for c, _, _ in _ROUND3_CORPUS
        if _old_denies_relative_redirect(c) != _new_denies_relative_redirect(c)
    ]
    assert len(hooks_dir_changed) >= 5, hooks_dir_changed
    assert len(relative_changed) >= 5, relative_changed
