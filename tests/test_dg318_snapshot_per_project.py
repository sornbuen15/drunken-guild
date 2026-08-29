"""DG-318: the approval snapshot is one file per project, not one per machine.

DG-313 split the socket so each project's daemon answers in its own room. It
did not split the state behind it. ``approval_snapshot_path()`` took no project
while ``daemon_socket_path(project)`` -- three functions above it in the same
module -- did, so every daemon rewrote one ``approvals.json`` from its own
memory.

Two consequences, both seen on 2026-08-29 with three daemons running: the last
writer erased the other projects' approvals (three were granted, one survived on
disk), and a restart then adopted a neighbour's request -- re-posting it into
the wrong room, which is the DG-313 symptom one layer down.

The path cases mirror ``test_dg313_socket_per_project.py`` deliberately: the two
resolution rules must not diverge, because a snapshot resolved by one rule and a
socket by another is a new way for the same two things to disagree.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import paths  # noqa: E402
from service.approval_manager import ApprovalManager  # noqa: E402


def _name(project: str | None = None) -> str:
    return os.path.basename(str(paths.approval_snapshot_path(project)))


# --------------------------------------------------------------------------
# The name
# --------------------------------------------------------------------------


def test_project_gets_its_own_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.chdir(tmp_path)  # an explicit argument must not need a cwd
    assert _name("alpha") == "approvals-alpha.json"
    assert _name("beta") == "approvals-beta.json"
    assert _name("drunken-guild") == "approvals-drunken-guild.json"


def test_two_projects_never_share_a_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.chdir(tmp_path)
    names = {_name(p) for p in ("alpha", "beta", "drunken-guild")}
    assert len(names) == 3, "distinct projects collided on one snapshot file"


def test_falls_back_to_env_so_the_daemon_finds_its_own_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The daemon passes no argument; DRUNKEN_PROJECT is what must reach here.

    Same pairing DG-313 relies on for the socket. ``snapshot_file()`` deliberately
    calls with no argument so the file, the socket and the room all name one
    project from one source.
    """
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.setenv("DRUNKEN_PROJECT", "alpha")
    assert _name() == "approvals-alpha.json"
    assert _name() == _name("alpha")


def test_the_snapshot_resolves_exactly_like_the_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One rule, not two.

    A machine where the socket resolves to alpha and the snapshot to beta would
    answer in the right room and persist into the wrong file -- harder to see
    than the bug this fixes, because both halves look correct alone.
    """
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    for project in ("alpha", "beta", "drunken-guild", None):
        socket = os.path.basename(str(paths.daemon_socket_path(project)))
        snapshot = _name(project)
        assert socket.removeprefix("daemon").removesuffix(".sock") == (
            snapshot.removeprefix("approvals").removesuffix(".json")
        ), f"socket {socket} and snapshot {snapshot} disagree for {project!r}"


def test_nothing_to_resolve_keeps_the_old_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A single-project machine is unchanged, exactly as with the socket."""
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert _name() == "approvals.json"


def test_explicit_snapshot_override_still_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DRUNKEN_APPROVAL_SNAPSHOT names a path, so it cannot be per-project."""
    target = tmp_path / "custom.json"
    monkeypatch.setenv("DRUNKEN_PROJECT", "alpha")
    monkeypatch.setenv("DRUNKEN_APPROVAL_SNAPSHOT", str(target))
    assert str(paths.approval_snapshot_path()) == str(target)
    assert str(paths.approval_snapshot_path("beta")) == str(target)


def test_project_id_cannot_escape_the_state_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A registry key is operator input and reaches a filename here."""
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.chdir(tmp_path)
    for hostile in ("../../etc/x", "a/b", "..", "/abs"):
        resolved = paths.approval_snapshot_path(hostile)
        assert os.path.dirname(str(resolved)) == str(paths.home().path)
        assert os.path.basename(str(resolved)).startswith("approvals-")


# --------------------------------------------------------------------------
# The behaviour the name exists for
#
# The cases above would all pass against a stub that renamed the file and
# changed nothing else. These two are the defect itself.
# --------------------------------------------------------------------------


