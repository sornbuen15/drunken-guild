#!/usr/bin/env python3
"""Measure whether a session actually calls a skill or an agent — before/after.

DG-session-routing: installing the skills is not the same as a session
*using* them. This runs one prompt, headless, in a given directory, and
prints which `Skill` or `Agent`/`Task` tools the run actually called — read
out of the `stream-json` event stream, the same shape
`scripts/run_routing_scenarios.py` already reads for its scenario suite.

This script does not run anything destructive: `--permission-mode plan`
means Claude Code plans but does not act, and nothing it would have done is
executed. Still, **this talks to the real `claude` binary and a real
project** — it is not run by the test suite, and it is not run against this
repository or anyone else's project by anything automated here. An operator
runs it by hand, deliberately, to compare a directory's behaviour before and
after installing the SessionStart hook (`drunken-install hook --apply`).

    python scripts/measure_routing.py /path/to/some/project "add a login form"

Only `parse_tool_uses` and `summarise` are unit-tested (against a canned
stream, never a live process) — see `tests/test_measure_routing.py`.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - a fixed, operator-supplied command list, run by hand
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


@dataclass(frozen=True)
class ToolUse:
    """One tool call seen in the stream, in the order it was emitted."""

    kind: str  # "skill" | "agent" | "mcp" | "other"
    name: str


def _tool_use(block: dict[str, Any]) -> Optional[ToolUse]:
    name = str(block.get("name", ""))
    if not name:
        return None
    inp = block.get("input") or {}
    if name == "Skill":
        skill = inp.get("skill") if isinstance(inp, dict) else None
        return ToolUse("skill", str(skill).rsplit(":", 1)[-1] if skill else "")
    if name in ("Agent", "Task"):
        subagent = inp.get("subagent_type") if isinstance(inp, dict) else None
        return ToolUse("agent", str(subagent) if subagent else "")
    if name.startswith("mcp__") and name.count("__") >= 2:
        return ToolUse("mcp", name.split("__", 2)[2])
    return ToolUse("other", name)


def parse_tool_uses(events: Iterable[dict[str, Any]]) -> list[ToolUse]:
    """Every tool call in *events*, in order. A malformed event contributes nothing."""
    found: list[ToolUse] = []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                use = _tool_use(block)
                if use is not None:
                    found.append(use)
    return found


def parse_stream(lines: Iterable[str]) -> list[ToolUse]:
    """`parse_tool_uses` over raw `stream-json` lines; a line that is not JSON is skipped."""
    events: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return parse_tool_uses(events)


def summarise(uses: Sequence[ToolUse]) -> str:
    """One line per call, or the explicit statement that none happened.

    "No output" and "ran but called nothing" must read differently — the
    second is the exact failure this script exists to catch.
    """
    if not uses:
        return "no Skill or Agent tool was called."
    lines = [
        f"{i + 1}. {use.kind}: {use.name or '(unnamed)'}" for i, use in enumerate(uses)
    ]
    skills = sum(1 for u in uses if u.kind == "skill")
    agents = sum(1 for u in uses if u.kind == "agent")
    lines.append(
        f"-- {skills} skill call(s), {agents} agent call(s), {len(uses)} total."
    )
    return "\n".join(lines)


def claude_command(claude: str, prompt: str) -> list[str]:
    return [
        claude,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "plan",
    ]


def run(claude: str, prompt: str, cwd: Path) -> list[ToolUse]:
    """Run *prompt* headless in *cwd* and return the tool calls it made.

    Not unit-tested — it starts a real process. Keep it thin; everything it
    can be wrong about is tested through :func:`parse_stream` instead.
    """
    proc = subprocess.run(  # nosec B603 - no shell, a fixed argv built above
        claude_command(claude, prompt),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return parse_stream(proc.stdout.splitlines())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("directory", help="where to run the prompt")
    parser.add_argument("prompt", help="the request to send, in plain words")
    parser.add_argument(
        "--claude", default="claude", help="the claude binary. Default: claude."
    )
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"error: {directory} is not a directory.", file=sys.stderr)
        return 1

    uses = run(args.claude, args.prompt, directory)
    print(summarise(uses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
