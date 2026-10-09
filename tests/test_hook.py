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
import subprocess
import time
from pathlib import Path

import pytest

from core import hook
from core import permission_rules as pr

DENY_RULES = [pr.Rule.parse("Bash(rm -rf:*)"), pr.Rule.parse("Read(**/.env)")]
ALLOW_RULES = [pr.Rule.parse("Bash(git status:*)")]


def payload(tool_name="Bash", command="whoami", mode="default", cwd=None, **extra):
    result = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"command": command} if tool_name == "Bash" else extra,
        "permission_mode": mode,
    }
    if cwd is not None:
        result["cwd"] = cwd
    return result


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


class TestDG465HookFloorDeniesSkippingTheHooks:
    """DG-465: the third rule of the floor.

    `.claude/settings.json` cannot spell "deny any flag that disables your
    own gate" -- settings rules match a command by prefix and never see a
    flag mid-command. This rule is hardcoded in the hook itself, independent
    of what the settings file says, for exactly the shapes that would let an
    agent (or an adversarial prompt) turn the gate off rather than go around
    it honestly.

    No deny rules are configured in `pr.Rules()` below -- these shapes must
    be denied by the hook floor on its own.
    """

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
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
        ],
    )
    def test_each_named_shape_is_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "echo hi && git commit --no-verify -m x",
            "git status; git push --no-verify",
            "true | git commit --no-verify -m x",
            "(git commit --no-verify -m x)",
            "echo start && (git push --no-verify) && echo end",
        ],
    )
    def test_denied_even_after_an_operator_or_inside_a_subshell(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
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
        ],
    )
    def test_denied_under_quoting_flag_order_path_and_case_variation(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_a_write_under_git_hooks_is_denied(self) -> None:
        decision = hook.decide(
            payload(tool_name="Write", file_path="/repo/.git/hooks/pre-commit"),
            self.NO_RULES,
        )
        assert decision.permission == "deny"

    def test_an_edit_under_git_hooks_is_denied(self) -> None:
        decision = hook.decide(
            payload(tool_name="Edit", path="/repo/.git/hooks/pre-commit"),
            self.NO_RULES,
        )
        assert decision.permission == "deny"

    def test_an_edit_under_git_hooks_windows_backslash_is_denied(self) -> None:
        decision = hook.decide(
            payload(tool_name="Edit", path="C:\\repo\\.git\\hooks\\pre-commit"),
            self.NO_RULES,
        )
        assert decision.permission == "deny"

    class TestNotDenied:
        """Written by the same hand as the bypass attempts above, on purpose:
        a floor that denies legitimate calls is as broken as one that lets
        a real bypass through, and nobody is more motivated to notice a false
        positive than the person who just wrote the true positives."""

        NO_RULES = pr.Rules(allow=[], deny=[])

        def test_a_push_dry_run_is_not_denied(self) -> None:
            decision = hook.decide(payload(command="git push -n"), self.NO_RULES)
            assert decision.permission is None

        def test_a_push_dry_run_long_flag_is_not_denied(self) -> None:
            decision = hook.decide(payload(command="git push --dry-run"), self.NO_RULES)
            assert decision.permission is None

        def test_a_commit_message_containing_the_words_no_verify_is_not_denied(
            self,
        ) -> None:
            decision = hook.decide(
                payload(command='git commit -m "no-verify"'), self.NO_RULES
            )
            assert decision.permission is None

        def test_a_commit_message_mentioning_no_dash_skip_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(command='git commit -m "please do not SKIP= this"'),
                self.NO_RULES,
            )
            assert decision.permission is None

        def test_an_ordinary_commit_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(command='git commit -m "fix: thing"'), self.NO_RULES
            )
            assert decision.permission is None

        def test_reading_the_hooks_path_config_is_not_a_false_alarm_exemption(
            self,
        ) -> None:
            """Not an exemption -- documented as the same greedy trade-off the
            deny side already makes everywhere else: a read of
            core.hooksPath still costs a prompt, not a lockout."""
            decision = hook.decide(
                payload(command="git config --get core.hooksPath"), self.NO_RULES
            )
            assert decision.permission == "deny"

        def test_an_unrelated_rm_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(command="rm -rf /tmp/scratch"), self.NO_RULES
            )
            assert decision.permission is None

        def test_an_unrelated_edit_path_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(tool_name="Edit", path="/repo/src/hooks/useThing.ts"),
                self.NO_RULES,
            )
            assert decision.permission is None

        def test_pre_commit_run_without_uninstall_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(command="pre-commit run --all-files"), self.NO_RULES
            )
            assert decision.permission is None


class TestDG465AdversarialReviewFollowUps:
    """The adversarial reviewer found five more shapes the first pass missed.

    Same rule, same no-settings-rules setup: the hook floor must catch these
    on its own.
    """

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            # 1. Overwriting a hook file without `rm`/`mv`/`chmod`.
            "cp evil.sh .git/hooks/pre-commit",
            "echo '' > .git/hooks/pre-commit",
            "echo malicious >> .git/hooks/pre-commit",
            "tee .git/hooks/pre-commit",
            "tee -a .git/hooks/pre-commit",
            "sed -i 's/exit 1/exit 0/' .git/hooks/pre-commit",
            "truncate -s0 .git/hooks/pre-commit",
            "dd of=.git/hooks/pre-commit",
            "install -m755 evil.sh .git/hooks/pre-commit",
            "rsync evil.sh .git/hooks/",
            "cat evil.sh > .git/hooks/pre-commit",
            # 2. `ln` pointing a symlink into/at the hooks dir.
            "ln -sf /tmp/empty .git/hooks",
            "ln -sf /tmp/empty .git/hooks/pre-commit",
            # 3. Bundled short flags that include `n` on `git commit`.
            "git commit -an -m x",
            "git commit -nm x",
            "git commit -anm x",
        ],
    )
    def test_each_new_bypass_shape_is_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "env SKIP=x git commit -m x",
            "export SKIP=ruff; git commit -m x",
            "sed -i '/hooksPath/d' .git/config",
            "sed -i '/hooksPath/d' .git\\config",
            "git config --unset core.hooksPath",
        ],
    )
    def test_env_and_config_file_editing_shapes_are_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "skip=x git commit -m x",
            "Skip=x git commit -m x",
            "drunken_no_registered_projects=1 git commit -m x",
        ],
    )
    def test_the_skip_env_vars_are_denied_case_insensitively(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_the_unambiguous_no_verify_prefix_git_itself_accepts_is_denied(
        self,
    ) -> None:
        """Verified against the real git binary (git 2.x on this host): `git
        commit --no-verif -m x` runs -- unambiguous, so git accepts it exactly
        like `--no-verify` -- while `--no-ver` is rejected as ambiguous with
        `--no-verbose`. The shortest prefix git itself resolves without
        complaint is `--no-veri`; this is denied from there down to the full
        spelling, not stricter and not looser than what git really does."""
        decision = hook.decide(
            payload(command="git commit --no-verif -m x"), self.NO_RULES
        )
        assert decision.permission == "deny"

    class TestStillNotDenied:
        """The same widening must not start catching legitimate calls."""

        NO_RULES = pr.Rules(allow=[], deny=[])

        def test_reading_a_hook_file_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(command="cat .git/hooks/pre-commit"), self.NO_RULES
            )
            assert decision.permission is None

        def test_listing_the_hooks_dir_is_not_denied(self) -> None:
            decision = hook.decide(payload(command="ls .git/hooks"), self.NO_RULES)
            assert decision.permission is None

        def test_a_push_dry_run_still_is_not_denied(self) -> None:
            decision = hook.decide(payload(command="git push -n"), self.NO_RULES)
            assert decision.permission is None

        def test_no_n_in_the_am_cluster_still_is_not_denied(self) -> None:
            """`-am` commits all tracked changes -- no `n` in the cluster, no
            reason to deny it."""
            decision = hook.decide(payload(command="git commit -am x"), self.NO_RULES)
            assert decision.permission is None

        def test_an_n_flag_quoted_inside_the_commit_message_is_not_denied(
            self,
        ) -> None:
            """The `-n` here is text inside the `-m` argument, not a flag --
            a naive substring scan over the raw command text cannot tell the
            difference; the hook has to actually respect the quoting."""
            decision = hook.decide(
                payload(command='git commit -m "x -n"'), self.NO_RULES
            )
            assert decision.permission is None

        def test_an_unrelated_cp_is_not_denied(self) -> None:
            decision = hook.decide(payload(command="cp a.txt b.txt"), self.NO_RULES)
            assert decision.permission is None

        def test_redirecting_output_away_from_the_hooks_dir_is_not_denied(self) -> None:
            decision = hook.decide(
                payload(command="echo hi > /tmp/not-a-hook"), self.NO_RULES
            )
            assert decision.permission is None


