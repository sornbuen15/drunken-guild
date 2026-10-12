# mypy: ignore-errors
"""``scripts/measure_routing.py``'s parser — a canned stream, never a live process.

DG-session-routing: the operator's way of measuring whether a hook actually
changes what a session does is this script. Only its parsing is tested here;
starting a real ``claude`` process is explicitly out of scope for the suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from measure_routing import (  # noqa: E402
    ToolUse,
    parse_stream,
    parse_tool_uses,
    summarise,
)


def _assistant_event(blocks: list[dict]) -> dict:
    return {"type": "assistant", "message": {"content": blocks}}


class TestParseToolUses:
    def test_a_skill_call_is_named_by_its_skill(self) -> None:
        events = [
            _assistant_event(
                [{"type": "tool_use", "name": "Skill", "input": {"skill": "build"}}]
            )
        ]
        assert parse_tool_uses(events) == [ToolUse("skill", "build")]

    def test_an_agent_call_is_named_by_its_subagent_type(self) -> None:
        events = [
            _assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Task",
                        "input": {"subagent_type": "worker"},
                    }
                ]
            )
        ]
        assert parse_tool_uses(events) == [ToolUse("agent", "worker")]

    def test_an_mcp_call_is_named_by_its_tool(self) -> None:
        events = [
            _assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "mcp__drunken-jira-mcp__jira_start_task",
                        "input": {},
                    }
                ]
            )
        ]
        assert parse_tool_uses(events) == [ToolUse("mcp", "jira_start_task")]

    def test_a_plain_tool_call_is_other(self) -> None:
        events = [_assistant_event([{"type": "tool_use", "name": "Bash", "input": {}}])]
        assert parse_tool_uses(events) == [ToolUse("other", "Bash")]

    def test_a_non_assistant_event_is_ignored(self) -> None:
        events = [{"type": "result", "is_error": False}]
        assert parse_tool_uses(events) == []

    def test_text_only_content_is_not_a_tool_use(self) -> None:
        events = [_assistant_event([{"type": "text", "text": "doing it myself"}])]
        assert parse_tool_uses(events) == []

    def test_order_is_preserved(self) -> None:
        events = [
            _assistant_event(
                [{"type": "tool_use", "name": "Skill", "input": {"skill": "prd"}}]
            ),
            _assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Task",
                        "input": {"subagent_type": "manager"},
                    }
                ]
            ),
        ]
        assert parse_tool_uses(events) == [
            ToolUse("skill", "prd"),
            ToolUse("agent", "manager"),
        ]


class TestParseStream:
    def test_reads_newline_delimited_json(self) -> None:
        lines = [
            json.dumps(
                _assistant_event(
                    [{"type": "tool_use", "name": "Skill", "input": {"skill": "audit"}}]
                )
            ),
            "",
            "not json at all",
        ]
        assert parse_stream(lines) == [ToolUse("skill", "audit")]

    def test_a_malformed_line_is_skipped_not_fatal(self) -> None:
        assert parse_stream(["{ broken"]) == []


class TestSummarise:
    def test_says_explicitly_when_nothing_was_called(self) -> None:
        assert "no Skill or Agent tool was called" in summarise([])

    def test_counts_skills_and_agents_separately(self) -> None:
        uses = [
            ToolUse("skill", "build"),
            ToolUse("agent", "worker"),
            ToolUse("other", "Bash"),
        ]
        text = summarise(uses)
        assert "1 skill call(s)" in text
        assert "1 agent call(s)" in text
        assert "3 total" in text
