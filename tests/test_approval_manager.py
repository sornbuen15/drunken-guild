# mypy: ignore-errors
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from service.approval_manager import ApprovalManager, ApprovalRequest


async def _wait_for_file(path, timeout: float = 2.0) -> None:
    # _snapshot() hops through asyncio.to_thread, so a fixed sleep after
    # triggering it is inherently racy under load — poll instead.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return
        await asyncio.sleep(0.005)
    raise TimeoutError(f"{path} was never written within {timeout}s")


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> MagicMock:
        msg = MagicMock()
        msg.id = len(self.sent) + 1
        msg.add_reaction = AsyncMock()
        self.sent.append(text)
        return msg


class FakeClient:
    def __init__(self, channel: FakeChannel) -> None:
        self._channel = channel

    def get_channel(self, channel_id: int) -> FakeChannel:
        return self._channel

    async def fetch_channel(self, channel_id: int) -> FakeChannel:
        return self._channel


@pytest.fixture()
def manager(monkeypatch, tmp_path):
    outbox = tmp_path / "approvals.json"
    # Through the environment rather than by patching an attribute: that is the
    # override a real deployment uses, so the test exercises the mechanism
    # instead of a stand-in for it.
    monkeypatch.setenv("DRUNKEN_APPROVAL_SNAPSHOT", str(outbox))

    channel = FakeChannel()
    client = FakeClient(channel)
    agent_runner = MagicMock()
    agent_runner.cancel_current_task = AsyncMock()
    jira_client = MagicMock()
    jira_client.add_comment = AsyncMock()
    jira_client.base_url = "https://fake.atlassian.net"

    mgr = ApprovalManager(
        client=client,
        channel_id=123,
        agent_runner=agent_runner,
        jira_client=jira_client,
        timeout_seconds=0.05,
    )
    return mgr, channel, agent_runner, jira_client, outbox


