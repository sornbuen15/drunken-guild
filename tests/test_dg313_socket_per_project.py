"""DG-313: the approval socket is one per project, not one per machine.

Before this, every project's MCP server dialled a single ``daemon.sock``, so the
one daemon behind it answered with whichever channel it had been pinned to.
twa's and isac's approvals posted into drunken-guild's room and reported
success. These assert the split at the level that caused it -- the socket name --
rather than by posting to a real Discord room.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import paths  # noqa: E402


def _name(project: str | None = None) -> str:
    return os.path.basename(str(paths.daemon_socket_path(project)))


def test_project_gets_its_own_socket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    monkeypatch.chdir(tmp_path)  # an explicit argument must not need a cwd
    assert _name("twa") == "daemon-twa.sock"
    assert _name("isac") == "daemon-isac.sock"
    assert _name("drunken-guild") == "daemon-drunken-guild.sock"


def test_two_projects_never_share_a_socket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    monkeypatch.chdir(tmp_path)
    names = {_name(p) for p in ("twa", "isac", "drunken-guild")}
    assert len(names) == 3, "distinct projects collided on one socket"


def test_falls_back_to_env_so_daemon_and_client_meet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The daemon passes no argument; it is DRUNKEN_PROJECT that must reach it.

    This is the pairing that makes the fix work without a second knob: the MCP
    server dials by --project, the daemon binds by DRUNKEN_PROJECT, and the two
    resolve to the same name.
    """
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    monkeypatch.setenv("DRUNKEN_PROJECT", "twa")
    assert _name() == "daemon-twa.sock"
    assert _name() == _name("twa")


def test_nothing_to_resolve_keeps_the_old_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no argument, no env and no matching checkout, the name is unchanged.

    Run from outside any registered project on purpose: inside one, resolving
    from cwd is the point of the change, and this asserts the floor beneath it.
    """
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    monkeypatch.chdir(tmp_path)
    assert _name() == "daemon.sock"


def test_explicit_socket_override_still_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DRUNKEN_DAEMON_SOCKET names a path, so it cannot be per-project."""
    target = tmp_path / "custom.sock"
    monkeypatch.setenv("DRUNKEN_PROJECT", "twa")
    monkeypatch.setenv("DRUNKEN_DAEMON_SOCKET", str(target))
    assert str(paths.daemon_socket_path()) == str(target)
    assert str(paths.daemon_socket_path("isac")) == str(target)


def test_project_id_cannot_escape_the_state_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A registry key is operator input and reaches a filename here."""
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    monkeypatch.chdir(tmp_path)
    for hostile in ("../../etc/x", "a/b", "..", "/abs"):
        resolved = paths.daemon_socket_path(hostile)
        assert os.path.dirname(str(resolved)) == str(paths.home().path)
        assert os.path.basename(str(resolved)).startswith("daemon-")


def test_launchagent_label_is_per_project() -> None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import setup_daemon_service as svc

    assert svc._label("twa") != svc._label("isac")
    assert svc._label("twa").endswith(".twa")
    assert svc._label("../x") == "com.drunkenteam.daemon.x"


def test_cwd_resolves_the_project_so_hooks_keep_working(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The processes that dial the daemon do not have DRUNKEN_PROJECT set.

    The pre-commit approval check, the away-mode PreToolUse hook and
    drunken-doctor all run from a plain shell. Splitting the socket without
    this would leave them on ``daemon.sock`` while the daemon moved to
    ``daemon-<project>.sock`` -- the approval gate would go quiet, a regression
    caused by the fix itself.
    """
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)

    root = tmp_path / "checkout-named-something-else"
    (root / "sub" / "deep").mkdir(parents=True)
    registry = {"projects": {"acme": {"path": str(root)}}}

    import json

    reg_file = tmp_path / "projects.json"
    reg_file.write_text(json.dumps(registry))
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(reg_file))

    monkeypatch.chdir(root / "sub" / "deep")
    assert _name() == "daemon-acme.sock", (
        "a checkout is not required to be named after its registry key; "
        "the match is on the entry's own path"
    )

    monkeypatch.chdir(tmp_path)
    assert _name() == "daemon.sock", "outside any project, the name is unchanged"


def test_explicit_argument_beats_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standing in one project must not override a server told to serve another."""
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    # cwd is this checkout, a registered project; the argument must still win.
    assert _name("twa") == "daemon-twa.sock"


def test_unreadable_registry_never_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """principle 8: resolving a path must not be what kills a hook."""
    monkeypatch.delenv("DRUNKEN_PROJECT", raising=False)
    monkeypatch.delenv("DRUNKEN_DAEMON_SOCKET", raising=False)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(broken))
    assert _name() == "daemon.sock"


def test_installer_can_target_another_registered_project() -> None:
    """One checkout holds the code; every project needs its own agent.

    Without this the only project that could ever get a daemon is the one this
    checkout is registered as, and every other project's MCP server would dial
    a socket nobody binds -- a loud failure instead of a silent wrong room, but
    still no way to fix it.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import setup_daemon_service as svc

    assert svc._label("twa") != svc._label("isac")
    assert svc._log_path("twa") != svc._log_path("isac"), (
        "two daemons interleaving into one log makes the first question during "
        "an incident -- which project -- unanswerable"
    )
    assert svc._slugify("../x") == "x"
