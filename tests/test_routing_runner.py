# mypy: ignore-errors
"""The routing runner's own logic, offline — DG-398.

`scripts/run_routing_scenarios.py` sends each scenario in
`tests/routing/scenarios.json` to Claude Code three times and passes it at two
of three. Sending costs tokens, so that part is marked `routing` and a default
run deselects it (`test_the_live_run_is_not_in_a_default_run`). Everything the
verdict depends on — reading the choice out of the agent's event stream,
counting it against the expected route, and writing the report — is here, and
costs nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_routing_scenarios as runner  # noqa: E402


def _tool_use(name: str, **inp: str) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]},
    }


def _text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


RESULT = {"type": "result", "subtype": "success"}


class TestTheChoiceIsReadFromTheStream:
    def test_a_skill(self) -> None:
        events = [_tool_use("Skill", skill="prd"), RESULT]

        assert runner.choice(events) == {"kind": "skill", "name": "prd"}

    def test_a_plugin_skill_is_named_without_its_plugin(self) -> None:
        events = [_tool_use("Skill", skill="drunken-guild:prd"), RESULT]

        assert runner.choice(events) == {"kind": "skill", "name": "prd"}

    def test_a_role(self) -> None:
        events = [_tool_use("Agent", subagent_type="reviewer", prompt="x"), RESULT]

        assert runner.choice(events) == {"kind": "role", "name": "reviewer"}

    def test_an_mcp_tool_is_named_without_its_server(self) -> None:
        events = [_tool_use("mcp__drunken-jira-mcp__jira_add_comment"), RESULT]

        assert runner.choice(events) == {"kind": "tool", "name": "jira_add_comment"}

    def test_reading_a_file_first_is_not_the_choice(self) -> None:
        events = [
            _tool_use("Read", file_path="skills/INDEX.md"),
            _tool_use("Skill", skill="breakdown"),
            RESULT,
        ]

        assert runner.choice(events) == {"kind": "skill", "name": "breakdown"}

    def test_the_first_route_counts_not_the_last(self) -> None:
        events = [_tool_use("Skill", skill="build"), _tool_use("Skill", skill="audit")]

        assert runner.choice(events) == {"kind": "skill", "name": "build"}

    def test_an_answer_with_no_route_is_none(self) -> None:
        events = [_text("UTC+7 is Indochina Time."), RESULT]

        assert runner.choice(events) == {"kind": "none"}

    def test_a_run_that_never_finished_is_an_error_not_none(self) -> None:
        """A crashed run said nothing. Counting it as `none` would pass every
        no-route scenario on an agent that is not even working."""
        assert runner.choice([]) == {"kind": "error"}
        assert runner.choice([_text("partial")]) == {"kind": "error"}

    def test_a_result_that_is_an_error_is_an_error(self) -> None:
        """Seen on the first live run: an expired login ends with
        `subtype: success` and `is_error: true`, and no route at all."""
        failed = {"type": "result", "subtype": "success", "is_error": True}

        assert runner.choice([_text("Failed to authenticate"), failed]) == {
            "kind": "error"
        }


class TestTwoOfThree:
    SKILL = {"kind": "skill", "name": "prd"}
    OTHER = {"kind": "skill", "name": "clarify"}

    def test_two_matches_pass(self) -> None:
        assert runner.passes(self.SKILL, [self.SKILL, self.OTHER, self.SKILL])

    def test_one_match_fails(self) -> None:
        assert not runner.passes(self.SKILL, [self.SKILL, self.OTHER, self.OTHER])

    def test_a_deliberately_wrong_expectation_fails(self) -> None:
        """ACCEPTANCE: seen failing first. The agent picks prd every time; the
        scenario claims clarify."""
        assert not runner.passes(self.OTHER, [self.SKILL, self.SKILL, self.SKILL])

    def test_none_matches_none_but_not_an_error(self) -> None:
        none, error = {"kind": "none"}, {"kind": "error"}

        assert runner.passes(none, [none, none, error])
        assert not runner.passes(none, [none, error, error])


class TestTheReport:
    def test_each_scenario_shows_its_three_choices(self) -> None:
        rows = [
            runner.Row(
                request="Turn the PRD into tickets.",
                expect={"kind": "skill", "name": "breakdown"},
                choices=[
                    {"kind": "skill", "name": "breakdown"},
                    {"kind": "none"},
                    {"kind": "skill", "name": "breakdown"},
                ],
            )
        ]

        report = runner.report("claude-code", rows)

        assert "PASS 2/3" in report
        assert "skill:breakdown, none, skill:breakdown" in report
        assert "Turn the PRD into tickets." in report
        assert "1 of 1 passed" in report

    def test_a_failure_is_marked(self) -> None:
        rows = [
            runner.Row(
                request="r",
                expect={"kind": "none"},
                choices=[{"kind": "error"}] * 3,
            )
        ]

        assert "FAIL 0/3" in runner.report("claude-code", rows)


class TestTheClaudeCodeCommand:
    def test_every_tool_call_is_blocked_before_it_runs(self) -> None:
        """A scenario says "leave a note on DG-311". The probe must record
        that choice, never post the comment."""
        command = runner.claude_command("claude", "Leave a note on DG-311.")

        settings = command[command.index("--settings") + 1]
        assert '"PreToolUse"' in settings
        assert "--permission-mode" in command
        assert command[command.index("--permission-mode") + 1] == "dontAsk"

    def test_it_streams_events_and_saves_no_session(self) -> None:
        command = runner.claude_command("claude", "x")

        assert command[command.index("--output-format") + 1] == "stream-json"
        assert "--no-session-persistence" in command


def test_the_live_run_is_not_in_a_default_run() -> None:
    """It spends tokens: three calls per scenario, forty-one scenarios."""
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    addopts = re.search(r"^addopts = (.+)$", config, re.M)

    assert addopts and "not routing" in addopts.group(1)
    assert re.search(r'^\s*"routing: ', config, re.M), "routing marker undeclared"