@pytest.mark.asyncio
async def test_request_resolves_on_reaction(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    task = asyncio.create_task(mgr.request("do thing", "because", "DG-1"))
    await asyncio.sleep(0.01)  # let the question post

    assert len(channel.sent) == 1
    assert "do thing" in channel.sent[0]

    req_id = next(iter(mgr._requests))
    msg_id = mgr._requests[req_id].discord_message_id
    resolved = await mgr.resolve(msg_id, approved=True)
    assert resolved is True

    result = await task
    assert result == {"status": "approved"}
    agent_runner.cancel_current_task.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_unknown_message_returns_false(manager) -> None:
    mgr, *_ = manager
    assert await mgr.resolve(99999, approved=True) is False


@pytest.mark.asyncio
async def test_resolve_cancels_timer_no_escalation(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    task = asyncio.create_task(mgr.request("do thing", "because", "DG-1"))
    await asyncio.sleep(0.01)
    req_id = next(iter(mgr._requests))
    msg_id = mgr._requests[req_id].discord_message_id

    await mgr.resolve(msg_id, approved=False)
    await task

    # Wait past where a reminder/escalation would have fired if the timer
    # hadn't been cancelled on resolve.
    await asyncio.sleep(0.15)
    agent_runner.cancel_current_task.assert_not_called()
    jira_client.add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_no_response_reminds_then_escalates(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    result = await mgr.request("run destroy", "cleanup", "DG-42")

    assert result == {"status": "escalated"}
    # Initial question + one reminder = 2 posts, plus the escalation summary = 3.
    assert len(channel.sent) == 3
    assert "Reminder" in channel.sent[1]
    assert "paused" in channel.sent[2].lower()

    agent_runner.cancel_current_task.assert_called_once()
    jira_client.add_comment.assert_called_once()
    comment_args = jira_client.add_comment.call_args[0]
    assert comment_args[0] == "DG-42"
    assert "Awaiting Boss Approval" in comment_args[1]

    req_id = next(iter(mgr._requests))
    assert mgr._requests[req_id].status == "escalated"


@pytest.mark.asyncio
async def test_escalate_does_not_cancel_a_different_generation_task(manager) -> None:
    # Regression test: escalation must not blindly kill whatever task
    # AgentRunner happens to be running now — only the one that was running
    # when THIS request was made. If a different task has started in the
    # meantime (the original task already finished on its own), killing it
    # would terminate unrelated, legitimate work.
    mgr, channel, agent_runner, jira_client, outbox = manager
    agent_runner.task_generation = 1  # generation active when request() is made

    task = asyncio.create_task(mgr.request("run destroy", "cleanup", "DG-42"))
    await asyncio.sleep(0.01)

    req_id = next(iter(mgr._requests))
    assert mgr._requests[req_id].originating_generation == 1

    # A new, unrelated task starts before this approval times out.
    agent_runner.task_generation = 2

    result = await task
    assert result == {"status": "escalated"}
    agent_runner.cancel_current_task.assert_not_called()


@pytest.mark.asyncio
async def test_escalated_requests_are_not_persisted_to_snapshot(manager) -> None:
    # Regression test: an earlier version kept "escalated" entries in the
    # outbox snapshot, which made recover_from_snapshot() re-escalate the
    # same request (duplicate Jira comment + Discord notification) on every
    # subsequent daemon restart. Escalation is terminal and already fully
    # actioned, so nothing should be left behind to "recover".
    mgr, channel, agent_runner, jira_client, outbox = manager

    await mgr.request("run destroy", "cleanup", "DG-42")

    with open(outbox, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == {}


@pytest.mark.asyncio
async def test_is_pending_or_escalated(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    assert mgr.is_pending_or_escalated("DG-1") is None

    task = asyncio.create_task(mgr.request("do thing", "because", "DG-1"))
    await asyncio.sleep(0.01)
    assert mgr.is_pending_or_escalated("DG-1") == "pending"

    req_id = next(iter(mgr._requests))
    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=True)
    await task

    assert mgr.is_pending_or_escalated("DG-1") is None


@pytest.mark.asyncio
async def test_clear_escalated_returns_and_removes_request(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    result = await mgr.request("run destroy", "cleanup", "DG-42")
    assert result == {"status": "escalated"}
    assert mgr.is_pending_or_escalated("DG-42") == "escalated"

    cleared = mgr.clear_escalated("DG-42")
    assert cleared is not None
    assert cleared.ticket_key == "DG-42"
    assert cleared.action == "run destroy"
    assert cleared.reason == "cleanup"

    # Clearing removes it entirely -- no longer pending/escalated/blocking.
    assert mgr.is_pending_or_escalated("DG-42") is None
    assert mgr.list_pending() == []


@pytest.mark.asyncio
async def test_clear_escalated_unknown_ticket_returns_none(manager) -> None:
    mgr, *_ = manager
    assert mgr.clear_escalated("DG-999") is None


@pytest.mark.asyncio
async def test_clear_escalated_ignores_still_pending_request(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    task = asyncio.create_task(mgr.request("do thing", "because", "DG-1"))
    await asyncio.sleep(0.01)

    # Still pending (not escalated yet) -- clear_escalated must not touch it.
    assert mgr.clear_escalated("DG-1") is None
    assert mgr.is_pending_or_escalated("DG-1") == "pending"

    req_id = next(iter(mgr._requests))
    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=True)
    await task


@pytest.mark.asyncio
async def test_list_pending(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    assert mgr.list_pending() == []

    task1 = asyncio.create_task(mgr.request("do thing 1", "because 1", "DG-1"))
    await asyncio.sleep(0.01)
    task2 = asyncio.create_task(mgr.request("do thing 2", "because 2", "DG-2"))
    await asyncio.sleep(0.01)

    pending = mgr.list_pending()
    assert len(pending) == 2
    # Newest first.
    assert pending[0]["ticket_key"] == "DG-2"
    assert pending[0]["action"] == "do thing 2"
    assert pending[0]["status"] == "pending"
    assert pending[1]["ticket_key"] == "DG-1"

    req_id_1 = next(rid for rid, r in mgr._requests.items() if r.ticket_key == "DG-1")
    msg_id_1 = mgr._requests[req_id_1].discord_message_id
    await mgr.resolve(msg_id_1, approved=True)
    await task1

    # Resolved requests are popped entirely -- only DG-2 remains.
    pending = mgr.list_pending()
    assert len(pending) == 1
    assert pending[0]["ticket_key"] == "DG-2"

    req_id_2 = next(iter(mgr._requests))
    msg_id_2 = mgr._requests[req_id_2].discord_message_id
    await mgr.resolve(msg_id_2, approved=True)
    await task2


@pytest.mark.asyncio
async def test_list_pending_includes_escalated(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    result = await mgr.request("do thing", "because", "DG-1")
    assert result == {"status": "escalated"}

    pending = mgr.list_pending()
    assert len(pending) == 1
    assert pending[0]["status"] == "escalated"
    assert pending[0]["ticket_key"] == "DG-1"


@pytest.mark.asyncio
async def test_concurrent_snapshots_do_not_interleave(manager) -> None:
    # Regression test: _snapshot() offloads its write via asyncio.to_thread,
    # which gives no FIFO guarantee across threads on its own — two snapshot
    # calls close together could otherwise have the *older* call's write
    # land on disk after the *newer* one's, clobbering it with stale data.
    # The internal lock must fully serialize concurrent calls: the second
    # call's write must not start until the first one's has finished.
    mgr, channel, agent_runner, jira_client, outbox = manager

    order: list[str] = []

    async def fake_write(func, data) -> None:
        order.append("start")
        await asyncio.sleep(0.02)  # long enough that a race would interleave
        order.append("end")

    with patch("service.approval_manager.asyncio.to_thread", side_effect=fake_write):
        await asyncio.gather(mgr._snapshot(), mgr._snapshot())

    # If the lock didn't serialize these, we'd see start, start, end, end.
    assert order == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_snapshot_written_and_cleared_on_resolve(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    task = asyncio.create_task(mgr.request("do thing", "because", "DG-7"))
    await _wait_for_file(outbox)

    with open(outbox, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1
    req_id = next(iter(data))
    assert data[req_id]["ticket_key"] == "DG-7"
    assert data[req_id]["status"] == "pending"

    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=True)
    await task

    with open(outbox, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == {}  # resolved requests are dropped from the snapshot


@pytest.mark.asyncio
async def test_recover_from_snapshot_escalates_orphans(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    orphan = ApprovalRequest(
        req_id="req_orphan",
        action="orphaned action",
        reason="daemon restarted",
        ticket_key="DG-99",
    )
    with open(outbox, "w", encoding="utf-8") as f:
        json.dump({"req_orphan": orphan.to_dict()}, f)

    await mgr.recover_from_snapshot()

    # Recovered orphans have no known originating_generation (it isn't
    # persisted, and can't be — the process that made the request is gone).
    # Escalation must not guess and kill whatever unrelated task happens to
    # be running now.
    agent_runner.cancel_current_task.assert_not_called()
    jira_client.add_comment.assert_called_once()
    assert jira_client.add_comment.call_args[0][0] == "DG-99"
    assert mgr._requests["req_orphan"].status == "escalated"


@pytest.mark.asyncio
async def test_recover_survives_a_snapshot_from_the_retired_protocol(manager) -> None:
    """The exact file found on the Boss's machine, failing at every start.

    `.agents/discord_outbox.json` was left behind by the retired Silent Wait
    Protocol, whose format was one request object rather than a map of them.
    Iterating it handed `.items()` a plain string, and the AttributeError took
    the whole recovery down — including entries that were perfectly readable.
    """
    mgr, channel, agent_runner, jira_client, outbox = manager

    with open(outbox, "w", encoding="utf-8") as f:
        json.dump({"question": "ผมจะย้ายตั๋ว...", "ticket_key": "DG-182"}, f)

    await mgr.recover_from_snapshot()

    assert mgr._requests == {}
    jira_client.add_comment.assert_not_called()


@pytest.mark.asyncio
async def test_one_unreadable_entry_does_not_discard_the_others(manager) -> None:
    """Principle 4, applied here: a corrupt entry reads as absent rather than
    raising. Losing every other pending approval to one bad record is a far
    worse outcome than skipping the bad record."""
    mgr, channel, agent_runner, jira_client, outbox = manager

    good = ApprovalRequest(
        req_id="req_good", action="a", reason="b", ticket_key="DG-77"
    )
    with open(outbox, "w", encoding="utf-8") as f:
        json.dump({"junk": "not an object", "req_good": good.to_dict()}, f)

    await mgr.recover_from_snapshot()

    assert "req_good" in mgr._requests
    assert jira_client.add_comment.call_args[0][0] == "DG-77"


@pytest.mark.asyncio
async def test_recover_from_snapshot_noop_when_empty(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    await mgr.recover_from_snapshot()  # no file yet

    agent_runner.cancel_current_task.assert_not_called()


# ---------------------------------------------------------------------------
# DG-232 — asynchronous approval: submit, keep working, poll for the answer.
#
# The blocking request() is kept (and still tested above) so the existing MCP
# tool contract survives until 3.0.0, but it is no longer how an unattended
# agent should ask: sitting on `await fut` means one waiting task freezes
# every other task behind it, and the deadline that unblocks it does so by
# killing the work.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_returns_without_waiting_for_a_human(manager) -> None:
    """The whole point of DG-232: asking must not block.

    request() only returns once someone reacts on Discord. submit() has to
    come straight back with a handle, leaving the agent free to pick up the
    next unblocked task.
    """
    mgr, channel, agent_runner, jira_client, outbox = manager

    req_id = await asyncio.wait_for(
        mgr.submit("delete staging db", "before the migration test", "DG-1"),
        timeout=1.0,  # nobody reacts; this must still return
    )

    assert isinstance(req_id, str) and req_id
    assert len(channel.sent) == 1
    assert "delete staging db" in channel.sent[0]
    assert mgr._requests[req_id].status == "pending"


@pytest.mark.asyncio
async def test_poll_reports_pending_then_the_resolution(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    req_id = await mgr.submit("ship it", "phase is green", "DG-2")
    assert mgr.poll([req_id])[req_id]["status"] == "pending"

    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=True)

    answer = mgr.poll([req_id])[req_id]
    assert answer["status"] == "approved"
    assert answer["action"] == "ship it"

    # Polling twice must not consume the answer -- an agent that polls,
    # crashes, and polls again has to still find it.
    assert mgr.poll([req_id])[req_id]["status"] == "approved"


@pytest.mark.asyncio
async def test_rejection_carries_the_reason_back(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    req_id = await mgr.submit("force push main", "rebase went sideways", "DG-3")
    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=False)

    answer = mgr.poll([req_id])[req_id]
    assert answer["status"] == "rejected"
    assert answer["action"] == "force push main"


@pytest.mark.asyncio
async def test_approval_does_not_carry_over_to_a_different_commit(manager) -> None:
    """A yes from this morning must not silently authorise tonight's code.

    The approval is bound to the commit it was granted against; polling from
    a different HEAD reports `stale` rather than `approved`, forcing a fresh
    request.
    """
    mgr, channel, agent_runner, jira_client, outbox = manager

    req_id = await mgr.submit(
        "rm -rf build/", "clean rebuild", "DG-4", commit_sha="aaa111"
    )
    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=True)

    assert mgr.poll([req_id], commit_sha="aaa111")[req_id]["status"] == "approved"

    stale = mgr.poll([req_id], commit_sha="bbb222")[req_id]
    assert stale["status"] == "stale"
    assert "aaa111" in stale["detail"]


@pytest.mark.asyncio
async def test_async_request_is_reminded_but_never_killed(manager, monkeypatch) -> None:
    """No countdown-to-death. Reminders keep nagging; the task stays alive.

    request() escalates after 2 unanswered reminders and cancels the running
    task. An async request has no caller sitting on it, so there is nothing
    to time out -- it stays pending until a human actually answers.
    """
    mgr, channel, agent_runner, jira_client, outbox = manager
    monkeypatch.setattr("service.approval_manager.ASYNC_REMINDER_BACKOFF", (1, 1, 1))

    req_id = await mgr.submit("needs a human", "nobody is home", "DG-5")

    # Three reminder windows go by with no reaction at all.
    await asyncio.sleep(0.05 * 3 + 0.15)

    assert len(channel.sent) > 1, "reminders should still be firing"
    assert mgr._requests[req_id].status == "pending"
    agent_runner.cancel_current_task.assert_not_called()
    jira_client.add_comment.assert_not_called()
    assert mgr.poll([req_id])[req_id]["status"] == "pending"


@pytest.mark.asyncio
async def test_recover_restores_async_pending_instead_of_escalating(manager) -> None:
    """A restart is not an answer.

    A sync request whose caller died with the old daemon is genuinely
    orphaned and is escalated (covered above). An async one is not: its
    caller was never waiting on the socket and will come back to poll, so
    throwing it away -- or escalating it -- would lose a live question.
    """
    mgr, channel, agent_runner, jira_client, outbox = manager

    pending = ApprovalRequest(
        req_id="req_async",
        action="async action",
        reason="daemon restarted",
        ticket_key="DG-6",
        mode="async",
    )
    with open(outbox, "w", encoding="utf-8") as f:
        json.dump({"req_async": pending.to_dict()}, f)

    await mgr.recover_from_snapshot()

    jira_client.add_comment.assert_not_called()
    agent_runner.cancel_current_task.assert_not_called()
    assert mgr._requests["req_async"].status == "pending"
    assert mgr.poll(["req_async"])["req_async"]["status"] == "pending"


@pytest.mark.asyncio
async def test_recover_restores_an_answer_nobody_collected_yet(manager) -> None:
    mgr, channel, agent_runner, jira_client, outbox = manager

    req_id = await mgr.submit("do the thing", "why not", "DG-8")
    msg_id = mgr._requests[req_id].discord_message_id
    await mgr.resolve(msg_id, approved=True)
    await _wait_for_file(outbox)

    # A fresh manager, as if the daemon had restarted before anyone polled.
    fresh = ApprovalManager(
        client=mgr.client,
        channel_id=mgr.channel_id,
        agent_runner=mgr.agent_runner,
        jira_client=mgr.jira_client,
        timeout_seconds=0.05,
    )
    await fresh.recover_from_snapshot()

    assert fresh.poll([req_id])[req_id]["status"] == "approved"
