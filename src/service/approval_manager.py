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

from core import paths
from jira_mcp.jira_client import JiraClient
from service.discord_runner import AgentRunner


def snapshot_file() -> str:
    """Where pending approvals and uncollected answers are persisted.

    This is the only thing standing between a daemon restart and a lost
    approval, so it is state and belongs under ``$DRUNKEN_HOME``. Derived from
    ``os.getcwd()`` it survived only because launchd pins WorkingDirectory —
    start the daemon from anywhere else and the snapshot silently became a
    different file.
    """
    return str(paths.approval_snapshot_path())


APPROVAL_TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"))

# Reminder spacing for async requests, as multipliers of timeout_seconds:
# 15 min, then an hour, then daily. The last entry repeats forever — an async
# request has no caller sitting on a socket, so there is nothing to time out.
# It nags at a decreasing rate until a human actually answers, rather than
# counting down to killing the work. Sync requests keep the old
# remind-twice-then-escalate deadline, because their caller *is* blocked.
ASYNC_REMINDER_BACKOFF = (1, 4, 96)

# Answers are kept after resolution so an agent that polls, crashes, and
# polls again still finds them. Approvals are a handful a day, so this cap
# exists only to stop an unbounded dict in a process that runs for months.
MAX_RESOLVED_RETAINED = 200

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
    # "sync"  — a caller is blocked on request(); it must be released, so the
    #           reminder clock still escalates and cancels the task.
    # "async" — submitted via submit(); nobody is waiting on a socket, so the
    #           request survives daemon restarts and is never auto-killed.
    # Defaults to "sync" so anything written by an older daemon, or by a
    # caller that hasn't been updated, keeps exactly its previous behaviour.
    mode: str = "sync"
    # HEAD at the moment the question was asked. An approval is only good for
    # the code it was granted against — see poll().
    commit_sha: Optional[str] = None

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
            "mode": self.mode,
            "commit_sha": self.commit_sha,
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
        # Answers to async requests, waiting to be collected by poll().
        self._resolved: dict[str, dict[str, Any]] = {}
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

    async def _ask(
        self,
        action: str,
        reason: str,
        ticket_key: str,
        mode: str,
        commit_sha: Optional[str] = None,
        fut: "Optional[asyncio.Future[dict[str, Any]]]" = None,
    ) -> str:
        """Post the question and start its clock. Shared by request/submit."""
        req_id = f"req_{os.urandom(4).hex()}"
        req = ApprovalRequest(
            req_id=req_id,
            action=action,
            reason=reason,
            ticket_key=ticket_key,
            originating_generation=self.agent_runner.task_generation,
            mode=mode,
            commit_sha=commit_sha,
        )
        self._requests[req_id] = req
        # Registered before the question is posted, not after: _post_question
        # awaits, and the moment it does the reaction that answers it can
        # already be dispatched on this same loop.
        if fut is not None:
            self._futures[req_id] = fut

        await self._post_question(req, reminder=False)
        await self._snapshot()
        watcher = self._watch_timeout if mode == "sync" else self._watch_reminders
        self._timers[req_id] = asyncio.create_task(watcher(req_id))
        return req_id

    async def submit(
        self,
        action: str,
        reason: str,
        ticket_key: str,
        commit_sha: Optional[str] = None,
    ) -> str:
        """Ask the Boss and return immediately with a handle.

        This is the asynchronous half of DT-232 and the one an unattended
        agent should use: the question goes to Discord, the calling task
        parks itself, and the agent moves on to whatever else is unblocked.
        Collect the answer later with poll().

        Pass `commit_sha` to bind the approval to the code it was granted
        against; poll() then refuses to report it as approved from a
        different HEAD.
        """
        return await self._ask(action, reason, ticket_key, "async", commit_sha)

    def poll(
        self, req_ids: list[str], commit_sha: Optional[str] = None
    ) -> dict[str, dict[str, Any]]:
        """Look up submitted requests without blocking on any of them.

        Answers are not consumed by reading, so polling twice is safe.

        Statuses: `pending` (no answer yet), `approved`, `rejected`,
        `stale` (approved, but against a different commit — ask again), and
        `unknown` (never seen, or lost with a daemon that died before it
        could persist).
        """
        out: dict[str, dict[str, Any]] = {}
        for req_id in req_ids:
            answer = self._resolved.get(req_id)
            if answer is not None:
                payload = dict(answer)
                granted_for = payload.get("commit_sha")
                if (
                    payload["status"] == "approved"
                    and granted_for
                    and commit_sha
                    and granted_for != commit_sha
                ):
                    payload["status"] = "stale"
                    payload["detail"] = (
                        f"Approved against commit {granted_for}, but you are "
                        f"now on {commit_sha}. The code changed after the Boss "
                        "said yes — ask again rather than reusing this answer."
                    )
                out[req_id] = payload
                continue

            req = self._requests.get(req_id)
            if req is not None:
                out[req_id] = {
                    "req_id": req_id,
                    "status": req.status,
                    "action": req.action,
                    "ticket_key": req.ticket_key,
                    "commit_sha": req.commit_sha,
                }
                continue

            out[req_id] = {
                "req_id": req_id,
                "status": "unknown",
                "detail": (
                    "No such approval request. It was never submitted, or it "
                    "was lost with a daemon that stopped before persisting it "
                    "— re-submit rather than assuming either answer."
                ),
            }
        return out

    async def request(
        self, action: str, reason: str, ticket_key: str
    ) -> dict[str, Any]:
        """Ask and block until answered. Retained for the pre-3.0.0 MCP tool
        contract; new callers should use submit() + poll() instead."""
        loop = asyncio.get_running_loop()
        fut: "asyncio.Future[dict[str, Any]]" = loop.create_future()
        req_id = await self._ask(action, reason, ticket_key, "sync", fut=fut)

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

    async def _watch_reminders(self, req_id: str) -> None:
        """Nag, forever, at a decreasing rate — never escalate, never kill.

        The sync path (_watch_timeout) has to end in *something* because a
        caller is blocked on the socket. Nothing is blocked here, so the only
        honest behaviour when a human hasn't answered is to ask again. A
        question the Boss hasn't got to yet is not a failure.
        """
        attempt = 0
        while True:
            step = ASYNC_REMINDER_BACKOFF[min(attempt, len(ASYNC_REMINDER_BACKOFF) - 1)]
            try:
                await asyncio.sleep(self.timeout_seconds * step)
            except asyncio.CancelledError:
                return

            req = self._requests.get(req_id)
            if not req or req.status != "pending":
                return

            attempt += 1
            req.attempt = attempt + 1
            await self._post_question(req, reminder=True)
            await self._snapshot()

    def _record_answer(self, req: ApprovalRequest) -> None:
        """Park a resolved async answer where poll() will find it."""
        self._resolved[req.req_id] = {
            "req_id": req.req_id,
            "status": req.status,
            "action": req.action,
            "reason": req.reason,
            "ticket_key": req.ticket_key,
            "commit_sha": req.commit_sha,
            "resolved_at": time.time(),
        }
        while len(self._resolved) > MAX_RESOLVED_RETAINED:
            self._resolved.pop(next(iter(self._resolved)))

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
        # An async request has no future to deliver the answer to, so the
        # answer has to be kept somewhere until its agent comes back to poll.
        if req.mode == "async":
            self._record_answer(req)
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

    def list_pending(self) -> list[dict[str, Any]]:
        """Requests still awaiting a human, newest first — for the /pending
        Discord command. Only pending/escalated: approved/rejected requests
        are already popped from self._requests by resolve()."""
        return [
            {
                "ticket_key": req.ticket_key,
                "action": req.action,
                "status": req.status,
                "created_at": req.created_at,
            }
            for req in sorted(
                self._requests.values(), key=lambda r: r.created_at, reverse=True
            )
            if req.status in ("pending", "escalated")
        ]

    def clear_escalated(self, ticket_key: str) -> Optional[ApprovalRequest]:
        """Clear the escalated request for `ticket_key`, if any, so
        is_pending_or_escalated() stops blocking commits for it. Used by the
        /approve Discord command -- the original agent process that made
        this request is long gone (escalation already killed it), so there
        is nothing to resume; the caller re-dispatches a fresh run instead.
        Returns the cleared request for its action/reason context, or None
        if there's no escalated request for that ticket."""
        for req_id, req in list(self._requests.items()):
            if req.ticket_key == ticket_key and req.status == "escalated":
                del self._requests[req_id]
                return req
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
            data: dict[str, Any] = {
                req_id: r.to_dict()
                for req_id, r in self._requests.items()
                if r.status == "pending"
            }
            # Uncollected async answers are persisted too. The agent that
            # asked may not poll until the next session, and a daemon restart
            # in between must not turn a real "yes" back into a question.
            # Sync answers are never here — their caller already got them
            # through the future before resolve() returned.
            data.update(self._resolved)
            # Offloaded to a thread: this runs on every state transition, and
            # blocking file I/O directly on the event loop would also stall
            # Discord gateway heartbeat/dispatch, which shares this same loop.
            await asyncio.to_thread(self._write_snapshot_file, data)

    def _write_snapshot_file(self, data: dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(snapshot_file()), exist_ok=True)
            with open(snapshot_file(), "w", encoding="utf-8") as f:
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
        if not os.path.exists(snapshot_file()):
            return
        try:
            with open(snapshot_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not data:
            return

        for req_id, payload in data.items():
            # A snapshot written by an older release is not a reason to lose
            # every readable entry alongside the unreadable one (principle 4).
            # The retired Silent Wait Protocol wrote a single request object
            # here rather than a map of them, so `payload` came back as a
            # string and the AttributeError took the whole recovery with it —
            # on every daemon start, in silence, for months.
            if not isinstance(payload, dict):
                print(
                    f"[ApprovalManager] Skipping unreadable snapshot entry "
                    f"{req_id!r} ({type(payload).__name__}, expected an object).",
                    flush=True,
                )
                continue

            status = payload.get("status")

            # An answer nobody collected yet. Hand it straight back to
            # _resolved so the next poll() finds it.
            if status in ("approved", "rejected"):
                self._resolved[req_id] = payload
                continue

            if status not in ("pending", "escalated"):
                continue

            req = ApprovalRequest(
                req_id=req_id,
                action=payload.get(
                    "action", "(unknown — recovered after daemon restart)"
                ),
                reason=payload.get("reason", ""),
                ticket_key=payload.get("ticket_key", "UNKNOWN"),
                attempt=payload.get("attempt", 2),
                created_at=payload.get("created_at", time.time()),
                mode=payload.get("mode", "sync"),
                commit_sha=payload.get("commit_sha"),
            )
            self._requests[req_id] = req

            # An async request is not orphaned by a restart. Nobody was
            # waiting on the socket, so the question is still live and its
            # agent will come back to poll — escalating it here would raise
            # a false alarm and, worse, teach the agent that a restart is an
            # answer. Just put it back and resume nagging.
            if req.mode == "async":
                print(
                    f"[ApprovalManager] Restored async approval {req_id} "
                    f"({req.ticket_key}) — still awaiting an answer.",
                    flush=True,
                )
                req.status = "pending"
                self._timers[req_id] = asyncio.create_task(
                    self._watch_reminders(req_id)
                )
                continue

            print(
                f"[ApprovalManager] Recovering orphaned approval {req_id} from a "
                "previous daemon run — escalating.",
                flush=True,
            )
            await self._escalate(req_id)
