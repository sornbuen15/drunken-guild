# mypy: ignore-errors
"""The PreToolUse hook — the deny floor.

What this file used to test was a router: away mode, a daemon socket, an
approval state machine, and the rule-learning that turned one 👍 into a
standing local rule. That half is retired with the Discord machinery (DG-355),
and so are its tests. What survives is what was never about asking anyone.

The floor answers two questions and then stops:

1. **Deny is not negotiable.** It was evaluated first when there was a remote
   answer to outrank, and it is evaluated first now that there is not.
2. **A call that cannot be read cannot have been checked** against the deny
   rules, so it is refused rather than waved through (DG-321).

Everything else gets silence — exit 0 with no decision, meaning "no opinion",
which is the right answer far more often than a verdict is. Silence is not
`allow`: the hook enforces a floor and has no authority to widen anything.
"""

import json

import pytest

from core import hook
from core import permission_rules as pr

DENY_RULES = [pr.Rule.parse("Bash(rm -rf:*)"), pr.Rule.parse("Read(**/.env)")]
ALLOW_RULES = [pr.Rule.parse("Bash(git status:*)")]


def payload(tool_name="Bash", command="whoami", mode="default", **extra):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"command": command} if tool_name == "Bash" else extra,
        "permission_mode": mode,
    }


