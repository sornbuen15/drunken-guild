"""State machine for Discord approval requests.

Replaces the old file-polling "Silent Wait Protocol" (outbox/inbox JSON +
agent schedule/resume hack) with real in-process asyncio coordination owned
by the persistent daemon: post -> wait -> remind once -> escalate.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import discord
from jira_mcp.jira_client import JiraClient

from service.discord_runner import AgentRunner

OUTBOX_FILE = os.path.join(os.getcwd(), ".agents", "discord_outbox.json")
APPROVAL_TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"))

ESCALATION_JIRA_TEMPLATE = (
    "⚠️ Blocked — Awaiting Boss Approval\n\n"
    "Paused after 2 reminders with no response on Discord.\n"
    "Question: {action} — {reason}\n"
    "Requested at: {created_at}\n\n"
    "Work has stopped. No commit has been made. Reply on Discord or update "
    "this ticket, then resume the task."
)

ESCALATION_DISCORD_TEMPLATE = (
    "⏸️ **Task paused — no response after 2 reminders**\n"
    "**Ticket:** {ticket_key}\n"
    "**What's needed:** {action}\n"
    "**Details:** {jira_url}/browse/{ticket_key}"
)

JIRA_COMMENT_FAILED_NOTE = (
    "\n\n⚠️ **Note:** the Jira comment for this ticket failed to post "
    "({error}). The ticket itself has NOT been updated — check it manually."
)


@dataclass
class ApprovalRequest:
    req_id: str
    action: str
    reason: str
    ticket_key: str
    status: str = "pending"  # pending | approved | rejected | escalated
    attempt: int = 1
    discord_message_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    # Which AgentRunner.task_generation was active when this request was
    # made. None for requests recovered from a snapshot after a daemon
    # restart, where there's no reliable way to know — escalation must not
    # guess and kill an unrelated task in that case. Not persisted to disk;
    # meaningless across a restart.
    originating_generation: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "req_id": self.req_id,
            "action": self.action,
            "reason": self.reason,
            "ticket_key": self.ticket_key,
            "status": self.status,
            "attempt": self.attempt,
            "discord_message_id": self.discord_message_id,
            "created_at": self.created_at,
        }


class ApprovalManager:
    def __init__(
        self,
        client: discord.Client,
        channel_id: int,
        agent_runner: AgentRunner,
        jira_client: JiraClient,
        timeout_seconds: int = APPROVAL_TIMEOUT_SECONDS,
    ) -> None:
        self.client = client
        self.channel_id = channel_id
        self.agent_runner = agent_runner
        self.jira_client = jira_client
        self.timeout_seconds = timeout_seconds
        self._requests: dict[str, ApprovalRequest] = {}
        self._futures: dict[str, "asyncio.Future[dict[str, Any]]"] = {}
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._message_to_req: dict[int, str] = {}
        self._snapshot_lock = asyncio.Lock()

    async def _get_channel(self) -> Any:
        channel = self.client.get_channel(self.channel_id)
        if channel:
            return channel
        try:
            return await self.client.fetch_channel(self.channel_id)
        except Exception:
            return None

    async def request(
        self, action: str, reason: str, ticket_key: str
    ) -> dict[str, Any]:
        req_id = f"req_{os.urandom(4).hex()}"
        req = ApprovalRequest(
            req_id=req_id,
            action=action,
            reason=reason,
            ticket_key=ticket_key,
            originating_generation=self.agent_runner.task_generation,
        )
        self._requests[req_id] = req

        loop = asyncio.get_running_loop()
        fut: "asyncio.Future[dict[str, Any]]" = loop.create_future()
        self._futures[req_id] = fut

        await self._post_question(req, reminder=False)
        await self._snapshot()
        self._timers[req_id] = asyncio.create_task(self._watch_timeout(req_id))

        try:
            return await fut
        finally:
            timer = self._timers.pop(req_id, None)
            if timer:
                timer.cancel()

    async def _post_question(self, req: ApprovalRequest, reminder: bool) -> None:
        channel = await self._get_channel()
        if not channel:
            print(
                f"[ApprovalManager] Could not resolve channel {self.channel_id} "
                f"to post approval request {req.req_id}",
                flush=True,
            )
            return
        prefix = (
            "⏰ **Reminder — still waiting:**"
            if reminder
            else "🤖 **Agent requires permission:**"
        )
        text = (
            f"{prefix}\n**Ticket:** {req.ticket_key}\n**Action:** {req.action}\n"
            f"**Reason:** {req.reason}\n\n*React with 👍 to approve, 👎 to reject.*"
        )
        msg = await channel.send(text)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        # A reminder repost supersedes the original message — drop its
        # mapping so it doesn't linger forever (it's still harmless if left,
        # since resolve() checks req.status, but there's no reason to keep it).
        if req.discord_message_id is not None:
            self._message_to_req.pop(req.discord_message_id, None)
        req.discord_message_id = msg.id
        self._message_to_req[msg.id] = req.req_id

    async def _watch_timeout(self, req_id: str) -> None:
        try:
            await asyncio.sleep(self.timeout_seconds)
        except asyncio.CancelledError:
            return

        req = self._requests.get(req_id)
        if not req or req.status != "pending":
            return

        if req.attempt >= 2:
            await self._escalate(req_id)
        else:
            req.attempt = 2
            await self._post_question(req, reminder=True)
            await self._snapshot()
            self._timers[req_id] = asyncio.create_task(self._watch_timeout(req_id))

    async def resolve(self, message_id: int, approved: bool) -> bool:
        req_id = self._message_to_req.pop(message_id, None)
        if not req_id:
            return False
        req = self._requests.get(req_id)
        if not req or req.status != "pending":
            return False

        req.status = "approved" if approved else "rejected"
        timer = self._timers.pop(req_id, None)
        if timer:
            timer.cancel()
        # Terminal, resolved state — nothing else needs to find this request
        # again (is_pending_or_escalated only cares about pending/escalated),
        # so drop it now rather than let self._requests grow forever.
        self._requests.pop(req_id, None)
        # Snapshot BEFORE resolving the future: setting the future's result
        # just schedules the waiting request() coroutine to resume on a
        # future loop iteration, it doesn't block on it — resolving first
        # would let the caller (and a test reading the file right after)
        # race ahead of this write completing.
        await self._snapshot()
        fut = self._futures.pop(req_id, None)
        if fut and not fut.done():
            fut.set_result({"status": req.status})
        return True

    async def _escalate(self, req_id: str) -> None:
        req = self._requests.get(req_id)
        if not req:
            return
        req.status = "escalated"
        if req.discord_message_id is not None:
            self._message_to_req.pop(req.discord_message_id, None)

        if (
            req.originating_generation is not None
            and req.originating_generation == self.agent_runner.task_generation
        ):
            await self.agent_runner.cancel_current_task()
        else:
            print(
                f"[ApprovalManager] Skipping task cancel for {req_id}: the task "
                "that made this request is no longer the one running (or this "
                "request was recovered after a restart with no known origin) — "
                "not killing an unrelated task.",
                flush=True,
            )

        jira_comment_error: str | None = None
        try:
            await self.jira_client.add_comment(
                req.ticket_key,
                ESCALATION_JIRA_TEMPLATE.format(
                    action=req.action,
                    reason=req.reason,
                    created_at=time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(req.created_at)
                    ),
                ),
            )
        except Exception as e:
            jira_comment_error = str(e)
            print(
                f"[ApprovalManager] Failed to comment on {req.ticket_key}: {e}",
                flush=True,
            )

        channel = await self._get_channel()
        if channel:
            try:
                summary = ESCALATION_DISCORD_TEMPLATE.format(
                    ticket_key=req.ticket_key,
                    action=req.action,
                    jira_url=self.jira_client.base_url,
                )
                if jira_comment_error:
                    summary += JIRA_COMMENT_FAILED_NOTE.format(error=jira_comment_error)
                await channel.send(summary)
            except Exception as e:
                print(
                    f"[ApprovalManager] Failed to post escalation summary: {e}",
                    flush=True,
                )

        # Deliberately NOT removed from self._requests: is_pending_or_escalated()
        # must keep reporting "escalated" (blocking commits) until a human
        # resolves it some other way — unlike approved/rejected, this isn't
        # a terminal state as far as the pre-commit safety net is concerned.
        # Snapshot BEFORE resolving the future, same reasoning as resolve().
        await self._snapshot()
        fut = self._futures.pop(req_id, None)
        if fut and not fut.done():
            fut.set_result({"status": "escalated"})

    def is_pending_or_escalated(self, ticket_key: str) -> Optional[str]:
        for req in self._requests.values():
            if req.ticket_key == ticket_key and req.status in ("pending", "escalated"):
                return req.status
        return None

    async def _snapshot(self) -> None:
        # Only "pending" is persisted. "escalated" is a terminal state that's
        # already been fully actioned (Jira commented, Discord notified) —
        # keeping it here would make recover_from_snapshot() re-escalate the
        # same request (duplicate comment/notification) on every subsequent
        # daemon restart, forever.
        #
        # The data computation AND the write are both inside the lock: two
        # snapshot calls close together (e.g. one request resolving while
        # another is reminded) each offload their write via asyncio.to_thread,
        # which gives no FIFO guarantee across threads — without this lock an
        # older call's write could land on disk after a newer one's,
        # clobbering it with stale data. asyncio.Lock wakes waiters in the
        # order they queued, so serializing here preserves call order.
        async with self._snapshot_lock:
            data = {
                req_id: r.to_dict()
                for req_id, r in self._requests.items()
                if r.status == "pending"
            }
            # Offloaded to a thread: this runs on every state transition, and
            # blocking file I/O directly on the event loop would also stall
            # Discord gateway heartbeat/dispatch, which shares this same loop.
            await asyncio.to_thread(self._write_snapshot_file, data)

    def _write_snapshot_file(self, data: dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
            with open(OUTBOX_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ApprovalManager] Failed to write snapshot: {e}", flush=True)

    async def recover_from_snapshot(self) -> None:
        """Called once after the daemon (re)connects.

        Any entries found here belong to a caller that was talking to a
        previous daemon process over a socket connection that's now gone —
        there is no future left to resolve. We can't silently resume them
        (the original agent already got a connection error and moved on),
        so we escalate on sight: comment on the ticket, notify Discord, and
        clear the snapshot. Erring toward "flag it" over "lose it silently".
        """
        if not os.path.exists(OUTBOX_FILE):
            return
        try:
            with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not data:
            return

        for req_id, payload in data.items():
            if payload.get("status") not in ("pending", "escalated"):
                continue
            print(
                f"[ApprovalManager] Recovering orphaned approval {req_id} from a "
                "previous daemon run — escalating.",
                flush=True,
            )
            req = ApprovalRequest(
                req_id=req_id,
                action=payload.get(
                    "action", "(unknown — recovered after daemon restart)"
                ),
                reason=payload.get("reason", ""),
                ticket_key=payload.get("ticket_key", "UNKNOWN"),
                attempt=payload.get("attempt", 2),
                created_at=payload.get("created_at", time.time()),
            )
            self._requests[req_id] = req
            await self._escalate(req_id)
