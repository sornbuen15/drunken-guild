# mypy: ignore-errors
"""The SessionStart hook template, templates/claude-session-hook.md.

DG-411: templates/ gains a Claude-only extra — a SessionStart hook snippet for
`.claude/settings.json` that injects the guild reminder at session start. The
Boss places and installs it; nothing here does.

Three things can go wrong with a snippet nobody runs until the Boss pastes it:

1. The JSON block does not parse, so the paste fails at the first attempt.
2. The reminder text breaks the `command` string's own quoting — the snippet
   wraps it in single quotes for the shell, so a stray apostrophe in the text
   corrupts the command it sits inside.
3. The `command` does more than print the reminder: a network call, a file
   write or a secret read running at every session start would be a standing
   liability nobody asked for.

This file is deliberately dumb about anything else in the template — prose,
headings, which skills it names — because that is for a human reading the
doc, not a parser.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "templates" / "claude-session-hook.md"

#: The reminder is wrapped in single quotes inside the shell command
#: (`printf '%s\n' '<json>'`). An apostrophe in the text would close that
#: quoting early and leave the rest as a syntax error the Boss only finds
#: after pasting it in.
MAX_REMINDER_CHARS = 600


def _template_text() -> str:
    assert TEMPLATE_PATH.exists(), (
        f"{TEMPLATE_PATH} is missing. DG-411 ships a SessionStart hook "
        "template at this path."
    )
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _json_block() -> str:
    """The fenced ```json block carrying the settings.json snippet."""
    text = _template_text()
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    assert match, (
        f"{TEMPLATE_PATH} has no fenced ```json block. The Boss copies JSON, "
        "not prose, into settings.json."
    )
    return match.group(1)


def _hook_command() -> str:
    """The `command` string inside the parsed hooks block."""
    parsed = json.loads(_json_block())
    command = parsed["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert isinstance(command, str)
    return command


def _reminder_text() -> str:
    """The `additionalContext` string the command's printf emits."""
    command = _hook_command()
    match = re.search(r"\"additionalContext\":\"(.*)\"\}\}", command)
    assert match, (
        "Could not find additionalContext inside the command string — the "
        "template's JSON-inside-a-shell-string shape may have changed."
    )
    return match.group(1)


def test_json_block_parses() -> None:
    """The snippet the Boss pastes must be valid JSON on the first try."""
    parsed = json.loads(_json_block())
    assert "hooks" in parsed, (
        "templates/claude-session-hook.md's JSON block has no top-level "
        "'hooks' key, so it cannot be merged into settings.json's own."
    )
    assert "SessionStart" in parsed["hooks"]


def test_reminder_is_under_600_characters() -> None:
    reminder = _reminder_text()
    assert len(reminder) < MAX_REMINDER_CHARS, (
        f"Reminder is {len(reminder)} characters, over the "
        f"{MAX_REMINDER_CHARS}-character budget set for a SessionStart "
        "hook's additionalContext."
    )


def test_reminder_has_no_apostrophe() -> None:
    """The command string wraps the reminder in single quotes for the shell.

    An apostrophe in the text closes that quoting early, and the Boss only
    discovers it when the pasted hook fails at session start.
    """
    reminder = _reminder_text()
    assert "'" not in reminder, (
        "The reminder text contains an apostrophe, which would break the "
        "single-quoted shell string the command wraps it in."
    )


def test_command_is_a_pure_printf() -> None:
    """No network call, file write or secret read runs at every session
    start. The command may only print.

    The reminder text itself is free to contain shell-looking punctuation —
    a semicolon between clauses, a slash in `/build` — because it sits
    *inside* the single-quoted JSON argument, where the shell never
    interprets it. What must stay pure is everything **outside** those
    quotes: splitting on `'` isolates the quoted segments (odd indices) from
    the shell-level ones (even indices), and only the latter are checked.
    """
    command = _hook_command()
    assert command.strip().startswith("printf "), (
        f"command does not start with 'printf ': {command!r}. An agent "
        "never places or installs a hook; the template must still only do "
        "the one safe thing it claims to."
    )
    shell_level_segments = command.split("'")[0::2]

    forbidden = (
        "curl",
        "wget",
        "http",
        ">",
        "rm ",
        "cat ",
        ".env",
        "secret",
        "token",
        "$(",
        "`",
        "&&",
        "||",
        ";",
        "|",
    )
    for segment in shell_level_segments:
        for token in forbidden:
            assert token not in segment, (
                f"command's shell-level text contains {token!r} outside "
                f"any quoting: {segment!r}. Full command: {command!r}"
            )
