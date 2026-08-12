"""Tests for the board_mcp package.

Covers:
- Card parsing (complete, minimal, malformed, old-format, milestone variants)
- Field manipulation helpers (set_card_field, remove_card_field)
- Board lane moves
- Claim acquisition, double-claim, assignee mismatch
- Claim expiry and reclaim
- board_report grouping maths
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from board_mcp.board import BoardManager
from board_mcp.card import (
    CardData,
    parse_card,
    remove_card_field,
    set_card_field,
)

# ---------------------------------------------------------------------------
# Fixture card bodies
# ---------------------------------------------------------------------------

_COMPLETE_CARD = """\
# ALPHA-10: Test Task

## Status
- **Status:** Todo
- **Assignee:** @antigravity
- **Start Time:** 2026-01-01
- **End Time:**
- **Milestone:** M2
- **Depends On:** ALPHA-5, ALPHA-6
- **Blocks:** ALPHA-15

## Requirements
1. Do the thing.

## Action Items
- [ ] First item
- [x] Second item
"""

_MINIMAL_CARD = """\
# ALPHA-11: Minimal Task
"""

_MALFORMED_CARD = """\
Not even a heading
Random content with no structure at all
"""

_OLD_FORMAT_CARD = """\
# ALPHA-001: Old Format Task

## Status
In Progress

## Assignee
Antigravity (Principal Engineer)
"""

_CLAIMED_CARD = """\
# TASK-001: Claimed Task

## Status
- **Status:** Todo
- **Assignee:** @agent1
- **Claimed By:** @agent1
- **Claimed At:** 2026-01-01T00:00:00+00:00
"""

_BLOCKED_CARD = """\
# TASK-002: Blocked Task

