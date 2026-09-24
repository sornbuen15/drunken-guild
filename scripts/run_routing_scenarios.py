#!/usr/bin/env python3
"""Send each routing scenario to an agent three times; pass at two of three.

DG-398, for REQ-002: the Boss describes the work in plain words and the agent
picks the skill, role or MCP tool without being told which. The requests and
the route each must produce are `tests/routing/scenarios.json` (DG-397). This
sends them to Claude Code headless and reads the choice out of its event stream.

    python scripts/run_routing_scenarios.py                # every scenario
    python scripts/run_routing_scenarios.py --only replan  # a subset

**It spends tokens** — three calls per scenario — so the test that wraps it is
marked `routing` and a default pytest run deselects it.

**Nothing a scenario asks for is done.** Every tool call is refused by a
PreToolUse hook before it runs, and the refused call is still in the stream,
which is all the choice needs. "Leave a note on DG-311" must record
`jira_add_comment`, not post a comment. The run stops at the first route.

The choice is the first Skill, Agent or MCP call. Reading a file first is not a
choice. A run that ends with none of those is `none`; a run that never reached
a result, or whose result is an error, is `error`, so a broken agent — one whose
login has expired, say — cannot pass the no-route scenarios.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "tests" / "routing" / "scenarios.json"

RUNS = 3
PASS_AT = 2

#: Seconds one run may take before it is recorded as an error.
TIMEOUT = 240

Route = Dict[str, str]

#: The hook refuses every call; exit 2 is a PreToolUse block.
_REFUSE = (
    "import sys; sys.stderr.write('routing probe: choice recorded, not run'); "
    "sys.exit(2)"
)


def _deny_all_settings() -> str:
    python = Path(sys.executable).as_posix()
    command = f'"{python}" -c "{_REFUSE}"'
    hook = {"type": "command", "command": command}
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}})


def claude_command(claude: str, request: str) -> List[str]:
    return [
        claude,
        "-p",
        request,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--settings",
        _deny_all_settings(),
    ]


def _route(block: Dict[str, Any]) -> Optional[Route]:
    name = str(block.get("name", ""))
    inp = block.get("input") or {}
    if name == "Skill" and inp.get("skill"):
        return {"kind": "skill", "name": str(inp["skill"]).rsplit(":", 1)[-1]}
    if name in ("Agent", "Task") and inp.get("subagent_type"):
        return {"kind": "role", "name": str(inp["subagent_type"])}
    if name.startswith("mcp__") and name.count("__") >= 2:
        return {"kind": "tool", "name": name.split("__", 2)[2]}
    return None


def _first_route(event: Dict[str, Any]) -> Optional[Route]:
    if event.get("type") != "assistant":
        return None
    for block in (event.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            route = _route(block)
            if route:
                return route
    return None


def choice(events: Iterable[Dict[str, Any]]) -> Route:
    """The route a run chose: its first Skill, Agent or MCP call."""
    finished = False
    for event in events:
        route = _first_route(event)
        if route:
            return route
        # An expired login ends with subtype "success" and is_error true.
        if event.get("type") == "result":
            finished = not event.get("is_error")
    return {"kind": "none"} if finished else {"kind": "error"}


def _matches(expect: Route, got: Route) -> bool:
    if got.get("kind") != expect.get("kind"):
        return False
    return expect["kind"] == "none" or got.get("name") == expect.get("name")


def passes(expect: Route, choices: List[Route]) -> bool:
    return sum(_matches(expect, c) for c in choices) >= PASS_AT


def _label(route: Route) -> str:
    return route["kind"] if "name" not in route else f"{route['kind']}:{route['name']}"


@dataclass
class Row:
    request: str
    expect: Route
    choices: List[Route] = field(default_factory=list)


def report(agent: str, rows: List[Row]) -> str:
    lines = [f"Routing — {agent}, {RUNS} runs each, pass at {PASS_AT}", ""]
    passed = 0
    for row in rows:
        hits = sum(_matches(row.expect, c) for c in row.choices)
        ok = passes(row.expect, row.choices)
        passed += ok
        lines.append(
            f"{'PASS' if ok else 'FAIL'} {hits}/{len(row.choices)}  "
            f"expect {_label(row.expect)}  got "
            f"{', '.join(_label(c) for c in row.choices)}  | {row.request}"
        )
    lines += ["", f"{passed} of {len(rows)} passed"]
    return "\n".join(lines) + "\n"


def run_claude(claude: str, request: str, cwd: Path) -> Route:
    """One run. Stops reading, and stops the agent, at the first route."""
    proc = subprocess.Popen(
        claude_command(claude, request),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    events: List[Dict[str, Any]] = []
    # A run that hangs is killed, its stream ends, and it reads as `error`.
    watchdog = threading.Timer(TIMEOUT, proc.kill)
    watchdog.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            events.append(event)
            if _first_route(event):
                break
        return choice(events)
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--only", default="", help="scenarios whose route contains this"
    )
    parser.add_argument("--cwd", default=str(ROOT), help="project the agent runs in")
    parser.add_argument("--report", default="", help="also write the report here")
    args = parser.parse_args(argv)

    claude = shutil.which("claude")
    if not claude:
        print("Routing — claude-code: SKIPPED, `claude` is not on PATH. Not a pass.")
        return 2

    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    rows = []
    for s in scenarios:
        if args.only and args.only not in _label(s["expect"]):
            continue
        row = Row(request=s["request"], expect=s["expect"])
        for _ in range(RUNS):
            row.choices.append(run_claude(claude, s["request"], Path(args.cwd)))
        rows.append(row)
        print(report("claude-code", [row]).splitlines()[2], flush=True)

    text = report("claude-code", rows)
    print("\n" + text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    return 0 if all(passes(r.expect, r.choices) for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