class TestDenyIsNotNegotiable:
    def test_a_denied_command_is_denied_without_asking_anyone(self) -> None:
        """The denylist is evaluated first and does not go to Discord at all.
        If it did, a 👍 would be able to authorise `rm -rf` remotely, which is
        precisely the authority the Boss said remote approval must not have.
        """
        decision = hook.decide(
            payload(command="rm -rf /tmp/x"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_deny_still_applies_when_the_boss_is_not_away(self) -> None:
        decision = hook.decide(
            payload(command="rm -rf /tmp/x"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_deny_survives_bypass_permissions_mode(self) -> None:
        """`--dangerously-skip-permissions` turns off the harness's prompting.
        The hook still runs, and the things the Boss put on the deny list are
        the things that were never meant to depend on a mode flag."""
        decision = hook.decide(
            payload(command="rm -rf /tmp/x", mode="bypassPermissions"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_a_denied_command_hidden_behind_an_allowed_one_is_denied(self) -> None:
        decision = hook.decide(
            payload(command="git status && rm -rf /tmp/x"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_reading_dotenv_is_denied(self) -> None:
        decision = hook.decide(
            payload(tool_name="Read", file_path="/somewhere/else/.env"),
            pr.Rules(allow=[], deny=DENY_RULES),
        )
        assert decision.permission == "deny"


class TestDG321UnreadableCallsFailClosed:
    """A call the hook cannot read is denied, not waved through.

    A missing command or path is not merely noisy -- `.get(name, "")` yields an
    empty string, and an empty string matches no rule at all, deny rules
    included. The call then falls past the deny list it was supposed to be
    stopped by. The case first came from a foreign payload mapped by field
    name (that mapping is retired, DG-349); the guard asks the question that
    survives any payload shape: "if this call carries no command or path, the
    hook has nothing to judge and must not pretend otherwise."
    """

    def test_a_command_that_is_an_empty_string_is_denied(self) -> None:
        """Without the guard this returns no decision, and the harness carries
        on with a call no deny rule was ever evaluated against."""
        decision = hook.decide(
            payload(command=""),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_a_bash_call_with_no_command_key_at_all_is_denied(self) -> None:
        decision = hook.decide(
            {"tool_name": "Bash", "tool_input": {}, "permission_mode": "default"},
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_a_path_tool_with_an_empty_path_is_denied(self) -> None:
        """An empty path is the same failure as an empty command, and
        `Read(**/.env)` cannot fire on it either."""
        decision = hook.decide(
            payload(tool_name="Read", path=""),
            pr.Rules(allow=[], deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_an_unreadable_call_is_denied_before_bypass_permissions(self) -> None:
        """Ordered with the deny list, not after it. `bypassPermissions` turns
        off prompting; it does not turn off the floor, and a call nobody can
        read is exactly when the floor matters."""
        decision = hook.decide(
            payload(command="", mode="bypassPermissions"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission == "deny"

    def test_a_tool_that_carries_neither_is_left_alone(self) -> None:
        """The guard must stay narrow. `Bash`, `Read` and the file-writing
        family are the three where an empty value is meaningless.
        A tool that legitimately carries no command and no path -- TodoWrite,
        say -- is none of the hook's business, and denying it would break every
        session to close a hole that is not there."""
        decision = hook.decide(
            {"tool_name": "TodoWrite", "tool_input": {}, "permission_mode": "default"},
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission is None


class TestSilenceWhereSilenceIsCorrect:
    def test_an_allowlisted_call_gets_no_decision(self) -> None:
        """Not `allow` -- silence. The harness's own allowlist already covers
        this call, so answering `allow` would only add a second authority
        saying the same thing, and a second place for the two to disagree."""
        decision = hook.decide(
            payload(command="git status --short"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission is None

    def test_an_unlisted_call_gets_no_decision_either(self) -> None:
        """The change DG-355 makes, stated as a test. This call used to be
        routed to Discord when the Boss was away; there is nowhere to route it
        now, and the harness's own prompt is the whole answer."""
        decision = hook.decide(
            payload(command="curl https://example.com"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission is None
        assert decision.reason == ""

    def test_bypass_permissions_mode_is_not_second_guessed(self) -> None:
        """Deny still applied above. Beyond that, an operator who explicitly
        turned prompting off did not ask for a second opinion."""
        decision = hook.decide(
            payload(command="curl https://example.com", mode="bypassPermissions"),
            pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES),
        )
        assert decision.permission is None

    def test_the_hook_never_returns_allow(self) -> None:
        """The floor can refuse and it can stand aside. Widening permission was
        only ever something a Boss's answer could do, and there is no answer to
        carry now — `allow` must not appear on any path."""
        for call in (
            payload(command="git status --short"),
            payload(command="curl https://example.com"),
            payload(tool_name="TodoWrite"),
            payload(command="rm -rf /tmp/x"),
        ):
            decision = hook.decide(call, pr.Rules(allow=ALLOW_RULES, deny=DENY_RULES))
            assert decision.permission in (None, "deny")


class TestTheWireFormat:
    def test_a_decision_serialises_to_the_documented_shape(self) -> None:
        emitted = json.loads(hook.render(hook.Decision("deny", "because")))
        specific = emitted["hookSpecificOutput"]
        assert specific["hookEventName"] == "PreToolUse"
        assert specific["permissionDecision"] == "deny"
        assert specific["permissionDecisionReason"] == "because"

    def test_silence_emits_no_permission_decision(self) -> None:
        """A decision key with a null value is not silence. The field has to
        be absent or the harness has been handed an opinion."""
        emitted = json.loads(hook.render(hook.Decision(None, "")))
        assert "permissionDecision" not in emitted.get("hookSpecificOutput", {})

    def test_malformed_stdin_does_not_produce_a_decision(self, capsys) -> None:
        """Principle 8, in the one place where failing loudly would be worst:
        a hook that crashes on unexpected input must not take the tool call
        with it. It stands aside and the normal flow continues."""
        assert hook.main(stdin_text="not json at all") == 0
        emitted = json.loads(capsys.readouterr().out or "{}")
        assert "permissionDecision" not in emitted.get("hookSpecificOutput", {})


class TestDG296CuratedStaticAllowlist:
    """DG-296: the shapes `fewer-permission-prompts` found repeated across
    real transcripts -- previously unlisted, read-only or build/test, and
    never prompted for again once here. Each command below is the actual
    shape observed, not a hand-picked simplification, so a rule that looks
    right but is scoped wrong (a missing subcommand, a stray flag) fails
    exactly like it would in the terminal."""

    def _allow_rules(self):
        from pathlib import Path

        settings = json.loads(
            (
                Path(__file__).resolve().parents[1] / ".claude" / "settings.json"
            ).read_text(encoding="utf-8")
        )
        return [pr.Rule.parse(entry) for entry in settings["permissions"]["allow"]]

    @pytest.mark.parametrize(
        "command",
        [
            "uv run ruff check src/ tests/ scripts/",
            "uv run ruff check .",
            "uv run mypy src",
            "uvx bandit -ll -q -r src/ 2>/dev/null",
            "git fetch --quiet origin",
            "uv run drunken-usage --project drunken-guild --by ticket",
        ],
    )
    def test_a_previously_prompted_shape_now_needs_no_prompt(self, command) -> None:
        rules = self._allow_rules()
        assert pr.is_allowed("Bash", {"command": command}, rules), (
            f"{command!r} was one of the repeated, read-only shapes DG-296 "
            "curated -- it must match Layer 1 without a prompt."
        )

    @pytest.mark.parametrize(
        "command",
        [
            "uv run ruff format src/ tests/",  # rewrites files -- not read-only
            "uv run python -c \"import os; os.system('rm -rf /')\"",  # interpreter
            "git checkout -b feature/DG-1-x",  # mutates the working tree
        ],
    )
    def test_a_mutating_or_arbitrary_exec_shape_was_not_curated_in(
        self, command
    ) -> None:
        """The scan surfaced these same verbs, but the mutating or
        code-execution variant must not have ridden along with the
        read-only one it was curated from."""
        rules = self._allow_rules()
        assert not pr.is_allowed("Bash", {"command": command}, rules)


class TestDG334TheWriteSideOfTheFloor:
    """`.env` is denied to every tool that can change it, not just to Read.

    The settings file must spell a file rule `Edit(...)` -- Claude Code
    consults no other name. When the matcher compared tool names exactly,
    that spelling covered nothing Claude actually calls to create or
    overwrite a file, so the deny list read as protection and was not.
    Away mode is where it bites: an unlisted, undenied `.env` write is
    routed to Discord, and the whole point of the deny list is that no
    answer arriving from there can authorise it.
    """

    EDIT_DENY = [pr.Rule.parse("Edit(**/.env)")]

    def test_writing_dotenv_is_denied(self) -> None:
        decision = hook.decide(
            payload(tool_name="Write", file_path="/somewhere/else/.env"),
            pr.Rules(allow=[], deny=self.EDIT_DENY),
        )
        assert decision.permission == "deny"

    def test_an_edit_to_dotenv_is_denied(self) -> None:
        """The Edit tool itself, not just Write. Same floor."""
        decision = hook.decide(
            payload(tool_name="Edit", path="/repo/.env"),
            pr.Rules(allow=[], deny=self.EDIT_DENY),
        )
        assert decision.permission == "deny"

    def test_a_file_write_carrying_no_path_is_denied(self) -> None:
        """DG-321 for the write side. An empty path matches no rule at all --
        deny rules included. It was once guarded under `Write` and stopped
        being guarded when the name it arrived under became `Edit`, because
        the guard was keyed on the name rather than on the family."""
        decision = hook.decide(
            payload(tool_name="Edit", path=""),
            pr.Rules(allow=ALLOW_RULES, deny=self.EDIT_DENY),
        )
        assert decision.permission == "deny"

    def test_an_edit_allow_rule_keeps_a_write_off_discord(self) -> None:
        """The other half of the same defect, and the noisy one: with no
        `Write(...)` rule left in the allow list, every file Claude creates
        while away became a question for the Boss."""
        decision = hook.decide(
            payload(tool_name="Write", file_path="/repo/src/thing.py"),
            pr.Rules(
                allow=[pr.Rule.parse("Edit(/repo/**)", base_dir="/repo")], deny=[]
            ),
        )
        # Both halves. An empty reason is what says the floor never fired:
        # the hook stood aside rather than refusing a legitimate write.
        assert decision.permission is None
        assert decision.reason == ""
