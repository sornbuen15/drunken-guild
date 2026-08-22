#!/usr/bin/env python3
import asyncio
import json
import os
import sys

import discord

from core import paths
from core.context import ProjectContext
from jira_mcp.jira_client import JiraClient
from service.approval_manager import ApprovalManager
from service.discord_router import DiscordRouter
from service.discord_runner import AgentRunner
from service.discord_utils import default_project_id, load_config

config = load_config()
BOT_TOKEN = config["bot_token"]
CHANNEL_ID = config["channel_id"]

if not BOT_TOKEN:
    print(
        "Error: Missing Discord Bot Token. Please set DISCORD_BOT_TOKEN in env or configure it.",
        file=sys.stderr,
    )
    sys.exit(1)

if not CHANNEL_ID:
    print(
        "Error: Missing Discord Channel ID. Please set DISCORD_CHANNEL_ID in env or configure it.",
        file=sys.stderr,
    )
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


# Which project this daemon serves is stated, never inferred. This used to read
# `list(projects.keys())[0]` -- the first key in a JSON file -- so on a machine
# with four registered projects the answer depended on which had been written
# first, and nothing anywhere reported the choice.
#
# `default_project_id()` takes DRUNKEN_PROJECT if it is set, and otherwise the
# single registered project when there is exactly one. With several and no
# variable it returns None, and the daemon starts without a Jira client rather
# than picking one: every project-scoped command then answers by naming the fix.
project_id = default_project_id()
if project_id:
    ctx = ProjectContext.build(project_id)
    jira_client = JiraClient(ctx)
    print(f"Serving project: {project_id}", file=sys.stderr)
else:
    jira_client = None  # type: ignore
    print(
        "No target project. Set DRUNKEN_PROJECT, or use /project <name> in "
        "Discord. Jira commands will say so until then.",
        file=sys.stderr,
    )
agent_runner = AgentRunner()
approval_manager = ApprovalManager(client, int(CHANNEL_ID), agent_runner, jira_client)
router = None


def socket_path() -> str:
    """Where this daemon listens.

    Resolved through :mod:`core.paths`, the one place the daemon and every
    client agree on. It used to be anchored to this file's own location, which
    is right from a checkout and points inside the virtualenv once installed —
    at which point a client reports the daemon as down while it is running.

    Called rather than captured at import so a container's entrypoint can still
    set ``DRUNKEN_DAEMON_SOCKET``.
    """
    return str(paths.daemon_socket_path())


def secure_socket(path: str) -> None:
    """Restrict the bound socket to its owner (S6).

    Connecting to a unix socket requires *write* permission on it, so the mode
    is the access control. Until now nothing set it and the result depended on
    the process umask: the usual 022 happens to be safe, umask 000 would have
    left it world-writable, and "safe because of how it was launched" is not a
    control.

    Missing file is not an error — a daemon must not die on startup over this
    (principle 8); the directory above is already 0700 either way.
    """
    try:
        os.chmod(path, paths.SECRET_FILE_MODE)
    except FileNotFoundError:
        pass


_socket_server: asyncio.base_events.Server | None = None
_startup_lock = asyncio.Lock()
# Separate flags on purpose: the socket server must start exactly once ever
# (starting it twice binds two servers to the same path), but
# recover_from_snapshot() should be retried on a later reconnect if it
# fails (e.g. a transient Jira/Discord API error) — collapsing these into
# one flag would either double-start the socket server on retry, or give up
# on recovery forever after one failure.
_socket_server_started = False
_recovery_complete = False

# A client that connects but never writes its request line (crashed
# subprocess, hung process) would otherwise leave this task — and its file
# descriptor — alive forever, unlike the bounded approval-wait path.
SOCKET_READ_TIMEOUT_SECONDS = 30