class TestDG465WindowsNativeAndPowerShellBypasses:
    """Round-2 adversarial review: the operator's shell is PowerShell, and
    the first two passes only covered POSIX verbs."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "del .git\\hooks\\pre-commit",
            "erase .git\\hooks\\pre-commit",
            "rd /s /q .git\\hooks",
            "rmdir /s /q .git\\hooks",
            "ren .git\\hooks\\pre-commit pre-commit.bak",
            "move .git\\hooks\\pre-commit C:\\tmp\\",
            "copy evil.ps1 .git\\hooks\\pre-commit",
            "xcopy evil.ps1 .git\\hooks\\pre-commit",
            "mklink .git\\hooks\\pre-commit C:\\tmp\\empty",
            'powershell -Command "Remove-Item .git/hooks -Recurse -Force"',
            'powershell -Command "Move-Item .git\\hooks C:\\tmp\\hooks-bak"',
            'pwsh -c "Rename-Item .git/hooks/pre-commit pre-commit.bak"',
            'pwsh -c "Copy-Item evil.ps1 .git/hooks/pre-commit"',
            "powershell -Command \"Set-Content -Path .git/hooks/pre-commit -Value ''\"",
            "powershell -Command \"Add-Content -Path .git/hooks/pre-commit -Value 'exit 0'\"",
            "powershell -Command \"'' | Out-File .git/hooks/pre-commit\"",
            'powershell -Command "New-Item -ItemType SymbolicLink -Path .git/hooks -Target C:\\tmp\\empty"',
            'powershell -Command "Clear-Content .git/hooks/pre-commit"',
            'cmd /c "del .git\\hooks\\pre-commit"',
            'cmd /c "echo off > .git\\hooks\\pre-commit"',
        ],
    )
    def test_windows_native_and_powershell_mutation_is_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "Get-Content .git/hooks/pre-commit",
            "type .git\\hooks\\pre-commit",
            "dir .git\\hooks",
            "ls .git/hooks",
            'powershell -Command "Get-Content .git/hooks/pre-commit"',
        ],
    )
    def test_windows_native_and_powershell_reads_stay_allowed(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"


class TestDG465GitSubcommandPrecision:
    """Round-2 adversarial review: `commit` and `-n` were matched anywhere in
    the segment, so `git log --grep=commit -n 1` -- an ordinary, read-only
    log command that merely mentions the word "commit" and takes a `-n`
    count -- was wrongly denied by a deny rule nothing can override. The
    fix: find the actual git subcommand (the first non-option token after
    `git` and its own global options such as `-C dir`/`-c k=v`), and gate on
    that rather than on the word appearing anywhere."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "git log --grep=commit -n 1",
            "git log --oneline -n 3 -- src/commit.py",
            "git tag -n",
            "git branch -n",
            "git log -n 3",
            "git stash list -n",
        ],
    )
    def test_unrelated_subcommands_mentioning_commit_or_dash_n_stay_allowed(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -an",
            "git -C some/dir commit -an",
            "git commit --no-verify",
        ],
    )
    def test_the_real_subcommand_is_still_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"