class _FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> MagicMock:
        msg = MagicMock()
        msg.id = len(self.sent) + 1
        msg.add_reaction = AsyncMock()
        self.sent.append(text)
        return msg


class _FakeClient:
    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel

    def get_channel(self, channel_id: int) -> _FakeChannel:
        return self._channel

    async def fetch_channel(self, channel_id: int) -> _FakeChannel:
        return self._channel


def _daemon(channel_id: int) -> ApprovalManager:
    """One project's daemon, as far as ApprovalManager is concerned."""
    jira_client = MagicMock()
    jira_client.add_comment = AsyncMock()
    jira_client.base_url = "https://fake.atlassian.net"
    agent_runner = MagicMock()
    agent_runner.cancel_current_task = AsyncMock()
    return ApprovalManager(
        client=_FakeClient(_FakeChannel()),
        channel_id=channel_id,
        agent_runner=agent_runner,
        jira_client=jira_client,
        timeout_seconds=3600,  # long: nothing here should reach a reminder
    )


@pytest.fixture()  # type: ignore[misc]
def two_projects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A state directory shared by two projects, which is the real arrangement.

    DRUNKEN_APPROVAL_SNAPSHOT is deliberately *not* set: naming the file
    outright is the one thing that would hide the bug, since it is per-machine
    by definition.
    """
    monkeypatch.setenv("DRUNKEN_HOME", str(tmp_path))
    monkeypatch.delenv("DRUNKEN_APPROVAL_SNAPSHOT", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.asyncio  # type: ignore[misc]
async def test_one_project_never_clobbers_anothers_approvals(
    two_projects: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two daemons, one submission each, and neither loses the other's.

    Each daemon is its own process with its own DRUNKEN_PROJECT, so the variable
    is set around each write rather than once for the test.
    """
    monkeypatch.setenv("DRUNKEN_PROJECT", "alpha")
    alpha = _daemon(channel_id=111)
    alpha_id = await alpha.submit("alpha action", "alpha reason", "AL-1")

    monkeypatch.setenv("DRUNKEN_PROJECT", "beta")
    beta = _daemon(channel_id=222)
    beta_id = await beta.submit("beta action", "beta reason", "BE-1")

    alpha_file = two_projects / "approvals-alpha.json"
    beta_file = two_projects / "approvals-beta.json"
    assert alpha_file.exists(), "alpha's daemon wrote no snapshot of its own"
    assert beta_file.exists(), "beta's daemon wrote no snapshot of its own"

    alpha_data = json.loads(alpha_file.read_text())
    beta_data = json.loads(beta_file.read_text())

    assert alpha_id in alpha_data, "the second daemon's write erased the first's"
    assert beta_id in beta_data
    assert beta_id not in alpha_data, "beta's request leaked into alpha's snapshot"
    assert alpha_id not in beta_data, "alpha's request leaked into beta's snapshot"


@pytest.mark.asyncio  # type: ignore[misc]
async def test_a_restart_never_adopts_another_projects_request(
    two_projects: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wrong-room posting, reached through the snapshot instead of the socket.

    A recovered request is re-posted and nagged in the recovering daemon's own
    channel, so adopting a neighbour's is the exact failure DG-313 fixed.
    """
    monkeypatch.setenv("DRUNKEN_PROJECT", "alpha")
    alpha_id = await _daemon(channel_id=111).submit("alpha action", "why", "AL-1")

    monkeypatch.setenv("DRUNKEN_PROJECT", "beta")
    beta_id = await _daemon(channel_id=222).submit("beta action", "why", "BE-1")

    # alpha's daemon restarts.
    monkeypatch.setenv("DRUNKEN_PROJECT", "alpha")
    restarted = _daemon(channel_id=111)
    await restarted.recover_from_snapshot()

    recovered = set(restarted._requests) | set(restarted._resolved)
    assert alpha_id in recovered, "alpha lost its own pending approval on restart"
    assert beta_id not in recovered, (
        "alpha's daemon adopted beta's request and would re-post it into "
        "alpha's Discord room"
    )