async def _handle_socket_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        try:
            line = await asyncio.wait_for(
                reader.readline(), timeout=SOCKET_READ_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            return
        if not line:
            return
        req = json.loads(line.decode("utf-8"))
        cmd = req.get("cmd")
        if cmd == "request_boss_approval":
            result = await approval_manager.request(
                req.get("action", ""), req.get("reason", ""), req.get("ticket_key", "")
            )
        elif cmd == "submit_approval":
            # Asynchronous sibling of request_boss_approval (DT-232): posts
            # the question and answers straight away with a handle, so the
            # caller can go and do something else.
            req_id = await approval_manager.submit(
                req.get("action", ""),
                req.get("reason", ""),
                req.get("ticket_key", ""),
                req.get("commit_sha"),
            )
            result = {"status": "submitted", "req_id": req_id}
        elif cmd == "poll_approvals":
            result = {
                "status": "ok",
                "results": approval_manager.poll(
                    req.get("req_ids", []), req.get("commit_sha")
                ),
            }
        elif cmd == "list_pending":
            result = {"status": "ok", "pending": approval_manager.list_pending()}
        elif cmd == "check_ticket":
            status = approval_manager.is_pending_or_escalated(req.get("ticket_key", ""))
            result = {"status": status or "clear"}
        else:
            result = {"status": "error", "detail": f"Unknown cmd: {cmd}"}
        writer.write((json.dumps(result) + "\n").encode("utf-8"))
        await writer.drain()
    except Exception as e:
        print(f"[Socket] Error handling client: {e}", flush=True)
        try:
            writer.write(
                (json.dumps({"status": "error", "detail": str(e)}) + "\n").encode(
                    "utf-8"
                )
            )
            await writer.drain()
        except Exception:
            pass
    finally:
        writer.close()


async def _start_socket_server() -> None:
    global _socket_server
    path = socket_path()
    if os.path.exists(path):
        os.remove(path)
    # ensure_home applies 0700 to the directory; the socket's own mode is set
    # immediately after binding, below.
    paths.ensure_home()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _socket_server = await asyncio.start_unix_server(_handle_socket_client, path=path)
    secure_socket(path)
    print(f"[Socket] Approval IPC listening on {path}", flush=True)
    async with _socket_server:
        await _socket_server.serve_forever()


@client.event  # type: ignore[misc]
async def on_ready() -> None:
    global _socket_server_started, _recovery_complete
    print(f"[{client.user}] Bot is ready and listening...", flush=True)
    # discord.py can refire on_ready after a session-invalidating reconnect.
    # A plain `if _socket_server is None` check races: _socket_server is only
    # assigned after start_unix_server() completes, so a second on_ready
    # firing before that finishes would pass the same check and start a
    # second socket server plus re-run recover_from_snapshot() (duplicate
    # Jira comments/Discord messages for anything still pending). The lock
    # plus flags set synchronously inside it closes that window.
    async with _startup_lock:
        if not _socket_server_started:
            _socket_server_started = True
            asyncio.create_task(_start_socket_server())

        if not _recovery_complete:
            try:
                await approval_manager.recover_from_snapshot()
                _recovery_complete = True
            except Exception as e:
                print(
                    f"[Startup] recover_from_snapshot failed ({e}) — will "
                    "retry on the next reconnect.",
                    flush=True,
                )


@client.event  # type: ignore[misc]
async def on_reaction_add(reaction: discord.Reaction, user: discord.User) -> None:
    if user.bot:
        return

    emoji = str(reaction.emoji)
    if emoji in ("👍", "👎"):
        resolved = await approval_manager.resolve(
            reaction.message.id, approved=(emoji == "👍")
        )
        if resolved:
            status = "approved" if emoji == "👍" else "rejected"
            await reaction.message.reply(f"Boss has **{status}** the request.")
        return

    if emoji == "❌":
        if (
            agent_runner.current_status_msg
            and reaction.message.id == agent_runner.current_status_msg.id
        ):
            if agent_runner.is_busy():
                print(
                    f"[Debug] Terminating running task due to ❌ reaction by {user.name}",
                    flush=True,
                )
                await agent_runner.cancel_current_task()


@client.event  # type: ignore[misc]
async def on_message(message: discord.Message) -> None:
    global router
    if not router:
        router = DiscordRouter(client, agent_runner, CHANNEL_ID, approval_manager)
    await router.route(message)
    return


def main() -> int:
    client.run(BOT_TOKEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