class TestDG465InterpreterAndCrossSegmentBypasses:
    """Round-2 adversarial review: interpreter one-liners that rewrite a hook
    file without naming any of the verbs above, and a bypass built across two
    shell segments (`cd` into the hooks dir, then a bare mutating verb; or a
    path piped into `xargs`). Variable indirection (`H=.git/hooks; mv $H
    /tmp/`) is explicitly out of scope -- see the PR body."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "python -c \"open('.git/hooks/pre-commit','w').write('')\"",
            "python3 -c \"open('.git/hooks/pre-commit','w').close()\"",
            "perl -pi -e 's/exit 1/exit 0/' .git/hooks/pre-commit",
            "awk -i inplace '{gsub(/exit 1/,\"exit 0\")}1' .git/hooks/pre-commit",
            "cd .git/hooks && rm *",
            "cd .git\\hooks && del pre-commit",
            "echo .git/hooks | xargs rm -rf",
        ],
    )
    def test_interpreter_and_cross_segment_bypasses_are_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_an_unrelated_python_one_liner_is_not_denied(self) -> None:
        decision = hook.decide(payload(command='python -c "print(1+1)"'), self.NO_RULES)
        assert decision.permission is None

    def test_cd_elsewhere_then_rm_is_not_denied(self) -> None:
        decision = hook.decide(payload(command="cd /tmp && rm somefile"), self.NO_RULES)
        assert decision.permission is None

    def test_reading_the_hooks_path_in_a_commit_message_then_unrelated_echo_is_not_denied(
        self,
    ) -> None:
        decision = hook.decide(
            payload(command="echo .git/hooks | xargs -I{} echo {}"), self.NO_RULES
        )
        assert decision.permission is None


class TestDG465QuotedGlobalOptionsStillResolveTheSubcommand:
    """Round-3 adversarial review, CRITICAL regression: quoting a `-C`/`-c`
    (or `--git-dir`/`--work-tree`) argument used to defeat the whole
    `--no-verify` check. `_mask_quoted_spans` blanked the quoted span to
    *spaces*, `masked.split()` then dropped it as a token entirely, and
    `_git_subcommand`'s two-token skip for `-C`/`-c` landed on `commit`'s own
    `--no-verify` flag instead of the subcommand -- so the subcommand lookup
    returned `--no-verify` (not in the skip list) and the whole call fell
    through to silence. Fixed by masking to a non-space filler instead, so a
    quoted argument stays exactly one token, in position, like a real shell
    would see it."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "global_opt",
        [
            'git -C "." commit --no-verify -m x',
            "git -C '.' commit --no-verify -m x",
            'git -C "$DIR" commit --no-verify -m x',
            'git -C "a b" commit --no-verify -m x',
            'git -C"dir" commit --no-verify -m x',
            'git -c "user.name=Agent" commit --no-verify -m x',
            "git -c 'user.name=Agent' commit --no-verify -m x",
            'git -c "core.hooksPath=x" commit --no-verify -m x',
            'git --git-dir="x" commit --no-verify -m x',
            'git --git-dir "x" commit --no-verify -m x',
            'git --work-tree="x" commit --no-verify -m x',
            'git --work-tree "x" commit --no-verify -m x',
            'git -C "." commit -an',
            "git -c 'user.name=Agent' commit -an",
            'git --git-dir="x" commit -an',
            'git --work-tree="x" commit -an',
        ],
    )
    def test_a_quoted_global_option_argument_still_resolves_to_commit(
        self, global_opt
    ) -> None:
        decision = hook.decide(payload(command=global_opt), self.NO_RULES)
        assert decision.permission == "deny", f"{global_opt!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            'git -C "." log -n 3',
            "git -c 'a=b' tag -n",
            'git -C "a b" branch -n',
            'git --git-dir="x" log -n 3',
        ],
    )
    def test_a_quoted_global_option_does_not_create_a_false_positive(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    @pytest.mark.parametrize(
        "command",
        [
            "git commit --no-verify -m x",
            "git -C dir commit --no-verify -m x",
            "git -c user.name=Agent commit --no-verify -m x",
            "git commit -an",
        ],
    )
    def test_quoting_every_argument_never_turns_a_denied_command_into_silence(
        self, command
    ) -> None:
        """Property check: for each command already known to be denied,
        quoting every space-separated argument (a transformation a real
        shell treats as a no-op) must never change the verdict to silence."""
        baseline = hook.decide(payload(command=command), self.NO_RULES)
        assert baseline.permission == "deny", f"baseline {command!r} must be denied"

        quoted = " ".join(f'"{tok}"' for tok in command.split())
        quoted_decision = hook.decide(payload(command=quoted), self.NO_RULES)
        assert quoted_decision.permission == "deny", (
            f"quoting every argument of {command!r} (-> {quoted!r}) must stay "
            "denied, not fall through to silence"
        )


class TestDG465CrossSegmentStateIsScopedNotSticky:
    """Round-3 adversarial review, MEDIUM-HIGH false positive: `cwd_is_hooks_dir`
    and `hooks_path_seen` were set but never reset, so any mutating verb or
    `xargs` call anywhere later in the same Bash call -- however unrelated --
    was wrongly denied by a rule nothing can override."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "cd .git/hooks && cd .. && mv somefile.txt elsewhere.txt",
            "cd .git/hooks && ls && cd - && mv dist/ dist_old/",
            "cd .git/hooks && cd /tmp && mv /tmp/build /tmp/build_old",
            "cat .git/hooks/pre-commit; find . -name temp | xargs mv /tmp/dest",
        ],
    )
    def test_the_cwd_and_pipe_state_do_not_leak_past_where_they_apply(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    @pytest.mark.parametrize(
        "command",
        [
            "cd .git/hooks && rm *",
            "echo .git/hooks | xargs rm -rf",
        ],
    )
    def test_the_real_cross_segment_bypasses_are_still_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"


class TestDG465EnvAssignmentWithAQuotedValue:
    """Looking for one more place quoting could open a hole: `SKIP="a b" git
    commit` has a space inside the quoted value, which the old
    `_ENV_ASSIGNMENT_PREFIX` pattern (`\\S*` for the value) could not consume
    as one token -- it would stop at the first space inside the quotes."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            'SKIP="ruff mypy" git commit -m x',
            "SKIP='ruff mypy' git commit -m x",
        ],
    )
    def test_a_quoted_env_value_with_a_space_is_still_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"


