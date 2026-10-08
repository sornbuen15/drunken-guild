# mypy: ignore-errors
"""DG-474: hook.py and permission_rules.py share one line-continuation and
segment splitter.

After DG-465, `hook.py` carried its own `_line_continuation_length` and
`_segments_with_leading_operator`, scanning the same quote and operator rules
as `permission_rules.split_command` (DG-467's `line_continuation_length`) a
second time. Two implementations of the same scan are two things that can
quietly disagree about the same command -- exactly the shape DG-467's own
`TestHookAndPermissionRulesAgreeOnSegments` pins down for the *deny-rule*
path. This file pins down the other path: the hook floor's own bypass
detection (`_bypasses_hook_floor_bash`), which used to run its own copy of
the scan rather than calling into `permission_rules` at all.

**Seen failing first**: `permission_rules.segments_with_leading_operator` did
not exist before this ticket -- every test below raised `AttributeError` the
first time it ran, because there was no shared place to ask for "the operator
before each segment" and the hook kept that logic to itself. That failure is
the proof two copies existed; a passing run here means there is now one.
"""

from __future__ import annotations

from typing import Final

import pytest

from core import hook
from core import permission_rules as pr

#: Ground truth captured from `hook.py`'s own (now-deleted) splitter before
#: this ticket touched anything -- see the PR body for how it was generated.
#: Covers every shape the ticket names: LF and CRLF continuations, quotes,
#: `||`, `&`, `|&`, `;;`, a bare newline, `$(..)`, backticks, unterminated
#: quotes, and a trailing backslash with nothing after it.
TABLE: Final[list[tuple[str, list[tuple[str, str]]]]] = [
    ("git commit --no-ver\\\nify -m x", [("", "git commit --no-verify -m x")]),
    ("git commit --no-ver\\\r\nify -m x", [("", "git commit --no-verify -m x")]),
    ('echo "hello world"', [("", 'echo "hello world"')]),
    ("echo 'hello world'", [("", "echo 'hello world'")]),
    ("a || b", [("", "a"), ("||", "b")]),
    ("a & b", [("", "a"), ("&", "b")]),
    ("a |& b", [("", "a"), ("&", "b")]),
    ("a ;; b", [("", "a"), (";", "b")]),
    ("a\nb", [("", "a"), ("\n", "b")]),
    ("echo $(rm -rf /)", [("", "echo"), ("$(", "rm -rf /")]),
    ("echo `rm -rf /`", [("", "echo"), ("`", "rm -rf /")]),
    ("echo 'unterminated", [("", "echo 'unterminated")]),
    ('echo "unterminated', [("", 'echo "unterminated')]),
    ("echo hi\\", [("", "echo hi\\")]),
    ("rm -rf .git/hoo\\\nks/pre-commit", [("", "rm -rf .git/hooks/pre-commit")]),
    ("git commit -m 'hello\\\nworld'", [("", "git commit -m 'hello\\\nworld'")]),
    (
        'git -C "a\\\nb" commit --no-verify -m x',
        [("", 'git -C "ab" commit --no-verify -m x')],
    ),
    ("echo hi && rm -r\\\nf /tmp/x", [("", "echo hi"), ("&&", "rm -rf /tmp/x")]),
    ("grep 'a \\\n&& b' file", [("", "grep 'a \\\n&& b' file")]),
]


class TestSharedSplitterMatchesTheOldHookOnlyBehaviour:
    """The table-driven test ACCEPTANCE asks for: both modules must give
    identical segments for the same inputs. There is only one module left to
    ask now -- `permission_rules` -- and this is what it must say."""

    @pytest.mark.parametrize("command,expected", TABLE)
    def test_segments_with_leading_operator(self, command, expected) -> None:
        assert pr.segments_with_leading_operator(command) == expected, (
            f"{command!r} must split into {expected!r}, the same way "
            "hook.py's own (now-deleted) copy of this scan used to"
        )

    @pytest.mark.parametrize("command,expected", TABLE)
    def test_split_command_agrees_on_the_segment_text(self, command, expected) -> None:
        """`split_command` throws away the operator but must agree on every
        segment's text -- the two are one scan now, not two."""
        assert pr.split_command(command) == [segment for _, segment in expected]


class TestHookHasNoSplitterOfItsOwnLeft:
    """DG-474's actual deliverable: not just "agrees", but "is the same
    code". A second implementation that happens to compute the same answer
    today is still a second implementation that can drift tomorrow."""

    def test_hook_module_does_not_define_its_own_line_continuation_length(self) -> None:
        assert not hasattr(hook, "_line_continuation_length"), (
            "hook.py must use permission_rules.line_continuation_length "
            "rather than keeping its own copy"
        )

    def test_hook_module_does_not_define_its_own_segment_splitter(self) -> None:
        assert not hasattr(hook, "_segments_with_leading_operator"), (
            "hook.py must use permission_rules.segments_with_leading_operator "
            "rather than keeping its own copy"
        )


#: The five `Bash` deny rules in `.claude/settings.json` (DG-467 names the
#: same five), each paired with a command it catches unspliced.
_FIVE_SETTINGS_DENY_RULES: Final = [
    ("Bash(git push --force:*)", "git push --force origin main"),
    ("Bash(git push -f:*)", "git push -f origin main"),
    ("Bash(git reset --hard:*)", "git reset --hard HEAD~1"),
    ("Bash(git clean -fd:*)", "git clean -fd"),
    ("Bash(rm -rf:*)", "rm -rf /tmp/x"),
]

