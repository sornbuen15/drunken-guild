"""Validate the per-agent evidence ledger and behavior scenario catalog."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "tests" / "routing" / "agent-coverage.json"
SMOKE = ROOT / "tests" / "routing" / "skills-first-smoke.json"
INTENT_AUTHORITY = ROOT / "tests" / "routing" / "intent-authorization.json"
DOC = ROOT / "docs" / "AGENT-COMPATIBILITY.md"


def test_agent_ledger_has_named_agents_and_dimensions() -> None:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    names = {agent["name"] for agent in data["agents"]}
    assert {"Codex", "Claude Code", "Aider", "Gemini CLI", "Antigravity"} <= names
    assert {
        "instruction_loading",
        "skill_access",
        "discovery",
        "routing",
        "tools_mcp",
        "human_gates",
        "token_usage",
    } <= set(data["dimensions"])


def test_unverified_agents_do_not_claim_evidence() -> None:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    for agent in data["agents"]:
        if agent["status"] == "not_tested":
            assert agent["evidence"] is None
        if agent["tokens"] is not None:
            assert agent["token_source"] and agent["measurement_window"]


def test_smoke_scenarios_cover_optional_jira_small_task_and_human_gates() -> None:
    data = json.loads(SMOKE.read_text(encoding="utf-8"))
    ids = {scenario["id"] for scenario in data["scenarios"]}
    assert {
        "new-project-prd",
        "tiny-task-build",
        "changed-requirement",
        "audit-unknown-evidence",
        "no-main-target",
        "preserve-human-approval",
    } <= ids
    assert "Jira" in DOC.read_text(encoding="utf-8")


def test_drunkenguild_main_prohibition_is_explicit() -> None:
    workflow = (ROOT / "skills" / "workflow" / "git-workflow" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Never push to `main`, open a pull request targeting" in workflow
    assert "Never merge into `main`" in workflow


def test_other_projects_instruction_files_are_preserved_by_policy() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    prd = (ROOT / ".ai" / "PRD.md").read_text(encoding="utf-8")
    assert "Instruction files are not disposable" in agents
    assert "does not authorize deleting `AGENTS.md`, `CLAUDE.md`" in prd
    assert "preserves the files on disk" in " ".join(prd.split())


def test_intent_and_authority_contract_covers_non_action_and_action_requests() -> None:
    data = json.loads(INTENT_AUTHORITY.read_text(encoding="utf-8"))
    scenarios = {scenario["id"]: scenario for scenario in data["scenarios"]}

    assert {
        "question-about-change",
        "explain-possible-fix",
        "review-without-editing",
        "plan-without-implementation",
        "explicit-small-build",
        "ambiguous-state-change",
        "external-action-question",
    } <= scenarios.keys()

    for scenario in scenarios.values():
        if scenario["intent"] != "implementation":
            assert scenario["authorizes_state_change"] is False
            assert scenario["expected_route"] != {"kind": "skill", "name": "build"}

    build = scenarios["explicit-small-build"]
    assert build["authorizes_state_change"] is True
    assert build["expected_route"] == {"kind": "skill", "name": "build"}

    known_routes = {
        ("skill", "clear-responses"),
        ("skill", "build"),
        ("role", "reviewer"),
        ("role", "manager"),
    }
    assert {
        (scenario["expected_route"]["kind"], scenario["expected_route"]["name"])
        for scenario in scenarios.values()
    } <= known_routes


def test_portable_instructions_require_intent_before_state_change() -> None:
    required = {
        "Classify intent before choosing a skill, role, or tool.",
        "A question, explanation, analysis, review, or plan does not authorize implementation",
        "When a request may change files or external state but authority is ambiguous, ask",
    }
    for path in (ROOT / "AGENTS.md", ROOT / "src" / "core" / "templates" / "AGENTS.md"):
        content = path.read_text(encoding="utf-8")
        missing = {rule for rule in required if rule not in content}
        assert not missing, (
            f"{path} is missing intent/authority rules: {sorted(missing)}"
        )