class TestDG465QuotingTheCommandWordItselfIsNotABypass:
    """Found while writing the property test above: masking a quoted span to
    any filler still cannot tell `"git"` (quoted, but still naming the real
    git binary -- a shell runs it identically either way) from quoted
    *content*. Real tokenising resolves `"git"` to the token `git`, exactly
    as `_git_subcommand` expects, so quoting the command word itself is not
    a way past this check."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            '"git" commit --no-verify -m x',
            'git "commit" --no-verify -m x',
            'git commit "--no-verify" -m x',
            '"git" "commit" "--no-verify" -m x',
        ],
    )
    def test_quoting_the_git_word_or_the_subcommand_or_the_flag_is_still_denied(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"


class TestDG465BackslashLineContinuationIsNotABypass:
    """Round-4 adversarial review: a backslash line continuation (`\\` then
    a newline, or on this Windows operator's shell, `\\` then CRLF) vanishes
    entirely in a real shell -- it is not an escaped newline, and the two
    physical lines join with nothing in between, not even a space. The
    tokenizer previously copied the newline into the token like any other
    escaped character, so a continuation right after `commit \\` or right
    before `--no-verify` broke the token stream and the whole call fell
    through to silence."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "git commit \\\n--no-verify -m x",
            "git commit\\\n --no-verify -m x",
            "git commit \\\r\n--no-verify -m x",
            "git commit\\\r\n --no-verify -m x",
            "git commit --no-ver\\\nify -m x",
            "git commit --no-ver\\\r\nify -m x",
            "git commit -a\\\nn",
            "git commit -a\\\r\nn",
        ],
    )
    def test_the_two_reviewer_repros_and_their_crlf_and_split_flag_variants(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_a_continuation_inside_double_quotes_still_resolves_the_subcommand(
        self,
    ) -> None:
        decision = hook.decide(
            payload(command='git -C "a\\\nb" commit --no-verify -m x'),
            self.NO_RULES,
        )
        assert decision.permission == "deny"

    def test_a_continuation_inside_single_quotes_stays_literal_and_inert(
        self,
    ) -> None:
        """Single quotes give a backslash no special meaning at all -- the
        backslash and the newline both stay in the value literally, and an
        ordinary commit message containing them is still just a message."""
        decision = hook.decide(
            payload(command="git commit -m 'hello\\\nworld'"), self.NO_RULES
        )
        assert decision.permission is None

    @pytest.mark.parametrize(
        "command",
        [
            "git commit --no-verify -m x",
            "git -C dir commit --no-verify -m x",
            "git commit -an",
        ],
    )
    def test_a_continuation_never_turns_a_denied_command_into_silence(
        self, command
    ) -> None:
        """Property check, same shape as round 3's quoting one: splicing a
        backslash line continuation into every gap between characters of an
        already-denied command must never change the verdict to silence."""
        baseline = hook.decide(payload(command=command), self.NO_RULES)
        assert baseline.permission == "deny", f"baseline {command!r} must be denied"

        spliced = "\\\n".join(command)
        spliced_decision = hook.decide(payload(command=spliced), self.NO_RULES)
        assert spliced_decision.permission == "deny", (
            f"splicing a line continuation into every gap of {command!r} "
            f"(-> {spliced!r}) must stay denied, not fall through to silence"
        )

    def test_a_continuation_split_hooks_path_is_still_denied(self) -> None:
        """The segment-splitting level, not just the word tokenizer: before
        this fix, a bare backslash-newline outside quotes was kept literally
        in the segment text `_denies_hooks_dir_mutation` scans, so a
        continuation landing in the middle of `.git/hooks` fragmented the
        literal substring the pattern looks for and the call was missed."""
        decision = hook.decide(
            payload(command="rm -rf .git/hoo\\\nks/pre-commit"), self.NO_RULES
        )
        assert decision.permission == "deny"


class TestDG465OtherInterTokenWhitespaceStaysSane:
    """Round-4 adversarial review asked for one more look: any other
    character the tokenizer or segment splitter might treat specially
    between tokens. `\\t`, a bare `\\r` (no following `\\n`, so not a line
    continuation), a form feed, and a non-breaking space are all Unicode
    whitespace by Python's own `str.isspace()`, so the word tokenizer
    already treats them as ordinary word separators -- the same substance
    as a plain space, nothing more. These are not continuations, so they do
    not vanish; they just separate words, which is what lets the following
    stay correctly denied or, for the last one, correctly undenied."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "git\tcommit\t--no-verify\t-m\tx",
            "git commit --no-verify\r-m x",
            "git commit --no-verify\x0c-m x",
        ],
    )
    def test_tab_bare_cr_and_form_feed_between_tokens_still_deny(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_a_non_breaking_space_does_not_glue_two_words_into_a_bypass(
        self,
    ) -> None:
        """A literal NBSP between `commit` and `-an` is whitespace to the
        tokenizer (and so denied, same as a plain space would be) -- the
        character is not being given some other, unsafe meaning."""
        decision = hook.decide(payload(command="git commit -an"), self.NO_RULES)
        assert decision.permission == "deny"


class TestDG476RedirectOrWriteAfterCdIntoHooksDir:
    """DG-476, found by the DG-474 reviewer: `cwd_is_hooks_dir` only ever
    checked later segments against `_HOOKS_DIR_MUTATING_VERBS` -- a verb
    list. A bare redirect (`>`, `>>`), `: >`, or a writer whose target is
    just a bare filename (no `.git/hooks` text in the segment at all, since
    cwd is already there) tripped none of those verbs and matched none of
    `_denies_hooks_dir_mutation`'s own path-anchored patterns either."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "cd .git/hooks && echo x > pre-commit",
            "cd .git/hooks && echo x >> pre-commit",
            "cd .git/hooks && printf x > pre-commit",
            "cd .git/hooks && : > pre-commit",
            "cd .git\\hooks; Set-Content pre-commit x",
            "cd .git/hooks && dd of=pre-commit",
            "cd .git/hooks && sed -i 's/exit 1/exit 0/' pre-commit",
        ],
    )
    def test_a_write_with_no_verb_and_no_hooks_text_is_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "cd .git/hooks && cat pre-commit",
            "cd .git/hooks && ls",
            "cd .git/hooks && cd .. && echo x > a.txt",
        ],
    )
    def test_a_read_or_a_write_after_leaving_the_hooks_dir_is_not_denied(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    def test_a_redirect_to_an_absolute_path_elsewhere_is_not_denied(self) -> None:
        """Still inside the hooks dir, but the target is not a file that
        lands there -- an absolute path writes wherever it names, same as it
        would from any other cwd."""
        decision = hook.decide(
            payload(command="cd .git/hooks && echo x > /tmp/elsewhere.txt"),
            self.NO_RULES,
        )
        assert decision.permission is None

    def test_a_redirect_inside_a_subshell_after_cd_is_still_denied(self) -> None:
        decision = hook.decide(
            payload(command="cd .git/hooks && (echo x > pre-commit)"),
            self.NO_RULES,
        )
        assert decision.permission == "deny"

    def test_a_redirect_after_an_or_operator_following_cd_is_still_denied(
        self,
    ) -> None:
        decision = hook.decide(
            payload(command="cd .git/hooks || true; echo x > pre-commit"),
            self.NO_RULES,
        )
        assert decision.permission == "deny"


class TestDG476Round2PushdAndCdVariants:
    """Adversarial round 2 (Jira comment on DG-481): `cwd_is_hooks_dir` only
    ever recognised a bare `cd`/`popd` segment -- `pushd`, `cd` with an
    option flag, a quoted path, a backslash path, or the PowerShell
    spellings (`Set-Location`, `sl`, `chdir`) all changed cwd into the hooks
    dir exactly the same way and were never seen doing it."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "pushd .git/hooks && echo x > pre-commit",
            "cd -P .git/hooks && echo x > pre-commit",
            "cd -L .git/hooks && echo x > pre-commit",
            "cd -- .git/hooks && echo x > pre-commit",
            'cd "./.git/hooks" && echo x > pre-commit',
            "cd '.git/hooks' && echo x > pre-commit",
            "cd .git\\hooks && echo x > pre-commit",
            "Set-Location .git/hooks; echo x > pre-commit",
            "sl .git/hooks; echo x > pre-commit",
            "chdir .git/hooks && echo x > pre-commit",
        ],
    )
    def test_entering_the_hooks_dir_by_any_spelling_still_denies_a_write(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_popd_after_pushd_into_hooks_dir_leaves_it(self) -> None:
        decision = hook.decide(
            payload(command="pushd .git/hooks && popd && echo x > a.txt"),
            self.NO_RULES,
        )
        assert decision.permission is None

    def test_a_later_cd_elsewhere_still_resets_pushd_state(self) -> None:
        decision = hook.decide(
            payload(command="pushd .git/hooks && cd /tmp && echo x > a.txt"),
            self.NO_RULES,
        )
        assert decision.permission is None

    def test_pushd_to_an_unrelated_dir_is_not_denied(self) -> None:
        decision = hook.decide(
            payload(command="pushd /tmp && echo x > a.txt"), self.NO_RULES
        )
        assert decision.permission is None


class TestDG476Round2DigitPrefixedAndSpecialRedirects:
    r"""Adversarial round 2: the old `(?<![\d&])` lookbehind excluded *any*
    digit before `>`, not just the fd-duplication shape `N>&M` -- so
    `2> pre-commit` (a real write of stderr to a file) read as a duplication
    and passed. `&>`, `&>>`, `>>` and `<>` into a relative path must also be
    denied; `2>/dev/null`, `>&2`, `1>&2`, `2>&1` (true fd operations, no file
    write) must stay allowed."""

    NO_RULES = pr.Rules(allow=[], deny=[])

    @pytest.mark.parametrize(
        "command",
        [
            "cd .git/hooks && echo bad 2> pre-commit",
            "cd .git/hooks && echo bad 1> pre-commit",
            "cd .git/hooks && exec 3> pre-commit",
            "cd .git/hooks && echo bad &> pre-commit",
            "cd .git/hooks && echo bad &>> pre-commit",
            "cd .git/hooks && echo bad >> pre-commit",
            "cd .git/hooks && exec 3<> pre-commit",
            "cd .git/hooks && echo bad >| pre-commit",
        ],
    )
    def test_digit_prefixed_and_special_redirects_into_the_hooks_dir_are_denied(
        self, command
    ) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "cd .git/hooks && echo bad 2>/dev/null",
            "cd .git/hooks && echo bad >&2",
            "cd .git/hooks && echo bad 1>&2",
            "cd .git/hooks && echo bad 2>&1",
        ],
    )
    def test_true_fd_operations_with_no_file_write_stay_allowed(self, command) -> None:
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    @pytest.mark.parametrize(
        "command",
        [
            'cd .git/hooks && bash -c "echo bad 2>&1"',
            'cd .git/hooks && bash -c "echo bad >&2"',
        ],
    )
    def test_fd_operations_stay_allowed_inside_a_quoted_wrapper_too(
        self, command
    ) -> None:
        """At the top level, a bare, unquoted `&` is itself a shell operator
        the shared splitter already cuts the segment on -- `echo bad 2>&1`
        is split into `echo bad 2>` and a bogus trailing `1` segment well
        before this pattern ever runs, so the `(?!&)` lookahead never gets
        exercised there. Quoted, the `&` is protected from that split and
        `2>&1` survives whole in one segment -- this is the shape that
        actually needs the lookahead, and the one a mutation that drops it
        breaks."""
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    @pytest.mark.parametrize(
        "command",
        [
            'cd .git/hooks && bash -c "echo bad &> pre-commit"',
            'cd .git/hooks && bash -c "echo bad &>> pre-commit"',
            'cd .git/hooks && bash -c "exec 3<> pre-commit"',
        ],
    )
    def test_special_redirects_still_denied_inside_a_quoted_wrapper(
        self, command
    ) -> None:
        """A quoted wrapper (`bash -c "..."`, `powershell -Command "..."`)
        is exactly where `&>`/`&>>`/`<>` survive as one unsplit segment --
        the shared splitter's own quote-awareness keeps an unquoted bare `&`
        from being read as a background operator and breaking the redirect
        apart the way it would at the top level. A lookbehind that excluded
        any `&` immediately before `>` (an earlier, narrower version of this
        fix) would miss exactly this shape -- `&>`'s `>` *is* preceded by
        `&` -- which is why :data:`_WRITING_REDIRECT_OPERATOR` has no
        lookbehind on what precedes `>` at all, only the `(?!&)` lookahead
        on what follows it."""
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"


class TestDG476Round3UnifiedRedirectOperatorGrammar:
    r"""Adversarial round 3: `_HOOKS_DIR_REDIRECT_PATTERN` matched `>|` only
    when there was no whitespace before the target. `>{1,2}` (the whole of
    `_WRITING_REDIRECT_OPERATOR` at the time) consumed only the first `>` of
    `>|`, leaving the `|` to be swept up by the catch-all `\S*` meant for an
    optional leading quote -- `\S*` cannot cross whitespace, so
    `>| .git/hooks/x` (a space before the path) was never reached by the
    `.git/hooks` literal that followed, while `>|.git/hooks/x` (no space)
    still matched by sheer backtracking luck.

    The fix is one operator grammar, built once and shared by both the
    direct-path check (:data:`hook._HOOKS_DIR_REDIRECT_PATTERN`, DG-476's
    own acceptance) and the cwd-tracking check
    (:data:`hook._RELATIVE_REDIRECT_PATTERN`) -- so the two cannot
    quietly disagree about what a redirect looks like again.
    """

    NO_RULES = pr.Rules(allow=[], deny=[])

    #: Every operator the reviewer named, each paired with a gap that must
    #: not matter: none, one space, two spaces (collapsed upstream by
    #: DG-481, but the end-to-end behaviour is what is under test), and a
    #: tab (same).
    _OPERATORS = [">", ">>", ">|", "1>", "2>", "2>>", "&>", "&>>", "<>"]
    _GAPS = ["", " ", "  ", "\t"]

    @pytest.mark.parametrize("gap", _GAPS)
    @pytest.mark.parametrize("operator", _OPERATORS)
    def test_direct_path_redirect_denied_regardless_of_gap(
        self, operator: str, gap: str
    ) -> None:
        command = f"echo bad {operator}{gap}.git/hooks/pre-commit"
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize("gap", _GAPS)
    @pytest.mark.parametrize("operator", _OPERATORS)
    def test_direct_path_redirect_denied_after_cd_too(
        self, operator: str, gap: str
    ) -> None:
        command = f"cd .git/hooks && echo bad {operator}{gap}.git/hooks/pre-commit"
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "target",
        [
            "./.git/hooks/pre-commit",
            ".git\\hooks\\pre-commit",
            '".git/hooks/pre-commit"',
            "'.git/hooks/pre-commit'",
            "/repo/.git/hooks/pre-commit",
        ],
    )
    @pytest.mark.parametrize("operator", _OPERATORS)
    def test_direct_path_redirect_denied_for_every_target_spelling(
        self, operator: str, target: str
    ) -> None:
        command = f"echo bad {operator} {target}"
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize("gap", _GAPS)
    @pytest.mark.parametrize("operator", _OPERATORS)
    def test_cwd_scoped_redirect_denied_regardless_of_gap(
        self, operator: str, gap: str
    ) -> None:
        command = f"cd .git/hooks && echo bad {operator}{gap}pre-commit"
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize("gap", _GAPS)
    @pytest.mark.parametrize("operator", _OPERATORS)
    def test_cwd_scoped_redirect_to_an_absolute_path_is_not_denied(
        self, operator: str, gap: str
    ) -> None:
        """Round 3 false positive, same root cause: with the old operator
        handling, `>|` to an absolute path while `cwd` is tracked as the
        hooks dir was wrongly denied because the stray `|` -- not the real
        operator -- was what the absolute-path lookahead was ever tested
        against."""
        command = f"cd .git/hooks && echo bad {operator}{gap}/tmp/out"
        decision = hook.decide(payload(command=command), self.NO_RULES)
        assert decision.permission is None, f"{command!r} should stay allowed"

    def test_the_exact_reported_bypass_is_denied(self) -> None:
        decision = hook.decide(
            payload(command="echo bad >| .git/hooks/pre-commit"), self.NO_RULES
        )
        assert decision.permission == "deny"

    def test_the_exact_reported_bypass_is_denied_with_a_tab(self) -> None:
        decision = hook.decide(
            payload(command="echo bad >|\t.git/hooks/pre-commit"), self.NO_RULES
        )
        assert decision.permission == "deny"

    def test_cwd_scoped_redirect_to_a_windows_drive_letter_path_is_not_denied(
        self,
    ) -> None:
        decision = hook.decide(
            payload(command="cd .git/hooks && echo bad > C:\\tmp\\out"), self.NO_RULES
        )
        assert decision.permission is None


class TestDG476Round3SubshellAndGroupCwdScoping:
    """Adversarial round 3, pre-existing since round 1: `(cd .git/hooks &&
    ls)` runs in a real subshell -- a child process with its own copy of
    cwd -- so the parent shell's working directory is unaffected once that
    subshell closes. `cwd_is_hooks_dir` was never reset at the `)`, so a
    write in the *next* segment, outside the subshell entirely, was denied
    for a directory the shell was never actually in by then.

    `{ ...; }` (a brace *group*, not a subshell) is the opposite case: it
    runs in the *same* shell, so a `cd` inside it must keep affecting
    `cwd_is_hooks_dir` for what follows, including inside the group itself.
    """

    NO_RULES = pr.Rules(allow=[], deny=[])

    def test_write_after_a_closing_subshell_is_not_denied(self) -> None:
        decision = hook.decide(
            payload(command="(cd .git/hooks && ls); echo y > b"), self.NO_RULES
        )
        assert decision.permission is None

    def test_write_inside_the_subshell_is_still_denied(self) -> None:
        decision = hook.decide(
            payload(command="(cd .git/hooks && echo x > pre-commit)"), self.NO_RULES
        )
        assert decision.permission == "deny"

    def test_nested_subshells_still_reset_on_close(self) -> None:
        decision = hook.decide(
            payload(command="(cd .git/hooks && (ls)); echo y > b"), self.NO_RULES
        )
        assert decision.permission is None

    def test_a_brace_group_still_denies_a_write_inside_it(self) -> None:
        decision = hook.decide(
            payload(command="{ cd .git/hooks; echo x > pre-commit; }"), self.NO_RULES
        )
        assert decision.permission == "deny"


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed in {cwd}: {result.stderr}"
    )
    return result


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run_git("init", "-q", cwd=path)
    _run_git("config", "user.email", "test@example.com", cwd=path)
    _run_git("config", "user.name", "Test", cwd=path)
    (path / "README.md").write_text("scratch\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=path)
    _run_git("commit", "-q", "-m", "initial", cwd=path)
    return path


def _add_worktree(main_repo: Path, worktree_path: Path, branch: str) -> Path:
    _run_git(
        "worktree",
        "add",
        "-q",
        "-b",
        branch,
        str(worktree_path),
        "HEAD",
        cwd=main_repo,
    )
    return worktree_path


NO_RULES = pr.Rules(allow=[], deny=[])


class TestDG482LinkedWorktreeHooksDir:
    """DG-482: `_HOOKS_DIR_PATTERN` matched only the main checkout's own
    `.git/hooks`. Every agent works in a linked worktree (DG-288), where
    `.git` is a *file* and the shared hooks dir is the main repository's --
    this is the static-text half of the fix: the `.git/worktrees/<name>/
    hooks` shape, and the absolute path into the main repo's hooks dir,
    both of which a linked worktree actually produces.
    """

    def test_worktree_is_a_file_not_a_directory(self, tmp_path: Path) -> None:
        """Proves the fixture is the real shape this ticket is about -- a
        test that cannot fail this way proves nothing about worktrees."""
        main_repo = _init_repo(tmp_path / "main")
        worktree = _add_worktree(main_repo, tmp_path / "wt", "wt-proof")
        assert (worktree / ".git").is_file()

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf .git/worktrees/wt/hooks",
            "mv .git/worktrees/wt/hooks /tmp/backup",
            "cp -r .git/worktrees/wt/hooks /tmp/backup",
            "chmod -R 000 .git/worktrees/wt/hooks",
            "ln -sf /dev/null .git/worktrees/wt/hooks/pre-commit",
            "tee .git/worktrees/wt/hooks/pre-commit < /dev/null",
            "echo bad > .git/worktrees/wt/hooks/pre-commit",
            "echo bad >> .git/worktrees/wt/hooks/pre-commit",
            "echo bad >| .git/worktrees/wt/hooks/pre-commit",
            "echo bad 2> .git/worktrees/wt/hooks/pre-commit",
            "echo bad &> .git/worktrees/wt/hooks/pre-commit",
            "sed -i s/x/y/ .git/worktrees/wt/hooks/pre-commit",
            "del .git\\worktrees\\wt\\hooks\\pre-commit",
        ],
    )
    def test_mutating_the_worktree_hooks_shape_is_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    @pytest.mark.parametrize(
        "command",
        ["cat .git/worktrees/wt/hooks/pre-commit", "ls .git/worktrees/wt/hooks"],
    )
    def test_reading_the_worktree_hooks_shape_is_not_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), NO_RULES)
        assert decision.permission is None, f"{command!r} should not be denied"

    def test_write_tool_targeting_the_worktree_hooks_shape_is_denied(self) -> None:
        decision = hook.decide(
            payload(tool_name="Write", file_path=".git/worktrees/wt/hooks/pre-push"),
            NO_RULES,
        )
        assert decision.permission == "deny"

    def test_edit_tool_targeting_the_worktree_hooks_shape_windows_backslash(
        self,
    ) -> None:
        decision = hook.decide(
            payload(
                tool_name="Edit", path="C:\\repo\\.git\\worktrees\\wt\\hooks\\pre-push"
            ),
            NO_RULES,
        )
        assert decision.permission == "deny"

    def test_absolute_main_repo_hooks_path_from_a_linked_worktree_redirect(
        self, tmp_path: Path
    ) -> None:
        """A redirect naming the *main* repo's absolute hooks path, run as
        if from inside the worktree (``cwd`` set accordingly) -- the shape
        the ticket's finding names explicitly."""
        main_repo = _init_repo(tmp_path / "main")
        worktree = _add_worktree(main_repo, tmp_path / "wt", "wt-abs")
        hooks_dir = _run_git(
            "rev-parse", "--git-path", "hooks", cwd=worktree
        ).stdout.strip()
        command = f"echo bad > {hooks_dir}/pre-commit"
        decision = hook.decide(payload(command=command, cwd=str(worktree)), NO_RULES)
        assert decision.permission == "deny", command


class TestDG482ResolveDynamicHooksDirsUnionsBothReads:
    """DG-482 (2)/(3), at the unit level: `_resolve_dynamic_hooks_dirs`
    unions *both* reads -- `git rev-parse --git-path hooks` and
    `git config --get core.hooksPath` -- rather than trusting one alone.
    On the git version this repository tests against, the first already
    reflects `core.hooksPath`, so an end-to-end test through `decide()`
    cannot tell "both reads happened" apart from "only the first did" --
    this test can, with the git calls themselves replaced."""

    def test_both_reads_are_unioned_into_the_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hook._resolve_dynamic_hooks_dirs.cache_clear()
        seen_args: list[tuple[str, ...]] = []

        # Absolute, drive-letter paths -- what the real git binary actually
        # returns on this platform (verified against a real repo elsewhere
        # in this file); a bare `/from/...` POSIX path with no drive letter
        # is not absolute by `os.path.isabs`'s own rules on Windows and
        # would be resolved against *tmp_path*'s drive instead, which is
        # not what this test is isolating.
        rev_parse_hooks = "C:/from/rev-parse/hooks"
        config_hooks = "C:/from/config/hooks"

        def fake_run_git(args, repo_root, *, timeout=None, text=True):
            seen_args.append(tuple(args))
            if tuple(args[:2]) == ("rev-parse", "--git-path"):
                return subprocess.CompletedProcess(
                    args, 0, stdout=f"{rev_parse_hooks}\n", stderr=""
                )
            if tuple(args[:2]) == ("config", "--get"):
                return subprocess.CompletedProcess(
                    args, 0, stdout=f"{config_hooks}\n", stderr=""
                )
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

        monkeypatch.setattr(hook, "run_git", fake_run_git)
        dirs = hook._resolve_dynamic_hooks_dirs(str(tmp_path))

        assert hook._normalise_path_for_match(rev_parse_hooks) in dirs
        assert hook._normalise_path_for_match(config_hooks) in dirs
        assert ("config", "--get", "core.hooksPath") in seen_args, (
            "the core.hooksPath config read must actually run, not only "
            "git rev-parse --git-path hooks"
        )


class TestDG482ResolvedHooksDirAndCoreHooksPath:
    """DG-482 (2)/(3): the shared hooks dir resolved once via
    `git rev-parse --git-path hooks` (which already honours
    `core.hooksPath`), and `core.hooksPath` read directly -- the case the
    *textual* patterns can never cover on their own, because an operator can
    name the custom directory anything at all.
    """

    def setup_custom_hooks_repo(self, tmp_path: Path) -> tuple[Path, Path]:
        main_repo = _init_repo(tmp_path / "main")
        custom_hooks = tmp_path / "unrelated-name"
        custom_hooks.mkdir()
        _run_git("config", "core.hooksPath", str(custom_hooks), cwd=main_repo)
        hook._resolve_dynamic_hooks_dirs.cache_clear()
        return main_repo, custom_hooks

    @pytest.mark.parametrize(
        "command_template",
        [
            "rm -rf {d}",
            "mv {d} /tmp/backup",
            "cp -r {d} /tmp/backup",
            "chmod -R 000 {d}",
            "tee {d}/pre-commit < /dev/null",
            "echo bad > {d}/pre-commit",
            "echo bad >> {d}/pre-commit",
            "echo bad 2> {d}/pre-commit",
            "sed -i s/x/y/ {d}/pre-commit",
        ],
    )
    def test_mutating_the_custom_hooks_path_dir_is_denied(
        self, tmp_path: Path, command_template: str
    ) -> None:
        main_repo, custom_hooks = self.setup_custom_hooks_repo(tmp_path)
        command = command_template.format(d=str(custom_hooks))
        decision = hook.decide(payload(command=command, cwd=str(main_repo)), NO_RULES)
        assert decision.permission == "deny", command

    def test_reading_the_custom_hooks_path_dir_is_not_denied(
        self, tmp_path: Path
    ) -> None:
        main_repo, custom_hooks = self.setup_custom_hooks_repo(tmp_path)
        decision = hook.decide(
            payload(command=f"cat {custom_hooks}/pre-commit", cwd=str(main_repo)),
            NO_RULES,
        )
        assert decision.permission is None

    def test_write_tool_targeting_the_custom_hooks_path_dir_is_denied(
        self, tmp_path: Path
    ) -> None:
        main_repo, custom_hooks = self.setup_custom_hooks_repo(tmp_path)
        decision = hook.decide(
            payload(
                tool_name="Write",
                file_path=str(custom_hooks / "pre-push"),
                cwd=str(main_repo),
            ),
            NO_RULES,
        )
        assert decision.permission == "deny"

    def test_cd_into_custom_hooks_path_dir_then_bare_redirect_is_denied(
        self, tmp_path: Path
    ) -> None:
        main_repo, custom_hooks = self.setup_custom_hooks_repo(tmp_path)
        command = f"cd {custom_hooks} && echo x > pre-push"
        decision = hook.decide(payload(command=command, cwd=str(main_repo)), NO_RULES)
        assert decision.permission == "deny", command

    def test_without_a_cwd_the_custom_hooks_path_dir_is_not_recognised(
        self, tmp_path: Path
    ) -> None:
        """Documented limit: resolving `core.hooksPath` needs a real `cwd`.
        A payload that never carries one (no agent call omits it in
        practice, but `decide()` must still degrade safely) falls back to
        the textual patterns alone, rather than crashing or guessing at
        `os.getcwd()` (which would break `decide()`'s own purity)."""
        _main_repo, custom_hooks = self.setup_custom_hooks_repo(tmp_path)
        decision = hook.decide(payload(command=f"rm -rf {custom_hooks}"), NO_RULES)
        assert decision.permission is None

    def test_a_non_repository_cwd_fails_safe_rather_than_crashing(
        self, tmp_path: Path
    ) -> None:
        plain_dir = tmp_path / "not-a-repo"
        plain_dir.mkdir()
        hook._resolve_dynamic_hooks_dirs.cache_clear()
        decision = hook.decide(
            payload(command="rm -rf /some/unrelated/path", cwd=str(plain_dir)),
            NO_RULES,
        )
        assert decision.permission is None

    def test_a_missing_cwd_path_fails_safe_rather_than_crashing(self) -> None:
        hook._resolve_dynamic_hooks_dirs.cache_clear()
        decision = hook.decide(
            payload(
                command="rm -rf /some/unrelated/path",
                cwd=str(Path("C:/definitely/does/not/exist/anywhere")),
            ),
            NO_RULES,
        )
        assert decision.permission is None


class TestDG482FailSafeWhenGitItselfErrors:
    """DG-482: a git failure other than a plain non-zero exit (a timeout, a
    missing binary, a permission error) must not crash `decide()` --
    `_resolve_dynamic_hooks_dirs` degrades to an empty set, same as "not a
    repository" does, rather than letting the exception escape."""

    def test_resolve_dynamic_hooks_dirs_returns_empty_when_run_git_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hook._resolve_dynamic_hooks_dirs.cache_clear()

        def raising_run_git(args, repo_root, *, timeout=None, text=True):
            raise hook.GitCommandError("simulated git failure")

        monkeypatch.setattr(hook, "run_git", raising_run_git)
        dirs = hook._resolve_dynamic_hooks_dirs(str(tmp_path))
        assert dirs == frozenset()

    def test_decide_does_not_crash_when_git_resolution_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hook._resolve_dynamic_hooks_dirs.cache_clear()

        def raising_run_git(args, repo_root, *, timeout=None, text=True):
            raise hook.GitCommandError("simulated git failure")

        monkeypatch.setattr(hook, "run_git", raising_run_git)
        decision = hook.decide(
            payload(command="rm -rf /tmp/x", cwd=str(tmp_path)), NO_RULES
        )
        assert decision.permission is None


class TestDG482HooksPathCommandSubstitution:
    """DG-482 (4): `$(git rev-parse --git-path hooks)` (or the backtick
    spelling, or `--git-common-dir`) used as a mutating verb's or a
    redirect's target is denied as text -- never evaluated."""

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf $(git rev-parse --git-path hooks)",
            "rm -rf `git rev-parse --git-path hooks`",
            "mv $(git rev-parse --git-path hooks)/pre-commit /tmp/x",
            "echo bad > $(git rev-parse --git-path hooks)/pre-commit",
            "rm -rf $(git rev-parse --git-common-dir)/hooks",
            'rm -rf "$(git rev-parse --git-path hooks)"',
            "chmod -R 000 $(git rev-parse --git-path hooks)",
        ],
    )
    def test_each_substitution_shape_as_a_target_is_denied(self, command) -> None:
        decision = hook.decide(payload(command=command), NO_RULES)
        assert decision.permission == "deny", f"{command!r} should be denied"

    def test_running_the_substitution_read_only_with_no_mutating_verb_is_not_denied(
        self,
    ) -> None:
        decision = hook.decide(
            payload(command="echo $(git rev-parse --git-path hooks)"), NO_RULES
        )
        assert decision.permission is None


