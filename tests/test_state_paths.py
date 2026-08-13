# mypy: ignore-errors
"""State lives under ``$DRUNKEN_HOME``; only packaged code is found via ``__file__``.

The distinction is the whole fix. Locating a *module that ships with this
package* through ``__file__`` is correct — it moves with the code. Locating a
*socket, registry or pid file* that way is the §1.3 bug: installed with
``uv tool install`` the expression resolves inside the virtualenv, so the daemon
and the MCP server that talks to it end up pointing at two different sockets and
neither of them says so.

Every module below therefore has to agree with :mod:`core.paths`, because
"agreeing" is the entire contract between a daemon and its clients.
"""

import ast
import os
import stat
from pathlib import Path

import pytest

from core import paths

#: Modules that must never derive user state from their own location, nor from
#: wherever they happened to be launched.
STATE_OWNERS = (
    "src/board_mcp/server.py",
    "src/discord_mcp/server.py",
    "src/service/approval_manager.py",
    "src/service/discord_listener.py",
    "src/service/discord_runner.py",
    "src/service/discord_router.py",
)

#: `scripts/check_pending_approval.py` is deliberately not in that list: it
#: uses `__file__` to bootstrap `sys.path` so it can import this project under
#: pre-commit's `language: system` python. That locates *code*, which is the
#: allowed half of the rule, and no static check can tell the two apart. It is
#: covered by TestThePreCommitGuardLooksAtTheRightSocket instead, which is the
#: property that actually matters.

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)  # type: ignore[misc]
def clean_env(monkeypatch):
    for var in (
        paths.ENV_HOME,
        paths.ENV_REGISTRY,
        paths.ENV_SOCKET,
        paths.ENV_SOCKET_LEGACY,
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("relative", STATE_OWNERS)  # type: ignore[misc]
def test_no_module_derives_state_from_its_own_location(relative: str) -> None:
    """Checked against the AST, so prose in a docstring describing the bug does
    not count as committing it."""
    tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "__file__" not in referenced, (
        f"{relative} resolves a path from __file__. Under 'uv tool install' "
        "that lands inside the virtualenv rather than a checkout."
    )


@pytest.mark.parametrize("relative", STATE_OWNERS)  # type: ignore[misc]
def test_no_module_derives_state_from_the_working_directory(relative: str) -> None:
    """The same bug in its other dialect, which the DT-241 sweep missed.

    ``os.getcwd()`` is arguably worse than ``__file__``: it does not even
    survive being launched from a different directory, and it is why the
    approval snapshot only ever worked because launchd pins WorkingDirectory.
    """
    tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
    calls = {
        f"{node.func.value.id}.{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }
    assert "os.getcwd" not in calls, (
        f"{relative} resolves a path from os.getcwd(). State belongs under "
        "$DRUNKEN_HOME, not wherever the process was started."
    )


class TestEveryoneAgreesOnTheSocket:
    """A daemon and a client that disagree here fail silently: the client gets
    'connection refused' and reports the daemon as down while it is running."""

    def test_the_mcp_client_and_the_daemon_resolve_the_same_path(self) -> None:
        from discord_mcp import server as mcp_server
        from service import discord_listener

        assert mcp_server.socket_path() == discord_listener.socket_path()
        assert mcp_server.socket_path() == str(paths.daemon_socket_path())

    def test_the_override_is_read_at_call_time(self, monkeypatch, tmp_path) -> None:
        """Captured at import instead, a container setting the variable in its
        entrypoint would be ignored."""
        from discord_mcp import server as mcp_server

        target = tmp_path / "elsewhere.sock"
        monkeypatch.setenv(paths.ENV_SOCKET, str(target))

        assert mcp_server.socket_path() == str(target)

    def test_the_deprecated_variable_still_works(self, monkeypatch, tmp_path) -> None:
        """Existing setups set AGY_DAEMON_SOCKET. Breaking them to tidy a name
        is not worth it; it is removed in 3.0.0."""
        from service import discord_listener

        target = tmp_path / "legacy.sock"
        monkeypatch.setenv(paths.ENV_SOCKET_LEGACY, str(target))

        assert discord_listener.socket_path() == str(target)


class TestSocketPermissions:
    """S6. The approval socket is how a yes/no reaches the machine, so anyone
    who can write to it can approve their own request."""

    def test_the_socket_is_locked_down_after_binding(self, tmp_path) -> None:
        from service.discord_listener import secure_socket

        sock = tmp_path / "daemon.sock"
        sock.touch(mode=0o777)

        secure_socket(str(sock))

        mode = stat.S_IMODE(os.stat(sock).st_mode)
        assert mode == 0o600, (
            f"socket left at {oct(mode)}. Connecting to a unix socket needs "
            "write permission, so group/other write is the whole vulnerability."
        )

    def test_it_does_not_fail_when_the_socket_is_absent(self, tmp_path) -> None:
        """Called on a path that was never bound, this must not take the daemon
        down with it — principle 8."""
        from service.discord_listener import secure_socket

        secure_socket(str(tmp_path / "never-created.sock"))


class TestThePreCommitGuardLooksAtTheRightSocket:
    """It fails open by design — a daemon that is down must not stop you
    committing. That makes pointing it at the wrong path invisible: it reports
    'daemon not running', returns 0, and pre-commit prints Passed."""

    def test_it_resolves_the_same_socket_as_the_daemon(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_pending_approval",
            REPO_ROOT / "scripts" / "check_pending_approval.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        from service import discord_listener

        assert module.socket_path() == discord_listener.socket_path()


class TestPackagedCodeIsStillFoundByLocation:
    """The other half of the rule: a module that ships with the package should
    be located through the package, and that keeps working once installed."""

    def test_the_bridge_scripts_resolve_through_the_package(self) -> None:
        from service import discord_router

        assert Path(discord_router.JIRA_BRIDGE_SCRIPT).is_file()
        assert Path(discord_router.QA_AUTOMATION_SCRIPT).is_file()
