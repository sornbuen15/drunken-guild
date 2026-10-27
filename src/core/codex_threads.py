"""Read child-thread metadata for Guild-owned Codex sessions via app-server.

The CLI JSON stream can omit subagent creation events. App-server's experimental
descendant filter and subAgentActivity items provide actual child IDs and state.
Only coordination fields are retained; messages and reasoning are discarded.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Any

from .redact import redact

MAX_REPLY = 2_000_000
TIMEOUT = 6.0
SOURCE_KINDS = [
    "subAgent",
    "subAgentReview",
    "subAgentCompact",
    "subAgentThreadSpawn",
    "subAgentOther",
]


class CodexThreadObserver:
    """A short-lived read-only app-server client for one managed Codex job."""

    def __init__(self, executable: str | None = None) -> None:
        command = executable or shutil.which("codex")
        if not command:
            raise OSError("Codex CLI is unavailable for subagent monitoring")
        self.process = subprocess.Popen(
            [command, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.replies: queue.Queue[dict[str, Any]] = queue.Queue()
        self.next_id = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self._request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "drunken_guild",
                        "title": "Drunken Guild",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            self._send({"method": "initialized", "params": {}})
        except (OSError, ValueError):
            self.close()
            raise

    def _read(self) -> None:
        assert self.process.stdout is not None
        while line := self.process.stdout.readline(MAX_REPLY + 1):
            if len(line) > MAX_REPLY or not line.endswith("\n"):
                self.replies.put(
                    {"error": "App-server reply exceeds the monitor limit"}
                )
                return
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get("id"), int):
                self.replies.put(value)

    def _send(self, message: dict[str, Any]) -> None:
        if not self.process.stdin or self.process.poll() is not None:
            raise OSError("Codex app-server stopped")
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        ident = self.next_id
        self._send({"id": ident, "method": method, "params": params})
        deadline = time.monotonic() + TIMEOUT
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                reply = self.replies.get(timeout=max(0.01, remaining))
            except queue.Empty as exc:
                raise OSError(f"Codex app-server timed out on {method}") from exc
            if "error" in reply:
                raise ValueError(f"Codex app-server could not answer {method}")
            if reply.get("id") == ident:
                result = reply.get("result")
                if not isinstance(result, dict):
                    raise ValueError(f"Invalid app-server reply for {method}")
                return result
        raise OSError(f"Codex app-server timed out on {method}")

    def children(self, parent_id: str) -> list[dict[str, str | None]]:
        """Return reported descendants, without claiming unknown activity is idle."""
        found = self._list_children(parent_id)
        if found:
            self._enrich_children(parent_id, found)
        return list(found.values())

    def _list_children(self, parent_id: str) -> dict[str, dict[str, str | None]]:
        found: dict[str, dict[str, str | None]] = {}
        cursor: str | None = None
        while len(found) < 128:
            result = self._request(
                "thread/list",
                {
                    "ancestorThreadId": parent_id,
                    "sourceKinds": SOURCE_KINDS,
                    "limit": 100,
                    "cursor": cursor,
                },
            )
            entries = result.get("data")
            if not isinstance(entries, list):
                raise ValueError("Invalid child-thread listing")
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    continue
                child_id = entry["id"]
                found[child_id] = {
                    "id": child_id,
                    "parent_id": entry.get("parentThreadId")
                    if isinstance(entry.get("parentThreadId"), str)
                    else parent_id,
                    "task": redact(entry.get("name") or entry.get("preview") or "")[
                        :240
                    ]
                    or "Task not reported",
                    "status": "unknown",
                    "activity": "Child thread reported",
                }
            cursor = result.get("nextCursor")
            if not isinstance(cursor, str) or not cursor:
                break
        return found

    def _enrich_children(
        self, parent_id: str, found: dict[str, dict[str, str | None]]
    ) -> None:
        # The CLI stream may omit child creation, but stored coordination items
        # supply a task path and state. Read only the current parent turn, then
        # keep only subAgentActivity fields; never persist conversation items.
        turns = self._request(
            "thread/turns/list",
            {"threadId": parent_id, "limit": 1, "itemsView": "full"},
        ).get("data", [])
        if not isinstance(turns, list):
            return
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("items"), list):
                continue
            for item in turn["items"]:
                if not isinstance(item, dict) or item.get("type") != "subAgentActivity":
                    continue
                child_id = item.get("agentThreadId")
                child = found.get(child_id) if isinstance(child_id, str) else None
                if child is not None:
                    self._apply_activity(child, item)

    @staticmethod
    def _apply_activity(child: dict[str, str | None], item: dict[str, Any]) -> None:
        path = item.get("agentPath")
        if isinstance(path, str) and path:
            child["task"] = redact(path.rsplit("/", 1)[-1].replace("_", " "))[:240]
        kind = item.get("kind")
        if kind in {"started", "interacted"}:
            child["status"] = "running"
        elif kind in {"completed", "failed"}:
            child["status"] = kind
        if isinstance(kind, str):
            child["activity"] = kind

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()