class TestDG482OneSharedPattern:
    """DG-481 round 3's lesson, applied here: the widened hooks-dir shape
    must be defined once and read by every caller, not re-spelled."""

    def test_token_pattern_and_search_pattern_share_the_worktrees_core(self) -> None:
        assert hook._HOOKS_DIR_CORE in hook._HOOKS_DIR_PATTERN.pattern
        assert hook._HOOKS_DIR_CORE in hook._HOOKS_DIR_TOKEN_PATTERN.pattern


class TestDG482FalsePositivesStayAllowed:
    """Everything that merely *contains* `.git`, `hooks`, or a path that
    looks adjacent to them, but is not actually the hooks dir, must stay
    undenied -- the false-positive list, extended with paths drawn from
    this repository's own tree."""

    @pytest.mark.parametrize(
        "path",
        [
            ".githooks",
            ".git.hooks.txt",
            "src/hooks",
            "docs/hooks/x.md",
            "my.git/hooks-notes",
            "src/core/hook.py",
            "src/core/permission_rules.py",
            "tests/test_hook.py",
            "tests/test_permission_rules.py",
            "skills/workflow/git-workflow/SKILL.md",
            "skills/workflow/jira-tickets/SKILL.md",
            ".claude/settings.json",
            ".claude/settings.local.json",
            "scripts/verify_clean_install.sh",
            "scripts/check_doc_drift.py",
            "agents/INDEX.md",
            "skills/INDEX.md",
            "RETIRED.md",
            "SESSION_CHECKPOINT.md",
            "pyproject.toml",
            "uv.lock",
            ".gitignore",
            ".gitattributes",
            "src/core/doctor.py",
            "src/core/init.py",
            "src/core/exclude.py",
            "src/core/ai_layer.py",
            "src/core/layer_copy.py",
            "examples/hooks/sample.md",
        ],
    )
    def test_the_path_alone_stays_allowed_for_bash_reads(self, path) -> None:
        decision = hook.decide(payload(command=f"cat {path}"), NO_RULES)
        assert decision.permission is None, f"{path!r} should not be denied"

    @pytest.mark.parametrize(
        "path",
        [
            ".githooks",
            ".git.hooks.txt",
            "src/hooks",
            "docs/hooks/x.md",
            "my.git/hooks-notes",
            "src/core/hook.py",
            "tests/test_hook.py",
        ],
    )
    def test_the_path_alone_stays_allowed_for_edit(self, path) -> None:
        decision = hook.decide(payload(tool_name="Edit", path=path), NO_RULES)
        assert decision.permission is None, f"{path!r} should not be denied"

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf .githooks",
            "rm -rf .git.hooks.txt",
            "rm -rf src/hooks",
            "rm -rf docs/hooks/x.md",
            "rm -rf my.git/hooks-notes",
        ],
    )
    def test_mutating_the_lookalike_paths_still_stays_allowed(self, command) -> None:
        decision = hook.decide(payload(command=command), NO_RULES)
        assert decision.permission is None, f"{command!r} should not be denied"