## Status
- **Status:** Blocked
- **Assignee:** @agent2
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_card(board_dir: str, lane: str, filename: str, content: str) -> str:
    """Write a card file directly (bypassing BoardManager locks) for test setup."""
    lane_dir = os.path.join(board_dir, lane)
    os.makedirs(lane_dir, exist_ok=True)
    path = os.path.join(lane_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture  # type: ignore[misc]
def board_dir(tmp_path: Path) -> str:
    return str(tmp_path / "board")


@pytest.fixture  # type: ignore[misc]
def manager(board_dir: str) -> BoardManager:
    bm = BoardManager(board_dir)
    bm._ensure_board()
    return bm


# ---------------------------------------------------------------------------
# Card parsing tests
# ---------------------------------------------------------------------------


class TestParseCard:
    def test_complete_card_fields(self) -> None:
        card = parse_card(_COMPLETE_CARD, "ALPHA-10_test-task.md")
        assert card.task_id == "ALPHA-10"
        assert "Test Task" in card.title
        assert card.status == "Todo"
        assert card.assignee == "@antigravity"
        assert card.milestone == "M2"
        assert card.depends_on == ["ALPHA-5", "ALPHA-6"]
        assert card.blocks == ["ALPHA-15"]
        assert len(card.action_items) == 2

    def test_minimal_card_has_no_required_fields(self) -> None:
        card = parse_card(_MINIMAL_CARD, "ALPHA-11_minimal.md")
        assert card.task_id == "ALPHA-11"
        assert "Minimal Task" in card.title
        assert card.status == ""
        assert card.assignee == ""
        assert card.milestone is None
        assert card.claimed_by is None
        assert card.claimed_at is None

    def test_malformed_card_does_not_raise(self) -> None:
        card = parse_card(_MALFORMED_CARD, "ALPHA-12_malformed.md")
        assert isinstance(card, CardData)
        assert card.status == ""

    def test_malformed_card_filename_fallback(self) -> None:
        card = parse_card(_MALFORMED_CARD, "not-a-real-id.md")
        assert card.task_id == "not-a-real-id"

    def test_old_format_card_plain_status(self) -> None:
        card = parse_card(_OLD_FORMAT_CARD, "ALPHA-001_old.md")
        assert card.task_id == "ALPHA-001"
        assert card.status == "In Progress"

    def test_no_milestone_returns_none(self) -> None:
        content = _COMPLETE_CARD.replace("- **Milestone:** M2\n", "")
        card = parse_card(content, "ALPHA-10_test.md")
        assert card.milestone is None

    def test_claimed_card_fields(self) -> None:
        card = parse_card(_CLAIMED_CARD, "TASK-001_claimed.md")
        assert card.claimed_by == "@agent1"
        assert card.claimed_at == "2026-01-01T00:00:00+00:00"

    def test_empty_content_does_not_raise(self) -> None:
        card = parse_card("", "TASK-999_empty.md")
        assert card.task_id == "TASK-999"

    def test_blank_field_does_not_swallow_next_line(self) -> None:
        content = (
            "# ALPHA-49: Blank assignee\n\n"
            "## Status\n"
            "- **Status:** To Do\n"
            "- **Assignee:**\n"
            "- **Start Time:**\n"
            "- **End Time:**\n"
        )
        card = parse_card(content, "ALPHA-49_blank-assignee.md")
        assert card.assignee == ""
        assert card.start_time == ""


# ---------------------------------------------------------------------------
# Field manipulation tests
# ---------------------------------------------------------------------------


class TestFieldManipulation:
    def test_set_field_updates_existing(self) -> None:
        content = "## Status\n- **Status:** Todo\n"
        result = set_card_field(content, "Status", "In Progress")
        assert "- **Status:** In Progress" in result
        assert "Todo" not in result

    def test_set_field_adds_new_to_status_block(self) -> None:
        content = "# Title\n\n## Status\n- **Status:** Todo\n"
        result = set_card_field(content, "Claimed By", "@agent")
        assert "- **Claimed By:** @agent" in result

    def test_set_field_creates_status_block_when_absent(self) -> None:
        content = "# Title\n\nSome body text.\n"
        result = set_card_field(content, "Milestone", "M3")
        assert "**Milestone:** M3" in result
        assert "## Status" in result

    def test_set_field_no_title_appends(self) -> None:
        content = "plain text"
        result = set_card_field(content, "Claimed By", "@x")
        assert "**Claimed By:** @x" in result

    def test_remove_field_removes_first_match(self) -> None:
        content = "## Status\n- **Claimed By:** @agent\n- **Claimed At:** 2026-01-01\n"
        result = remove_card_field(content, "Claimed By")
        assert "Claimed By" not in result
        assert "Claimed At" in result

    def test_remove_field_missing_key_is_noop(self) -> None:
        content = "## Status\n- **Status:** Todo\n"
        result = remove_card_field(content, "NonExistentField")
        assert result == content

    def test_set_then_remove_roundtrip(self) -> None:
        content = "# T\n\n## Status\n- **Status:** Todo\n"
        with_field = set_card_field(content, "Claimed By", "@a")
        without_field = remove_card_field(with_field, "Claimed By")
        assert "Claimed By" not in without_field
        assert "- **Status:** Todo" in without_field


# ---------------------------------------------------------------------------
# Board lane move tests
# ---------------------------------------------------------------------------


class TestBoardLaneMoves:
    def test_create_task_success(self, manager: BoardManager) -> None:
        content = "# TASK-001: My Task\n\n## Status\n- **Status:** Todo\n"
        result = manager.create_task("todo", "my-task", content)
        assert result["ok"] is True
        task_id: str = result["id"]
        assert os.path.exists(result["path"])
        # File should contain the content
        with open(result["path"], encoding="utf-8") as fh:
            assert "My Task" in fh.read()
        # ID should follow PREFIX-NNN format
        assert "-" in task_id

    def test_create_task_invalid_lane(self, manager: BoardManager) -> None:
        result = manager.create_task("nonexistent", "slug", "content")
        assert result["ok"] is False
        assert "invalid_lane" in result["reason"]

    def test_create_task_injects_milestone(self, manager: BoardManager) -> None:
        content = "# TASK-001: Task\n\n## Status\n- **Status:** Todo\n"
        result = manager.create_task("backlog", "task", content, milestone="M3")
        assert result["ok"] is True
        with open(result["path"], encoding="utf-8") as fh:
            body = fh.read()
        assert "**Milestone:** M3" in body

    def test_create_task_does_not_double_inject_milestone(
        self, manager: BoardManager
    ) -> None:
        content = "# TASK-001: T\n\n## Status\n- **Milestone:** M1\n"
        result = manager.create_task("backlog", "task", content, milestone="M3")
        assert result["ok"] is True
        with open(result["path"], encoding="utf-8") as fh:
            body = fh.read()
        assert body.count("**Milestone:**") == 1
        assert "M1" in body  # original preserved

    def test_move_task_basic(self, manager: BoardManager) -> None:
        content = "# TASK-001: T\n\n## Status\n- **Status:** Backlog\n"
        manager.create_task("backlog", "task", content)
        # Find the created task_id
        task_id = manager.next_id()["id"]  # not reliable — scan instead
        loc = None
        for fname in os.listdir(os.path.join(manager.board_dir, "backlog")):
            if fname.endswith(".md"):
                m_id = fname.split("_")[0]
                loc = manager._find_task(m_id)
                if loc:
                    task_id = m_id
                    break
        assert loc is not None
        result = manager.move_task(task_id, "todo", "@agent")
        assert result["ok"] is True
        assert result["to"] == "todo"

    def test_move_task_not_found(self, manager: BoardManager) -> None:
        result = manager.move_task("ALPHA-999", "todo", "@agent")
        assert result["ok"] is False
        assert "task_not_found" in result["reason"]

    def test_move_to_inprogress_requires_claim(self, manager: BoardManager) -> None:
        content = (
            "# TASK-001: T\n\n## Status\n- **Status:** Todo\n- **Assignee:** @agent\n"
        )
        manager.create_task("todo", "task", content)
        task_id = _get_only_task_id(manager, "todo")
        result = manager.move_task(task_id, "in-progress", "@agent")
        assert result["ok"] is False
        assert "not_claimed" in result["reason"]

    def test_full_workflow_todo_to_done(self, manager: BoardManager) -> None:
        content = (
            "# TASK-001: T\n\n## Status\n- **Status:** Todo\n- **Assignee:** @agent\n"
        )
        manager.create_task("todo", "task", content)
        task_id = _get_only_task_id(manager, "todo")

        assert manager.claim_task(task_id, "@agent")["ok"] is True
        assert manager.move_task(task_id, "in-progress", "@agent")["ok"] is True
        assert manager.done_task(task_id, "@agent")["ok"] is True

        found = manager._find_task(task_id)
        assert found is not None
        assert found.lane == "done"

    def test_move_task_rewrites_status_field(self, manager: BoardManager) -> None:
        content = "# TASK-001: T\n\n## Status\n- **Status:** Backlog\n"
        manager.create_task("backlog", "task", content)
        task_id = _get_only_task_id(manager, "backlog")

        manager.move_task(task_id, "todo", "@agent")
        assert manager.get_task(task_id)["status"] == "To Do"

    def test_done_task_rewrites_status_field(self, manager: BoardManager) -> None:
        content = (
            "# TASK-001: T\n\n## Status\n- **Status:** Todo\n- **Assignee:** @agent\n"
        )
        manager.create_task("todo", "task", content)
        task_id = _get_only_task_id(manager, "todo")

        manager.claim_task(task_id, "@agent")
        manager.move_task(task_id, "in-progress", "@agent")
        assert manager.get_task(task_id)["status"] == "In Progress"

        manager.done_task(task_id, "@agent")
        assert manager.get_task(task_id)["status"] == "Done"

    def test_status_field_never_drifts_from_lane(self, manager: BoardManager) -> None:
        """A card carrying a stale Status is corrected by the next move."""
        content = "# TASK-001: T\n\n## Status\n- **Status:** Completed\n"
        manager.create_task("backlog", "task", content)
        task_id = _get_only_task_id(manager, "backlog")

        for lane, expected in (("todo", "To Do"), ("backlog", "Backlog")):
            manager.move_task(task_id, lane, "@agent")
            assert manager.get_task(task_id)["status"] == expected

    def test_done_task_wrong_lane(self, manager: BoardManager) -> None:
        content = "# TASK-001: T\n\n## Status\n- **Status:** Todo\n"
        manager.create_task("todo", "task", content)
        task_id = _get_only_task_id(manager, "todo")
        result = manager.done_task(task_id, "@agent")
        assert result["ok"] is False
        assert "wrong_lane" in result["reason"]

    def test_get_task(self, manager: BoardManager) -> None:
        content = (
            "# TASK-001: T\n\n## Status\n- **Status:** Todo\n- **Milestone:** M1\n"
        )
        manager.create_task("backlog", "task", content)
        task_id = _get_only_task_id(manager, "backlog")
        result = manager.get_task(task_id)
        assert result["ok"] is True
        assert result["lane"] == "backlog"
        assert result["milestone"] == "M1"

    def test_get_task_not_found(self, manager: BoardManager) -> None:
        result = manager.get_task("ALPHA-999")
        assert result["ok"] is False

    def test_list_lane_empty(self, manager: BoardManager) -> None:
        assert manager.list_lane("backlog") == []

    def test_list_lane_invalid(self, manager: BoardManager) -> None:
        with pytest.raises(ValueError, match="Invalid lane"):
            manager.list_lane("garbage")

    def test_wip_limit_enforced(self, manager: BoardManager) -> None:
        # Agent has a task already in-progress
        c1 = "# TASK-001: T\n\n## Status\n- **Status:** Todo\n- **Assignee:** @agent\n"
        c2 = "# TASK-002: U\n\n## Status\n- **Status:** Todo\n- **Assignee:** @agent\n"
        manager.create_task("todo", "task1", c1)
        id1 = _get_only_task_id(manager, "todo")
        manager.claim_task(id1, "@agent")
        manager.move_task(id1, "in-progress", "@agent")

        manager.create_task("todo", "task2", c2)
        id2 = _get_only_task_id(manager, "todo")
        manager.claim_task(id2, "@agent")
        result = manager.move_task(id2, "in-progress", "@agent")
        assert result["ok"] is False
        assert "wip_limit_exceeded" in result["reason"]


# ---------------------------------------------------------------------------
# Claim semantics tests
# ---------------------------------------------------------------------------


class TestClaimSemantics:
    def _setup_todo(self, manager: BoardManager, assignee: str = "") -> str:
        """Create a task in todo and return its task_id."""
        line = f"- **Assignee:** {assignee}\n" if assignee else ""
        content = f"# TASK-001: T\n\n## Status\n- **Status:** Todo\n{line}"
        manager.create_task("todo", "task", content)
        return _get_only_task_id(manager, "todo")

    def test_claim_success(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        result = manager.claim_task(task_id, "@agent")
        assert result["ok"] is True
        assert "claimed_at" in result

    def test_claim_writes_fields_to_card(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent")
        loc = manager._find_task(task_id)
        assert loc is not None
        card = manager._read_card(loc)
        assert card.claimed_by == "@agent"
        assert card.claimed_at is not None

    def test_double_claim_rejected(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent1")
        result = manager.claim_task(task_id, "@agent2")
        assert result["ok"] is False
        assert "already_claimed_by" in result["reason"]

    def test_same_agent_double_claim_rejected(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent")
        result = manager.claim_task(task_id, "@agent")
        assert result["ok"] is False

    def test_assignee_mismatch_rejected(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager, assignee="@agent1")
        result = manager.claim_task(task_id, "@agent2")
        assert result["ok"] is False
        assert "assignee_mismatch" in result["reason"]

    def test_claim_wrong_lane(self, manager: BoardManager) -> None:
        content = "# TASK-001: T\n\n## Status\n- **Status:** Backlog\n"
        manager.create_task("backlog", "task", content)
        task_id = _get_only_task_id(manager, "backlog")
        result = manager.claim_task(task_id, "@agent")
        assert result["ok"] is False
        assert "wrong_lane" in result["reason"]

    def test_stale_claim_can_be_reclaimed(
        self, manager: BoardManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent1")
        # Simulate expiry
        monkeypatch.setattr(manager, "_is_claim_stale", lambda _: True)
        result = manager.claim_task(task_id, "@agent2")
        assert result["ok"] is True
        loc = manager._find_task(task_id)
        assert loc is not None
        card = manager._read_card(loc)
        assert card.claimed_by == "@agent2"

    def test_release_claim_by_claimant(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent")
        result = manager.release_claim(task_id, "@agent")
        assert result["ok"] is True
        # Now reclaimable
        assert manager.claim_task(task_id, "@other")["ok"] is True

    def test_release_claim_by_principal_engineer(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent")
        result = manager.release_claim(task_id, "principal-engineer")
        assert result["ok"] is True

    def test_unauthorized_release_rejected(self, manager: BoardManager) -> None:
        task_id = self._setup_todo(manager)
        manager.claim_task(task_id, "@agent1")
        result = manager.release_claim(task_id, "@agent2")
        assert result["ok"] is False
        assert "claim_owned_by" in result["reason"]

    def test_release_nonexistent_task(self, manager: BoardManager) -> None:
        result = manager.release_claim("ALPHA-999", "@agent")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# board_summary auto-release tests
# ---------------------------------------------------------------------------


class TestSummaryAutoRelease:
    def test_summary_counts_correct(self, manager: BoardManager) -> None:
        _write_card(
            manager.board_dir,
            "done",
            "TASK-001_d.md",
            "# TASK-001: Done\n\n## Status\n- **Status:** Done\n",
        )
        _write_card(
            manager.board_dir,
            "todo",
            "TASK-002_t.md",
            "# TASK-002: Todo\n\n## Status\n- **Status:** Todo\n",
        )
        result = manager.summary()
        assert result["counts"]["done"] == 1
        assert result["counts"]["todo"] == 1

    def test_summary_auto_releases_stale_claim(
        self, manager: BoardManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        content = "# TASK-001: T\n\n## Status\n- **Status:** Todo\n"
        manager.create_task("todo", "task", content)
        task_id = _get_only_task_id(manager, "todo")
        manager.claim_task(task_id, "@agent")

        monkeypatch.setattr(manager, "_is_claim_stale", lambda _: True)
        result = manager.summary()
        todo_tasks: list[dict[str, Any]] = result["lanes"]["todo"]
        released = [t for t in todo_tasks if t.get("_stale_claim_released")]
        assert len(released) == 1


# ---------------------------------------------------------------------------
# board_report grouping math tests
# ---------------------------------------------------------------------------


class TestBoardReport:
    def _populate(self, board_dir: str) -> None:
        _write_card(
            board_dir,
            "done",
            "TASK-001_m2-d.md",
            "# TASK-001: M2 Done\n\n## Status\n- **Milestone:** M2\n",
        )
        _write_card(
            board_dir,
            "todo",
            "TASK-002_m2-t.md",
            "# TASK-002: M2 Todo\n\n## Status\n- **Milestone:** M2\n",
        )
        _write_card(
            board_dir,
            "done",
            "TASK-003_m3-d.md",
            "# TASK-003: M3 Done\n\n## Status\n- **Milestone:** M3\n",
        )
        _write_card(
            board_dir,
            "todo",
            "TASK-004_no-ms.md",
            "# TASK-004: No Milestone\n\n## Status\n- **Status:** Todo\n",
        )
        _write_card(
            board_dir,
            "in-progress",
            "TASK-005_ip.md",
            "# TASK-005: In Progress\n\n## Status\n- **Status:** In Progress\n- **Assignee:** @dev\n- **Milestone:** M2\n",
        )
        _write_card(
            board_dir,
            "in-progress",
            "TASK-006_blocked.md",
            "# TASK-006: Blocked\n\n## Status\n- **Status:** Blocked\n- **Assignee:** @dev\n- **Milestone:** M3\n",
        )

    def test_milestone_grouping(self, manager: BoardManager) -> None:
        self._populate(manager.board_dir)
        report = manager.report("exec")
        milestones: dict[str, Any] = {m["milestone"]: m for m in report["milestones"]}
        # M2: done=1, todo=1, in_progress=1, total=3
        assert milestones["M2"]["total"] == 3
        assert milestones["M2"]["done"] == 1
        assert milestones["M2"]["in_progress"] == 1
        assert milestones["M2"]["todo"] == 1
        assert milestones["M2"]["completion_pct"] == pytest.approx(33.3, abs=0.1)

    def test_milestone_completion_100(self, manager: BoardManager) -> None:
        self._populate(manager.board_dir)
        report = manager.report("staff")
        milestones: dict[str, Any] = {m["milestone"]: m for m in report["milestones"]}
        # M3: done=1, in_progress=1 (blocked), total=2 => 50 %
        assert milestones["M3"]["done"] == 1
        assert milestones["M3"]["total"] == 2
        assert milestones["M3"]["completion_pct"] == pytest.approx(50.0)

    def test_unassigned_group(self, manager: BoardManager) -> None:
        self._populate(manager.board_dir)
        report = manager.report("dev")
        milestones: dict[str, Any] = {m["milestone"]: m for m in report["milestones"]}
        assert "unassigned" in milestones
        assert milestones["unassigned"]["total"] == 1

    def test_in_progress_list(self, manager: BoardManager) -> None:
        self._populate(manager.board_dir)
        report = manager.report("dev")
        assert len(report["in_progress"]) == 2
        ids = {t["id"] for t in report["in_progress"]}
        assert "TASK-005" in ids
        assert "TASK-006" in ids

    def test_blocked_list(self, manager: BoardManager) -> None:
        self._populate(manager.board_dir)
        report = manager.report("exec")
        assert len(report["blocked"]) == 1
        assert report["blocked"][0]["id"] == "TASK-006"

    def test_empty_board_returns_empty_milestones(self, manager: BoardManager) -> None:
        report = manager.report("exec")
        assert report["milestones"] == []
        assert report["in_progress"] == []
        assert report["blocked"] == []

    def test_audience_echoed(self, manager: BoardManager) -> None:
        report = manager.report("staff")
        assert report["audience"] == "staff"


# ---------------------------------------------------------------------------
# board_orchestrate tests
# ---------------------------------------------------------------------------


class TestOrchestrate:
    def test_single_wave_no_deps(self, manager: BoardManager) -> None:
        for i in range(1, 4):
            _write_card(
                manager.board_dir,
                "todo",
                f"TASK-00{i}_t.md",
                f"# TASK-00{i}: T{i}\n\n## Status\n- **Assignee:** @a{i}\n",
            )
        result = manager.orchestrate(["TASK-001", "TASK-002", "TASK-003"])
        assert result["total_tasks"] == 3
        assert len(result["waves"]) == 1
        assert result["waves"][0]["mode"] == "parallel"

    def test_missing_task_skipped(self, manager: BoardManager) -> None:
        result = manager.orchestrate(["TASK-999"])
        assert result["total_tasks"] == 0


# ---------------------------------------------------------------------------
# board_agent_context tests
# ---------------------------------------------------------------------------


class TestAgentContext:
    def test_agent_context_found(self, manager: BoardManager) -> None:
        content = """\
# TASK-001: Auth Feature

## Status
- **Status:** Todo
- **Assignee:** @dev

## Requirements
Implement JWT authentication.

## Action Items
- [ ] Write `auth/jwt.py`
- [x] Update `config.py`
"""
        _write_card(manager.board_dir, "todo", "TASK-001_auth.md", content)
        result = manager.agent_context("TASK-001")
        assert result["ok"] is True
        assert "JWT" in result["objective"]
        assert len(result["acceptance_criteria"]) == 2
        assert "auth/jwt.py" in result["relevant_files"]

    def test_agent_context_not_found(self, manager: BoardManager) -> None:
        result = manager.agent_context("ALPHA-999")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# next_id tests
# ---------------------------------------------------------------------------


class TestNextId:
    def test_empty_board_defaults_to_task_prefix(self, manager: BoardManager) -> None:
        result = manager.next_id()
        assert result["id"].startswith("TASK-")
        assert result["number"] == 1

    def test_increments_from_existing(self, manager: BoardManager) -> None:
        _write_card(
            manager.board_dir, "done", "ALPHA-037_slug.md", "# ALPHA-037: T\n\n## Status\n"
        )
        result = manager.next_id()
        assert result["id"] == "ALPHA-038"
        assert result["number"] == 38


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_only_task_id(manager: BoardManager, lane: str) -> str:
    """Return the task_id of the single card in *lane*."""
    lane_dir = os.path.join(manager.board_dir, lane)
    files = [f for f in os.listdir(lane_dir) if f.endswith(".md")]
    assert len(files) == 1, f"Expected 1 card in {lane}, got {files}"
    fname = files[0]
    m = fname.split("_")[0]
    return m


# ---------------------------------------------------------------------------
# DT-233 — a lane to park work in, and a scheduler that skips what is parked.
#
# Without a `blocked` lane a task waiting on the Boss either sat in
# in-progress (blocking everything behind it) or was quietly dropped. The
# point of asking asynchronously (DT-232) is that the agent picks up the
# next thing that *isn't* waiting -- which needs somewhere to put the one
# that is, and a rule for what "isn't waiting" means transitively.
# ---------------------------------------------------------------------------


def _mk(manager: BoardManager, lane: str, task_id: str, **fields: str) -> None:
    """Write a card straight into a lane with the given Status fields."""
    lines = [f"# {task_id}: {task_id}", "", "## Status", "- **Status:** Todo"]
    for key, value in fields.items():
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    path = os.path.join(manager.board_dir, lane, f"{task_id}_t.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


class TestBlockedLane:
    def test_blocked_is_a_real_lane(self) -> None:
        from board_mcp.board import LANE_STATUS, VALID_LANES

        assert "blocked" in VALID_LANES
        assert LANE_STATUS["blocked"] == "Blocked"

    def test_block_records_what_it_is_waiting_on(self, manager: BoardManager) -> None:
        """Parking a task is useless if you can't tell what would free it."""
        _mk(manager, "in-progress", "ALPHA-1")

        result = manager.block_task("ALPHA-1", "req_abc", "needs Boss approval")
        assert result["ok"] is True

        card = manager.get_task("ALPHA-1")
        assert card["lane"] == "blocked"
        assert card["blocked_by"] == "req_abc"
        assert "approval" in card["blocked_reason"]

    def test_unblock_returns_it_to_the_queue(self, manager: BoardManager) -> None:
        _mk(manager, "in-progress", "ALPHA-1")
        manager.block_task("ALPHA-1", "req_abc", "needs Boss approval")

        result = manager.unblock_task("ALPHA-1")
        assert result["ok"] is True

        card = manager.get_task("ALPHA-1")
        assert card["lane"] == "todo"
        assert not card.get("blocked_by")


class TestAvailableTasks:
    def test_picks_up_c_when_b_is_blocked(self, manager: BoardManager) -> None:
        """The whole scheduling story, in one case.

        201 (A) done, 202 (B) blocked, 203 (C) free, 204 (D) depends on B.
        C is available; D is not, because what it needs is parked.
        """
        _mk(manager, "done", "ALPHA-201")
        _mk(manager, "blocked", "ALPHA-202", blocked_by="req_1")
        _mk(manager, "todo", "ALPHA-203")
        _mk(manager, "todo", "ALPHA-204", depends_on="ALPHA-202")

        available = {t["id"] for t in manager.available_tasks()}
        assert available == {"ALPHA-203"}

    def test_blocking_is_transitive(self, manager: BoardManager) -> None:
        """204 depends on 203, 203 on 202, and 202 is blocked -- none runnable.

        Checking only direct dependencies would hand back D and waste a
        whole task's work on something that cannot finish.
        """
        _mk(manager, "blocked", "ALPHA-202", blocked_by="req_1")
        _mk(manager, "todo", "ALPHA-203", depends_on="ALPHA-202")
        _mk(manager, "todo", "ALPHA-204", depends_on="ALPHA-203")

        assert manager.available_tasks() == []

    def test_a_dependency_that_is_merely_unfinished_also_holds(
        self, manager: BoardManager
    ) -> None:
        _mk(manager, "todo", "ALPHA-201")
        _mk(manager, "todo", "ALPHA-202", depends_on="ALPHA-201")

        available = {t["id"] for t in manager.available_tasks()}
        assert available == {"ALPHA-201"}

    def test_done_dependencies_do_not_hold_anything_back(
        self, manager: BoardManager
    ) -> None:
        _mk(manager, "done", "ALPHA-201")
        _mk(manager, "todo", "ALPHA-202", depends_on="ALPHA-201")

        available = {t["id"] for t in manager.available_tasks()}
        assert available == {"ALPHA-202"}

    def test_a_cycle_does_not_hang_the_scheduler(self, manager: BoardManager) -> None:
        """Malformed input must not spin forever -- report nothing runnable."""
        _mk(manager, "todo", "ALPHA-201", depends_on="ALPHA-202")
        _mk(manager, "todo", "ALPHA-202", depends_on="ALPHA-201")

        assert manager.available_tasks() == []
