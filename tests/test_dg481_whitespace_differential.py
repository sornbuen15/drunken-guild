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

#: Whitespace fills: each collapses to one plain space under the new code;
#: NBSP and a lone CR are the two the ticket says must NOT collapse.
_NORMALISING_FILLS: Final = ["\t", "\f", "\v", "  ", "\t\t", " \t "]
_NON_NORMALISING_FILLS: Final = ["\xa0", "\r"]


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


def _has_unquoted_normalising_whitespace(command: str) -> bool:
    """Whether *command* contains a tab, form feed, vertical tab or a run of
    two-or-more plain spaces, outside any quoted span -- the only thing the
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
        if char in ("\t", "\f", "\v"):
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
