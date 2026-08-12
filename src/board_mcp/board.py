"""File-based Kanban board manager.

Board layout::

    <board_dir>/
        .kanban.lock          # exclusive write lock (ephemeral)
        backlog/
        todo/
        in-progress/
        blocked/
        done/

Each lane contains ``<PREFIX>-<NNN>_<slug>.md`` card files.

Claim semantics
---------------
A task in ``todo/`` may be claimed by one agent at a time.  The claim is
recorded as two fields in the ``## Status`` block::

    - **Claimed By:** @agent-slug
    - **Claimed At:** 2026-01-01T00:00:00+00:00

Claims expire after :data:`CLAIM_TTL_SECONDS` (default 1800 s).  An expired
claim is reclaimed by any agent; ``board_summary`` also auto-releases stale
claims on each call.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .card import (
    CardData,
    extract_section,
    parse_card,
    remove_card_field,
    set_card_field,
)

VALID_LANES: tuple[str, ...] = ("backlog", "todo", "in-progress", "blocked", "done")
# The lane a card sits in is the source of truth; the ``Status`` field is a
# human-readable mirror of it. Every lane change rewrites the field so the two
# can never drift apart (they had, across two boards, before this was added).
LANE_STATUS: dict[str, str] = {
    "backlog": "Backlog",
    "todo": "To Do",
    "in-progress": "In Progress",
    "blocked": "Blocked",
    "done": "Done",
}
# Where a card goes when whatever it was waiting on is resolved. Back to the
# queue, not straight to in-progress: the agent re-picks it through the normal
# scheduler, so it takes its turn behind anything that became more urgent
# while it was parked.
UNBLOCK_LANE: str = "todo"
CLAIM_TTL_SECONDS: int = 1800
_LOCK_STALE_SECONDS: float = 5.0
_LOCK_RETRIES: int = 10
_LOCK_DELAY: float = 0.05  # seconds


@dataclass
class TaskLocation:
    lane: str
    filename: str
    full_path: str


class BoardManager:
    """Manages a file-based Kanban board for a single project."""

    def __init__(self, board_dir: str) -> None:
        self.board_dir = board_dir

    # ── Internal helpers ────────────────────────────────────────────────────

    def _ensure_lane(self, lane: str) -> str:
        """Create *lane* directory if missing; return its absolute path."""
        path = os.path.join(self.board_dir, lane)
        os.makedirs(path, exist_ok=True)
        return path

    def _ensure_board(self) -> None:
        """Create the board directory and every lane subdirectory."""
        for lane in VALID_LANES:
            self._ensure_lane(lane)

    @contextmanager
    def _lock(self) -> Generator[None, None, None]:
        """Acquire an exclusive file lock on the board directory."""
        os.makedirs(self.board_dir, exist_ok=True)
        lock_path = os.path.join(self.board_dir, ".kanban.lock")
        acquired = False
        for attempt in range(_LOCK_RETRIES):
            if os.path.exists(lock_path):
                try:
                    age = time.monotonic() - os.path.getmtime(lock_path)
                    if age > _LOCK_STALE_SECONDS:
                        os.unlink(lock_path)
                except OSError:
                    pass
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                if attempt < _LOCK_RETRIES - 1:
                    time.sleep(_LOCK_DELAY)
        if not acquired:
            raise RuntimeError(
                f"Cannot acquire board lock after {_LOCK_RETRIES} attempts"
            )
        try:
            yield
        finally:
            try:
                os.unlink(lock_path)
            except OSError:
                pass

    def _find_task(self, task_id: str) -> TaskLocation | None:
        """Locate a task by ID across all lanes; returns ``None`` if not found."""
        for lane in VALID_LANES:
            lane_dir = os.path.join(self.board_dir, lane)
            if not os.path.isdir(lane_dir):
                continue
            for fname in os.listdir(lane_dir):
                if fname.startswith(task_id + "_") and fname.endswith(".md"):
                    return TaskLocation(
                        lane=lane,
                        filename=fname,
                        full_path=os.path.join(lane_dir, fname),
                    )
        return None

    def _read_card(self, loc: TaskLocation) -> CardData:
        with open(loc.full_path, encoding="utf-8") as fh:
            content = fh.read()
        return parse_card(content, loc.filename)

    def _write_content(self, path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def _card_summary(self, lane: str, filename: str, full_path: str) -> dict[str, Any]:
        """Return a compact summary dict for a card, safe against read errors."""
        try:
            with open(full_path, encoding="utf-8") as fh:
                content = fh.read()
            card = parse_card(content, filename)
        except OSError:
            return {"id": filename, "lane": lane, "error": "unreadable"}
        return {
            "id": card.task_id,
            "title": card.title,
            "status": card.status,
            "assignee": card.assignee,
            "milestone": card.milestone,
            "claimed_by": card.claimed_by,
            "claimed_at": card.claimed_at,
            "depends_on": card.depends_on,
            "blocks": card.blocks,
            "blocked_by": card.blocked_by,
            "blocked_reason": card.blocked_reason,
            "lane": lane,
        }

    def _infer_prefix(self) -> str:
        """Infer the task-ID prefix from existing cards (e.g. ``ALPHA``).

        Falls back to ``'TASK'`` when the board is empty.
        """
        for lane in VALID_LANES:
            lane_dir = os.path.join(self.board_dir, lane)
            if not os.path.isdir(lane_dir):
                continue
            for fname in os.listdir(lane_dir):
                m = re.match(r"^([A-Z]+)-\d+", fname)
                if m:
                    return m.group(1)
        return "TASK"

    def _compute_next_id(self) -> tuple[str, int]:
        """Return ``(prefix, next_number)`` by scanning all lanes."""
        prefix = self._infer_prefix()
        max_num = 0
        for lane in VALID_LANES:
            lane_dir = os.path.join(self.board_dir, lane)
            if not os.path.isdir(lane_dir):
                continue
            for fname in os.listdir(lane_dir):
                m = re.match(rf"^{re.escape(prefix)}-(\d+)", fname)
                if m:
                    max_num = max(max_num, int(m.group(1)))
        return prefix, max_num + 1

    def _is_claim_stale(self, claimed_at: str | None) -> bool:
        """Return ``True`` if *claimed_at* is older than :data:`CLAIM_TTL_SECONDS`."""
        if not claimed_at:
            return False
        try:
            # Handle both offset-aware and naive ISO strings
            raw = claimed_at.rstrip("Z")
            if "+" in raw or raw.endswith("00:00"):
                ts = datetime.fromisoformat(claimed_at)
            else:
                ts = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            return age > CLAIM_TTL_SECONDS
        except ValueError:
            return False

    # ── Tool implementations ────────────────────────────────────────────────

    def next_id(self) -> dict[str, Any]:
        """Preview the next available task ID (non-atomic)."""
        prefix, num = self._compute_next_id()
        padded = str(num).zfill(3)
        return {"id": f"{prefix}-{padded}", "number": num}

    def create_task(
        self,
        lane: str,
        slug: str,
        content: str,
        milestone: str | None = None,
    ) -> dict[str, Any]:
        """Atomically create a new task card under a file lock."""
        if lane not in VALID_LANES:
            return {"ok": False, "reason": f"invalid_lane: {lane}"}
        with self._lock():
            prefix, num = self._compute_next_id()
            padded = str(num).zfill(3)
            task_id = f"{prefix}-{padded}"
            lane_dir = self._ensure_lane(lane)
            filename = f"{task_id}_{slug}.md"
            dest = os.path.join(lane_dir, filename)
            if os.path.exists(dest):
                return {"ok": False, "reason": f"file_exists: {dest}"}
            final_content = content
            if milestone and "**Milestone:**" not in final_content:
                final_content = set_card_field(final_content, "Milestone", milestone)
            self._write_content(dest, final_content)
        return {"ok": True, "id": task_id, "path": dest}

    def claim_task(self, task_id: str, agent_slug: str) -> dict[str, Any]:
        """Atomically claim a ``todo/`` task for *agent_slug*."""
        with self._lock():
            loc = self._find_task(task_id)
            if not loc:
                return {"ok": False, "reason": "task_not_found"}
            if loc.lane != "todo":
                return {"ok": False, "reason": f"wrong_lane: {loc.lane}"}
            card = self._read_card(loc)
            # Assignee gate: only permit if unassigned or matches requester
            assignee = card.assignee.lstrip("@")
            requester = agent_slug.lstrip("@")
            if assignee and assignee != requester:
                return {
                    "ok": False,
                    "reason": f"assignee_mismatch: assigned to {card.assignee}",
                }
            # Active-claim gate
            if card.claimed_at and not self._is_claim_stale(card.claimed_at):
                return {
                    "ok": False,
                    "reason": (
                        f"already_claimed_by: {card.claimed_by} at {card.claimed_at}"
                    ),
                }
            now = datetime.now(timezone.utc).isoformat()
            updated = set_card_field(card.content, "Claimed By", agent_slug)
            updated = set_card_field(updated, "Claimed At", now)
            self._write_content(loc.full_path, updated)
        return {"ok": True, "id": task_id, "claimed_at": now}

    def release_claim(self, task_id: str, agent_slug: str) -> dict[str, Any]:
        """Release a claim.  Only the claimant or ``principal-engineer`` may release."""
        with self._lock():
            loc = self._find_task(task_id)
            if not loc:
                return {"ok": False, "reason": "task_not_found"}
            card = self._read_card(loc)
            claimant = (card.claimed_by or "").lstrip("@")
            requester = agent_slug.lstrip("@")
            if claimant and claimant != requester and requester != "principal-engineer":
                return {"ok": False, "reason": f"claim_owned_by: {card.claimed_by}"}
            updated = remove_card_field(card.content, "Claimed By")
            updated = remove_card_field(updated, "Claimed At")
            self._write_content(loc.full_path, updated)
        return {"ok": True, "id": task_id}

    def move_task(
        self, task_id: str, target_lane: str, agent_slug: str
    ) -> dict[str, Any]:
        """Move a task between lanes.

        Moving to ``in-progress`` requires a prior :meth:`claim_task` and
        enforces a WIP limit of 1 per agent.
        """
        if target_lane not in VALID_LANES:
            return {"ok": False, "reason": f"invalid_lane: {target_lane}"}
        with self._lock():
            loc = self._find_task(task_id)
            if not loc:
                return {"ok": False, "reason": "task_not_found"}
            if target_lane == "in-progress":
                card = self._read_card(loc)
                if not card.claimed_at:
                    return {
                        "ok": False,
                        "reason": "not_claimed: call board_claim_task first",
                    }
                claimant = (card.claimed_by or "").lstrip("@")
                requester = agent_slug.lstrip("@")
                if claimant and claimant != requester:
                    return {
                        "ok": False,
                        "reason": f"claim_owned_by: {card.claimed_by}",
                    }
                # WIP = 1 per agent
                ip_dir = os.path.join(self.board_dir, "in-progress")
                if os.path.isdir(ip_dir):
                    for fname in os.listdir(ip_dir):
                        if not fname.endswith(".md"):
                            continue
                        with open(os.path.join(ip_dir, fname), encoding="utf-8") as fh:
                            other_card = parse_card(fh.read(), fname)
                        other_assignee = other_card.assignee.lstrip("@")
                        other_claimant = (other_card.claimed_by or "").lstrip("@")
                        if requester in (other_assignee, other_claimant):
                            return {
                                "ok": False,
                                "reason": (
                                    f"wip_limit_exceeded: {other_card.task_id} "
                                    f"already in-progress for {agent_slug}"
                                ),
                            }
            card = self._read_card(loc)
            self._write_content(
                loc.full_path,
                set_card_field(card.content, "Status", LANE_STATUS[target_lane]),
            )
            dest_dir = self._ensure_lane(target_lane)
            dest_path = os.path.join(dest_dir, loc.filename)
            os.rename(loc.full_path, dest_path)
        return {"ok": True, "id": task_id, "to": target_lane}

    def done_task(self, task_id: str, agent_slug: str) -> dict[str, Any]:
        """Move a task from ``in-progress`` to ``done`` and strip its claim."""
        with self._lock():
            loc = self._find_task(task_id)
            if not loc:
                return {"ok": False, "reason": "task_not_found"}
            if loc.lane != "in-progress":
                return {"ok": False, "reason": f"wrong_lane: {loc.lane}"}
            card = self._read_card(loc)
            if agent_slug:
                claimant = (card.claimed_by or "").lstrip("@")
                requester = agent_slug.lstrip("@")
                if claimant and claimant != requester:
                    return {
                        "ok": False,
                        "reason": f"assignee_mismatch: claimed by {card.claimed_by}",
                    }
            updated = remove_card_field(card.content, "Claimed By")
            updated = remove_card_field(updated, "Claimed At")
            updated = set_card_field(updated, "Status", LANE_STATUS["done"])
            self._write_content(loc.full_path, updated)
            done_dir = self._ensure_lane("done")
            dest_path = os.path.join(done_dir, loc.filename)
            os.rename(loc.full_path, dest_path)
        return {"ok": True, "id": task_id}

    def block_task(self, task_id: str, req_id: str, reason: str) -> dict[str, Any]:
        """Park *task_id* until *req_id* is answered.

        Called when a task asks for approval asynchronously (DT-232). The
        card moves to the `blocked` lane carrying the request it is waiting
        on, so anyone — the next session, the Boss, /pending — can tell what
        would free it without reading the agent's mind.
        """
        result = self.move_task(task_id, "blocked", "@scheduler")
        if not result.get("ok"):
            return result

        loc = self._find_task(task_id)
        if not loc:  # pragma: no cover — move_task just succeeded
            return {"ok": False, "reason": "task_not_found"}
        card = self._read_card(loc)
        content = set_card_field(card.content, "Blocked By", req_id)
        content = set_card_field(content, "Blocked Reason", reason)
        self._write_content(
            os.path.join(self.board_dir, loc.lane, loc.filename), content
        )
        return {"ok": True, "id": task_id, "lane": "blocked", "blocked_by": req_id}

    def unblock_task(self, task_id: str) -> dict[str, Any]:
        """Return a parked task to the queue and forget what held it."""
        loc = self._find_task(task_id)
        if not loc:
            return {"ok": False, "reason": "task_not_found"}
        if loc.lane != "blocked":
            return {"ok": False, "reason": f"not_blocked: {loc.lane}"}

        card = self._read_card(loc)
        content = remove_card_field(card.content, "Blocked By")
        content = remove_card_field(content, "Blocked Reason")
        self._write_content(
            os.path.join(self.board_dir, loc.lane, loc.filename), content
        )
        return self.move_task(task_id, UNBLOCK_LANE, "@scheduler")

    def available_tasks(self) -> list[dict[str, Any]]:
        """Tasks that can actually be started right now.

        A task is available when it is queued in `todo` and every dependency
        it names is finished.

        "Finished" is the whole rule, and it is transitive for free: a task
        whose dependency is blocked is held because that dependency is not
        done, and the task behind *that* is held for the same reason, all
        the way down. Walking the graph to distinguish "blocked" from
        "merely unstarted" would compute a different label for the same
        answer — either way it cannot be started yet.

        An unknown dependency id (typo'd, or a deleted card) also holds.
        Running the task anyway would silently drop whatever that
        dependency was there to guarantee.
        """
        done: set[str] = set()
        queued: list[dict[str, Any]] = []
        for lane in VALID_LANES:
            for card in self.list_lane(lane):
                if "error" in card:
                    continue
                if lane == "done":
                    done.add(card["id"])
                elif lane == "todo":
                    queued.append(card)

        available = [
            card
            for card in queued
            if all(dep in done for dep in card.get("depends_on", []))
        ]
        return sorted(available, key=lambda c: str(c["id"]))

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Return the full content and parsed fields of a single task."""
        loc = self._find_task(task_id)
        if not loc:
            return {"ok": False, "reason": "task_not_found"}
        card = self._read_card(loc)
        return {
            "ok": True,
            "id": task_id,
            "lane": loc.lane,
            "filename": loc.filename,
            "title": card.title,
            "status": card.status,
            "assignee": card.assignee,
            "milestone": card.milestone,
            "claimed_by": card.claimed_by,
            "claimed_at": card.claimed_at,
            "depends_on": card.depends_on,
            "blocks": card.blocks,
            "blocked_by": card.blocked_by,
            "blocked_reason": card.blocked_reason,
            "content": card.content,
        }

    def list_lane(self, lane: str) -> list[dict[str, Any]]:
        """Return structured summaries for all cards in *lane*."""
        if lane not in VALID_LANES:
            raise ValueError(f"Invalid lane: {lane}")
        lane_dir = os.path.join(self.board_dir, lane)
        if not os.path.isdir(lane_dir):
            return []
        results: list[dict[str, Any]] = []
        for fname in sorted(os.listdir(lane_dir)):
            if fname.endswith(".md"):
                full_path = os.path.join(lane_dir, fname)
                results.append(self._card_summary(lane, fname, full_path))
        return results

    def summary(self) -> dict[str, Any]:
        """Snapshot all lanes and auto-release stale claims in ``todo/``."""
        lanes: dict[str, list[dict[str, Any]]] = {}
        for lane in VALID_LANES:
            lanes[lane] = self.list_lane(lane)

        # Collect stale-claim candidates (read phase — no lock held yet)
        stale_ids = [
            t["id"]
            for t in lanes.get("todo", [])
            if t.get("claimed_at")
            and self._is_claim_stale(
                t.get("claimed_at")  # type: ignore[arg-type]
            )
        ]

        # Release each stale claim under lock with double-check
        for task_id in stale_ids:
            with self._lock():
                loc = self._find_task(task_id)
                if not loc:
                    continue
                card = self._read_card(loc)
                if not card.claimed_at or not self._is_claim_stale(card.claimed_at):
                    continue
                updated = remove_card_field(card.content, "Claimed By")
                updated = remove_card_field(updated, "Claimed At")
                self._write_content(loc.full_path, updated)
                for entry in lanes.get("todo", []):
                    if entry.get("id") == task_id:
                        entry["claimed_by"] = None
                        entry["claimed_at"] = None
                        entry["_stale_claim_released"] = True

        counts = {lane: len(tasks) for lane, tasks in lanes.items()}
        return {"counts": counts, "lanes": lanes}

    def orchestrate(self, task_ids: list[str]) -> dict[str, Any]:
        """Dependency-resolve *task_ids* into parallel execution waves."""
        tasks: list[dict[str, Any]] = []
        for tid in task_ids:
            loc = self._find_task(tid)
            if not loc:
                continue
            card = self._read_card(loc)
            tasks.append(
                {
                    "id": tid,
                    "title": card.title,
                    "assignee": card.assignee,
                    "depends_on": [d for d in card.depends_on if d in task_ids],
                }
            )

        task_map: dict[str, dict[str, Any]] = {t["id"]: t for t in tasks}
        level_map: dict[str, int] = {}
        for t in tasks:
            _compute_level(t["id"], task_map, level_map)

        waves = _build_waves(tasks, level_map)
        return {"total_tasks": len(tasks), "waves": waves}

    def agent_context(self, task_id: str) -> dict[str, Any]:
        """Return a compact handoff envelope for a task (~100-150 tokens)."""
        loc = self._find_task(task_id)
        if not loc:
            return {"ok": False, "reason": "task_not_found"}
        card = self._read_card(loc)
        content = card.content

        # Objective: prefer Objective, fall back to Requirements, then Description
        objective = (
            extract_section(content, "Objective")
            or extract_section(content, "Requirements")
            or extract_section(content, "Description")
        ).strip()

        action_block = extract_section(content, "Action Items")
        criteria = re.findall(r"^\s*-\s+\[[ xX]\]\s+.+$", action_block, re.MULTILINE)
        notes_raw = extract_section(content, "Technical Notes").strip()
        notes: str | None = notes_raw if notes_raw else None
        files = list(
            dict.fromkeys(
                m.strip("`")
                for m in re.findall(r"`[^`]+\.[a-zA-Z]{1,6}`", action_block)
            )
        )

        return {
            "ok": True,
            "task_id": task_id,
            "lane": loc.lane,
            "title": card.title,
            "assignee": card.assignee,
            "objective": objective,
            "acceptance_criteria": criteria,
            "technical_notes": notes,
            "relevant_files": files,
            "depends_on": card.depends_on,
            "blocks": card.blocks,
        }

    def report(self, audience: str) -> dict[str, Any]:
        """Return structured board data grouped by milestone.

        *audience* is ``'exec' | 'staff' | 'dev'`` and is echoed back as
        metadata — the caller writes the prose.
        """
        milestone_data: dict[str, dict[str, Any]] = {}
        in_progress_list: list[dict[str, Any]] = []
        blocked_list: list[dict[str, Any]] = []

        for lane in VALID_LANES:
            lane_dir = os.path.join(self.board_dir, lane)
            if not os.path.isdir(lane_dir):
                continue
            for fname in sorted(os.listdir(lane_dir)):
                if not fname.endswith(".md"):
                    continue
                full_path = os.path.join(lane_dir, fname)
                try:
                    with open(full_path, encoding="utf-8") as fh:
                        raw = fh.read()
                    card = parse_card(raw, fname)
                except OSError:
                    continue

                ms = card.milestone or "unassigned"
                if ms not in milestone_data:
                    milestone_data[ms] = {
                        "milestone": ms,
                        "total": 0,
                        "done": 0,
                        "in_progress": 0,
                        "todo": 0,
                        "backlog": 0,
                        "completion_pct": 0.0,
                    }

                entry = milestone_data[ms]
                entry["total"] = int(entry["total"]) + 1
                lane_key = lane.replace("-", "_")
                entry[lane_key] = int(entry.get(lane_key, 0)) + 1

                if lane == "in-progress":
                    ip_entry: dict[str, Any] = {
                        "id": card.task_id,
                        "title": card.title,
                        "assignee": card.assignee,
                        "claimed_by": card.claimed_by,
                    }
                    in_progress_list.append(ip_entry)
                    if "blocked" in card.status.lower():
                        blocked_list.append(ip_entry)

        for entry in milestone_data.values():
            total = int(entry["total"])
            done = int(entry["done"])
            entry["completion_pct"] = round(done / total * 100, 1) if total > 0 else 0.0

        return {
            "audience": audience,
            "milestones": list(milestone_data.values()),
            "in_progress": in_progress_list,
            "blocked": blocked_list,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def query_project_context(
        self,
        project_root: str,
        files: list[str],
        keywords: list[str],
    ) -> dict[str, Any]:
        """Search project context files for keyword-matching sections."""
        results: list[dict[str, Any]] = []
        for file_path in files:
            if os.path.isabs(file_path):
                resolved = file_path
            else:
                # Try .claude/ prefix first (Claude Code convention)
                candidate = os.path.join(project_root, ".claude", file_path)
                resolved = (
                    candidate
                    if os.path.exists(candidate)
                    else os.path.join(project_root, file_path)
                )
            if not os.path.exists(resolved):
                results.append({"file": file_path, "error": "file_not_found"})
                continue
            try:
                with open(resolved, encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
            except OSError:
                results.append({"file": file_path, "error": "read_error"})
                continue
            sections = _extract_matching_sections(lines, keywords)
            for section in sections:
                results.append({"file": file_path, **section})
        return {"results": results, "total_matches": len(results)}


def _compute_level(
    tid: str,
    task_map: dict[str, dict[str, Any]],
    level_map: dict[str, int],
) -> int:
    """Recursively compute the topological level for *tid*."""
    if tid in level_map:
        return level_map[tid]
    task = task_map.get(tid)
    if not task:
        return 0
    deps: list[str] = task["depends_on"]
    if not deps:
        level_map[tid] = 0
        return 0
    lvl = max(_compute_level(d, task_map, level_map) for d in deps) + 1
    level_map[tid] = lvl
    return lvl


def _build_waves(
    tasks: list[dict[str, Any]], level_map: dict[str, int]
) -> list[dict[str, Any]]:
    """Group *tasks* into ordered execution waves based on *level_map*."""
    wave_map: dict[int, list[dict[str, Any]]] = {}
    for t in tasks:
        lvl = level_map.get(t["id"], 0)
        wave_map.setdefault(lvl, []).append(t)

    waves: list[dict[str, Any]] = []
    for lvl in sorted(wave_map.keys()):
        wave_tasks = wave_map[lvl]
        agents = [t["assignee"] for t in wave_tasks]
        unique_agents = set(agents)
        conflict = len(unique_agents) < len(agents)
        mode = "parallel" if len(wave_tasks) > 1 else "sequential"
        rationale = _wave_rationale(wave_tasks, unique_agents, conflict)
        waves.append(
            {
                "wave": lvl + 1,
                "mode": mode,
                "depends_on_wave": lvl if lvl > 0 else None,
                "agent_conflict": conflict,
                "rationale": rationale,
                "tasks": [
                    {"id": t["id"], "assignee": t["assignee"], "title": t["title"]}
                    for t in wave_tasks
                ],
            }
        )
    return waves


def _wave_rationale(
    wave_tasks: list[dict[str, Any]],
    unique_agents: set[str],
    conflict: bool,
) -> str:
    """Return a human-readable rationale string for a wave."""
    n = len(wave_tasks)
    if n == 1:
        return "Single task in this wave."
    if conflict:
        return f"{n} tasks share an agent — sub-sequence required within wave."
    return f"{n} tasks, {len(unique_agents)} different agents, no mutual dependencies."


def _extract_matching_sections(
    lines: list[str], keywords: list[str], max_lines: int = 60
) -> list[dict[str, Any]]:
    """Return sections from *lines* whose heading or body matches any keyword."""
    heading_re = re.compile(r"^(#{1,4})\s+(.+)$")
    sections: list[dict[str, Any]] = []
    kw_lower = [k.lower() for k in keywords]
    i = 0
    while i < len(lines):
        hm = heading_re.match(lines[i])
        if hm:
            level = len(hm.group(1))
            title = hm.group(2)
            start = i
            i += 1
            while i < len(lines):
                nm = heading_re.match(lines[i])
                if nm and len(nm.group(1)) <= level:
                    break
                i += 1
            body = "\n".join(lines[start + 1 : i])
            title_hit = any(kw in title.lower() for kw in kw_lower)
            body_hit = not title_hit and any(kw in body.lower() for kw in kw_lower)
            if title_hit or body_hit:
                sections.append(
                    {
                        "section_title": title,
                        "content": "\n".join(lines[start : min(i, start + max_lines)]),
                        "line_start": start + 1,
                        "truncated": (i - start) > max_lines,
                    }
                )
            continue
        i += 1

    if not sections:
        seen: set[str] = set()
        j = 0
        while j < len(lines):
            if any(kw in lines[j].lower() for kw in kw_lower):
                s = max(0, j - 3)
                e = min(len(lines), j + 7)
                key = f"{s}-{e}"
                if key not in seen:
                    seen.add(key)
                    sections.append(
                        {
                            "section_title": "(inline match)",
                            "content": "\n".join(lines[s:e]),
                            "line_start": s + 1,
                            "truncated": False,
                        }
                    )
                j = e
            else:
                j += 1

    return sections