class TestDG482PerformanceAndCaching:
    """DG-482 performance requirements: `decide()` stays fast, the git
    resolution is cached (so repeated calls in the same repo pay for at
    most one subprocess pair), and nothing is run at all for commands that
    carry no path-like token."""

    def test_the_git_resolution_gate_skips_commands_with_no_path_token(self) -> None:
        assert hook._might_reference_protected_dir("git status") is False
        assert hook._might_reference_protected_dir("echo hello world") is False
        assert hook._might_reference_protected_dir("rm -rf /tmp/x") is True

    def test_resolution_is_cached_across_repeated_calls(self, tmp_path: Path) -> None:
        main_repo = _init_repo(tmp_path / "main")
        hook._resolve_dynamic_hooks_dirs.cache_clear()
        info_before = hook._resolve_dynamic_hooks_dirs.cache_info()
        hook._resolve_dynamic_hooks_dirs(str(main_repo))
        hook._resolve_dynamic_hooks_dirs(str(main_repo))
        hook._resolve_dynamic_hooks_dirs(str(main_repo))
        info_after = hook._resolve_dynamic_hooks_dirs.cache_info()
        assert info_after.misses - info_before.misses == 1
        assert info_after.hits - info_before.hits == 2

    def test_a_thousand_ordinary_calls_stay_fast(self, tmp_path: Path) -> None:
        main_repo = _init_repo(tmp_path / "main")
        hook._resolve_dynamic_hooks_dirs.cache_clear()
        commands = [
            "git status",
            "ls -la",
            "echo hello",
            "git log --oneline -5",
            "rm -rf /tmp/scratch",
            "cat README.md",
        ]
        started = time.monotonic()
        for i in range(1000):
            hook.decide(
                payload(command=commands[i % len(commands)], cwd=str(main_repo)),
                NO_RULES,
            )
        elapsed = time.monotonic() - started
        assert elapsed < 5.0, f"1000 decide() calls took {elapsed:.2f}s"


class TestDG482NoStateLeaksBetweenCalls:
    def test_a_resolved_custom_hooks_path_in_one_repo_does_not_leak_to_another(
        self, tmp_path: Path
    ) -> None:
        repo_a = _init_repo(tmp_path / "a")
        custom_a = tmp_path / "a-hooks"
        custom_a.mkdir()
        _run_git("config", "core.hooksPath", str(custom_a), cwd=repo_a)

        repo_b = _init_repo(tmp_path / "b")

        hook._resolve_dynamic_hooks_dirs.cache_clear()
        decision_a = hook.decide(
            payload(command=f"rm -rf {custom_a}", cwd=str(repo_a)), NO_RULES
        )
        decision_b = hook.decide(
            payload(command=f"rm -rf {custom_a}", cwd=str(repo_b)), NO_RULES
        )
        assert decision_a.permission == "deny"
        assert decision_b.permission is None, (
            "repo b never configured core.hooksPath to a-hooks, so a "
            "command naming it must not be denied just because repo a's "
            "resolution happened first"
        )