#: Every command parametrized across the DG-465 floor-bypass test classes in
#: `tests/test_hook.py`, so the refactor is checked against the same battery
#: that earned five rounds of adversarial review -- not a hand-picked subset.
_DG465_FLOOR_BYPASS_COMMANDS: Final = [
    "git commit --no-verify -m x",
    "git push --no-verify",
    "git merge --no-verify branch",
    "git rebase --no-verify",
    "git cherry-pick --no-verify abc123",
    "git am --no-verify patch.mbox",
    "git revert --no-verify HEAD",
    "git commit -n -m x",
    "git -c core.hooksPath=/tmp/empty commit -m x",
    "git config core.hooksPath /tmp/empty",
    "git config --global core.hooksPath /tmp/empty",
    "SKIP=ruff git commit -m x",
    "DRUNKEN_NO_REGISTERED_PROJECTS=1 git commit -m x",
    "pre-commit uninstall",
    "rm -rf .git/hooks",
    "mv .git/hooks /tmp/hooks-backup",
    "chmod -R 000 .git/hooks",
    "echo hi && git commit --no-verify -m x",
    "git status; git push --no-verify",
    "true | git commit --no-verify -m x",
    "(git commit --no-verify -m x)",
    "echo start && (git push --no-verify) && echo end",
    'git commit --no-verify -m "message"',
    "git   commit   --no-verify",
    "git -C /some/dir commit --no-verify -m x",
    "GIT COMMIT --NO-VERIFY -m x",
    "rm -rf .git\\hooks",
    "mv .GIT\\HOOKS /tmp/x",
    "chmod -R 000 .Git/Hooks",
    "git --no-verify commit -m x",
    "rm -rf C:\\repo\\.git\\hooks",
    "FOO=bar SKIP=ruff git commit -m x",
    "git -c user.name=x -c core.hooksPath=/tmp/empty commit -m x",
    "git commit --no-ver\\\nify -m x",
    "git commit --no-ver\\\r\nify -m x",
    "git commit -a\\\nn",
    "git commit -a\\\r\nn",
    'git -C "a\\\nb" commit --no-verify -m x',
    "rm -rf .git/hoo\\\nks/pre-commit",
]


def _splice_every_gap(command: str, newline: str) -> list[str]:
    """*command* with a backslash + *newline* spliced at every character gap
    -- same technique `test_permission_rules.py::_splice_continuation` uses,
    generating one variant per gap rather than one hand-picked example."""
    return [
        command[:gap] + "\\" + newline + command[gap:]
        for gap in range(len(command) + 1)
    ]


#: Splicing a *second* backslash next to a command's own, pre-existing
#: backslash does not make a continuation -- `.git\hooks` + a spliced
#: ``\<newline>`` right after that backslash is an escaped backslash (one
#: literal ``\``) followed by a real, ordinary newline, exactly the shape
#: `test_permission_rules.py::test_escaped_backslash_then_a_real_newline_
#: still_splits` documents on purpose. That is correct shell-escaping
#: behaviour, not a bypass, so the every-gap property only makes sense on
#: commands that do not already contain a backslash -- the same restriction
#: DG-467's own `_DENY_RULE_COMMANDS` battery (all backslash-free) relies on.
_DG465_FLOOR_BYPASS_COMMANDS_BACKSLASH_FREE: Final = [
    command for command in _DG465_FLOOR_BYPASS_COMMANDS if "\\" not in command
]


class TestOldVsNewBehaviourOnALargeBattery:
    """SECURITY surface: a refactor can silently change what the deny floor
    denies. This compares the real production code (`hook.decide`, not a
    stub of either splitter) against the verdict the battery is *supposed*
    to produce, across hundreds of inputs: the DG-465 floor-bypass commands
    as written, plus every one of them with a continuation spliced into
    every gap, plus the five settings deny rules treated the same way.

    Every case here must still be denied after the refactor -- if any one
    of them silently became silence instead, that is the regression this
    ticket exists to catch.
    """

    NO_RULES = pr.Rules(allow=[], deny=[])

    def _settings_deny_rules(self) -> list[pr.Rule]:
        return [pr.Rule.parse(text) for text, _ in _FIVE_SETTINGS_DENY_RULES]

    @pytest.mark.parametrize("command", _DG465_FLOOR_BYPASS_COMMANDS)
    def test_floor_bypass_battery_as_written(self, command: str) -> None:
        decision = hook.decide(
            {"tool_name": "Bash", "tool_input": {"command": command}}, self.NO_RULES
        )
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize("command", _DG465_FLOOR_BYPASS_COMMANDS_BACKSLASH_FREE)
    @pytest.mark.parametrize("newline", ["\n", "\r\n"])
    def test_floor_bypass_battery_with_a_continuation_at_every_gap(
        self, command: str, newline: str
    ) -> None:
        for spliced in _splice_every_gap(command, newline):
            decision = hook.decide(
                {"tool_name": "Bash", "tool_input": {"command": spliced}},
                self.NO_RULES,
            )
            assert decision.permission == "deny", (
                f"a continuation spliced into {command!r} (-> {spliced!r}) "
                "must stay denied, not fall through to silence"
            )

    @pytest.mark.parametrize("rule_text,command", _FIVE_SETTINGS_DENY_RULES)
    @pytest.mark.parametrize("newline", ["\n", "\r\n"])
    def test_five_settings_deny_rules_with_a_continuation_at_every_gap(
        self, rule_text: str, command: str, newline: str
    ) -> None:
        rules = pr.Rules(allow=[], deny=[pr.Rule.parse(rule_text)])
        for spliced in _splice_every_gap(command, newline):
            decision = hook.decide(
                {"tool_name": "Bash", "tool_input": {"command": spliced}}, rules
            )
            assert decision.permission == "deny", (
                f"gap-spliced {command!r} (-> {spliced!r}) must still be "
                f"denied by {rule_text!r}"
            )
