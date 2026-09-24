# mypy: ignore-errors
"""DG-397. The scenario list that proves routing (REQ-002).

The Boss's complaint: agents follow the written rules, but do not work out on
their own when a skill, a role or an MCP tool is needed. The acceptance is a
fixed list of plain-language requests, each naming the route it must produce,
run on every supported agent (DG-398, DG-399, DG-400).

This file only holds the list to its own shape. Whether an agent actually picks
the route is the runners' job, and costs tokens; whether the list can be trusted
is this file's, and costs nothing.
"""

from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "tests" / "routing" / "scenarios.json"
KINDS = {"skill", "role", "tool", "none"}


def _load() -> list[dict]:
    return json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]


def _skills() -> set[str]:
    return {p.parent.name for p in (ROOT / "skills").rglob("SKILL.md")}


def _roles() -> set[str]:
    return {p.stem for p in (ROOT / "agents").glob("*.md") if p.name != "INDEX.md"}


def _tools() -> set[str]:
    tree = ast.parse((ROOT / "src" / "jira_mcp" / "server.py").read_text("utf-8"))
    return {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any("mcp.tool" in ast.unparse(d) for d in n.decorator_list)
    }


def test_the_list_exists() -> None:
    assert SCENARIOS.is_file(), f"{SCENARIOS} is missing"


def test_every_scenario_has_a_request_and_one_expected_route() -> None:
    for s in _load():
        assert s["request"].strip(), s
        assert s["expect"]["kind"] in KINDS, s
        if s["expect"]["kind"] == "none":
            assert "name" not in s["expect"], s
        else:
            assert s["expect"]["name"].strip(), s


def test_requests_are_not_repeated() -> None:
    dupes = [r for r, n in Counter(s["request"] for s in _load()).items() if n > 1]
    assert not dupes, dupes


def test_every_expected_route_resolves() -> None:
    known = {"skill": _skills(), "role": _roles(), "tool": _tools()}
    missing = [
        s["expect"]
        for s in _load()
        if s["expect"]["kind"] != "none"
        and s["expect"]["name"] not in known[s["expect"]["kind"]]
    ]
    assert not missing, f"routes to nothing: {missing}"


def test_every_skill_and_role_is_asked_for_at_least_twice() -> None:
    counts = Counter(
        (s["expect"]["kind"], s["expect"]["name"])
        for s in _load()
        if s["expect"]["kind"] in {"skill", "role"}
    )
    short = [
        (kind, name)
        for kind, names in (("skill", _skills()), ("role", _roles()))
        for name in names
        if counts[(kind, name)] < 2
    ]
    assert not short, f"fewer than two scenarios: {sorted(short)}"


def test_at_least_five_requests_trigger_nothing() -> None:
    assert sum(s["expect"]["kind"] == "none" for s in _load()) >= 5
