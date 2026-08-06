#!/usr/bin/env python3
import asyncio
import json
import os
import sys

import discord

from core.context import ProjectContext
from core.registry import ProjectRegistry
from jira_mcp.jira_client import JiraClient
from service.approval_manager import ApprovalManager
from service.discord_router import DiscordRouter
from service.discord_runner import AgentRunner
from service.discord_utils import load_config

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


registry = ProjectRegistry()
projects = registry.get_projects()
if projects:
    project_id = list(projects.keys())[0]
    ctx = ProjectContext.build(project_id)
    jira_client = JiraClient(ctx)
else:
    jira_client = None  # type: ignore
agent_runner = AgentRunner()
approval_manager = ApprovalManager(client, int(CHANNEL_ID), agent_runner, jira_client)
router = None

# Anchored to the repo root via this file's own location, not os.getcwd() —
# the daemon and the MCP stdio subprocess it talks to can be launched from
# different working directories, so a cwd-relative path would silently
# point at two different sockets.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOCKET_PATH = os.environ.get(
    "AGY_DAEMON_SOCKET", os.path.join(_REPO_ROOT, ".agents", "agy_daemon.sock")
)

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
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)
    _socket_server = await asyncio.start_unix_server(
        _handle_socket_client, path=SOCKET_PATH
    )
    print(f"[Socket] Approval IPC listening on {SOCKET_PATH}", flush=True)
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
