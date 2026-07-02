#!/usr/bin/env python3
import json
import os
import sys

import discord
from discord.ext import tasks

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

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

agent_runner = AgentRunner()
router = None

OUTBOX_FILE = os.path.join(os.getcwd(), ".agents", "discord_outbox.json")
INBOX_FILE = os.path.join(os.getcwd(), ".agents", "discord_inbox.json")
outbox_message_map: dict[int, str] = {}  # msg_id: req_id


@tasks.loop(seconds=5)
async def watch_outbox() -> None:
    if not os.path.exists(OUTBOX_FILE):
        return
    try:
        with open(OUTBOX_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    if not data:
        return

    channel = client.get_channel(int(CHANNEL_ID))
    if not channel:
        # Check if it's still loading or if ID is wrong
        try:
            channel = await client.fetch_channel(int(CHANNEL_ID))
        except Exception:
            return

    global outbox_message_map
    for req_id, req_data in data.items():
        if req_id in outbox_message_map.values():
            continue  # Already sent

        question = req_data.get("question", "Agent asks for permission.")
        try:
            msg = await channel.send(
                f"🤖 **Agent requires permission:**\n{question}\n\n*React with 👍 to approve, 👎 to reject.*"
            )
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
            outbox_message_map[msg.id] = req_id
        except Exception as e:
            print(f"Error sending outbox message: {e}", flush=True)


@client.event  # type: ignore[misc]
async def on_ready() -> None:
    print(f"[{client.user}] Bot is ready and listening...", flush=True)
    if not watch_outbox.is_running():
        watch_outbox.start()


@client.event  # type: ignore[misc]
async def on_reaction_add(reaction: discord.Reaction, user: discord.User) -> None:
    if user.bot:
        return

    global outbox_message_map
    if reaction.message.id in outbox_message_map:
        emoji = str(reaction.emoji)
        if emoji in ["👍", "👎"]:
            req_id = outbox_message_map.pop(reaction.message.id)
            status = "approved" if emoji == "👍" else "rejected"

            # Write to inbox
            inbox_data = {}
            if os.path.exists(INBOX_FILE):
                try:
                    with open(INBOX_FILE, "r") as f:
                        inbox_data = json.load(f)
                except json.JSONDecodeError:
                    pass

            inbox_data[req_id] = {"status": status}
            os.makedirs(os.path.dirname(INBOX_FILE), exist_ok=True)
            with open(INBOX_FILE, "w") as f:
                json.dump(inbox_data, f, indent=2)

            # Remove from outbox
            if os.path.exists(OUTBOX_FILE):
                try:
                    with open(OUTBOX_FILE, "r") as f:
                        outbox_data = json.load(f)
                    if req_id in outbox_data:
                        del outbox_data[req_id]
                        with open(OUTBOX_FILE, "w") as f:
                            json.dump(outbox_data, f, indent=2)
                except Exception as e:
                    print(f"Error removing from outbox: {e}", flush=True)

            await reaction.message.reply(f"Boss has **{status}** the request.")
            return

    if str(reaction.emoji) == "❌":
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
        router = DiscordRouter(client, agent_runner, CHANNEL_ID)
    await router.route(message)
    return


def main() -> int:
    client.run(BOT_TOKEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
