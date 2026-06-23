#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import subprocess
import discord

def load_dotenv():
    # Look for .env in current directory or parent directories
    curr_dir = os.getcwd()
    while True:
        dotenv_path = os.path.join(curr_dir, '.env')
        if os.path.exists(dotenv_path):
            try:
                with open(dotenv_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, val = line.split('=', 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if key and key not in os.environ:
                                os.environ[key] = val
            except Exception as e:
                print(f"Warning: Failed to load .env file: {e}", file=sys.stderr)
            break
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent

# Automatically load local .env variables at startup
load_dotenv()

# Defaults
DEFAULT_BOT_TOKEN = None
DEFAULT_CHANNEL_ID = 1518206617336811573

def find_config():
    curr_dir = os.getcwd()
    while True:
        config_path = os.path.join(curr_dir, '.agents', 'discord_config.json')
        if os.path.exists(config_path):
            return config_path
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None

def load_config():
    config = {
        "bot_token": os.environ.get("DISCORD_BOT_TOKEN") or DEFAULT_BOT_TOKEN,
        "channel_id": None
    }
    
    # Try environment variable for Channel ID first
    env_channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if env_channel_id:
        try:
            config["channel_id"] = int(env_channel_id)
        except ValueError:
            pass

    # Read configuration file first
    config_file = find_config()
    if config_file:
        try:
            with open(config_file, "r") as f:
                file_data = json.load(f)
                if "bot_token" in file_data and file_data["bot_token"]:
                    config["bot_token"] = file_data["bot_token"]
                if "channel_id" in file_data and file_data["channel_id"]:
                    config["channel_id"] = int(file_data["channel_id"])
        except Exception as e:
            print(f"Warning: Failed to parse config file: {e}", file=sys.stderr)
            
    # Try 1Password CLI ONLY if environment and config bot_token is empty
    if not config["bot_token"] or config["bot_token"] == DEFAULT_BOT_TOKEN:
        DISCORD_URIS = [
            "op://Personal/Discord-TFF/token",
            "op://Private/Discord-TFF/token",
            "op://Personal/Discord-TFF/credential",
            "op://Private/Discord-TFF/credential"
        ]
        for uri in DISCORD_URIS:
            try:
                res = subprocess.run(["op", "read", uri], capture_output=True, text=True, check=True)
                token = res.stdout.strip()
                if token:
                    config["bot_token"] = token
                    break
            except Exception:
                continue

    # Fallback to default channel ID if not set
    if config["channel_id"] is None:
        config["channel_id"] = DEFAULT_CHANNEL_ID

    return config


if len(sys.argv) < 2:
    print("Error: Missing question argument.")
    print("Usage: python3 ask_boss.py <question>")
    sys.exit(1)

question = sys.argv[1]

config = load_config()
BOT_TOKEN = config["bot_token"]
CHANNEL_ID = config["channel_id"]

if not BOT_TOKEN:
    print("Error: Missing Discord Bot Token. Please set DISCORD_BOT_TOKEN in env or configure it.", file=sys.stderr)
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        try:
            channel = await client.fetch_channel(CHANNEL_ID)
        except Exception as e:
            print(f"Error fetching channel: {e}")
            await client.close()
            sys.exit(1)

    try:
        msg = await channel.send(question)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
    except Exception as e:
        print(f"Error sending message or reactions: {e}")
        await client.close()
        sys.exit(1)

    def check(reaction, user):
        # Ignore bot's own reactions
        if user.id == client.user.id:
            return False
        # Must be on the sent message
        if reaction.message.id != msg.id:
            return False
        # Must be thumbs up or down emoji
        if str(reaction.emoji) not in ["👍", "👎"]:
            return False
        # Must be from the server/guild owner
        if msg.guild and user.id == msg.guild.owner_id:
            return True
        # Fallback if not a guild message
        elif not msg.guild:
            return True
        return False

    try:
        reaction, user = await client.wait_for('reaction_add', check=check)
        if str(reaction.emoji) == "👍":
            print("Approved")
            await client.close()
            sys.exit(0)
        elif str(reaction.emoji) == "👎":
            print("Rejected")
            await client.close()
            sys.exit(1)
    except Exception as e:
        print(f"Error waiting for reaction: {e}")
        await client.close()
        sys.exit(1)

try:
    client.run(BOT_TOKEN)
except Exception as e:
    print(f"Error running Discord client: {e}")
    sys.exit(1)
