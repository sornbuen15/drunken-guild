#!/usr/bin/env python3
import time

#!/usr/bin/env python3
import os
import sys
import json
import uuid
import subprocess


def load_dotenv():
    # Look for .env in current directory or parent directories
    curr_dir = os.getcwd()
    while True:
        dotenv_path = os.path.join(curr_dir, ".env")
        if os.path.exists(dotenv_path):
            try:
                with open(dotenv_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, val = line.split("=", 1)
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
DEFAULT_CHANNEL_ID = None


def find_config():
    curr_dir = os.getcwd()
    while True:
        config_path = os.path.join(curr_dir, ".agents", "discord_config.json")
        if os.path.exists(config_path):
            return config_path
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None


def save_config(config):
    config_file = find_config()
    if not config_file:
        config_file = os.path.join(os.getcwd(), ".agents", "discord_config.json")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save config file: {e}", file=sys.stderr)


def load_config():
    config = {
        "bot_token": os.environ.get("DISCORD_BOT_TOKEN") or DEFAULT_BOT_TOKEN,
        "channel_id": None,
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
        DISCORD_URIS = (
            os.environ.get("DISCORD_PASS_URIS", "").split(",")
            if os.environ.get("DISCORD_PASS_URIS")
            else [
                "op://Personal/Discord/token",
                "op://Private/Discord/token",
                "op://Personal/Discord/credential",
                "op://Private/Discord/credential",
            ]
        )
        for uri in DISCORD_URIS:
            try:
                res = subprocess.run(
                    ["op", "read", uri],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                token = res.stdout.strip()
                if token:
                    config["bot_token"] = token
                    save_config(
                        config
                    )  # Cache it so we don't ask for fingerprint again
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
req_id = str(uuid.uuid4())

outbox_file = os.path.join(os.getcwd(), ".agents", "discord_outbox.json")
inbox_file = os.path.join(os.getcwd(), ".agents", "discord_inbox.json")
os.makedirs(os.path.dirname(outbox_file), exist_ok=True)

# Write to outbox
outbox = {}
if os.path.exists(outbox_file):
    try:
        with open(outbox_file, "r") as f:
            outbox = json.load(f)
    except Exception:
        pass
outbox[req_id] = {"question": question, "timestamp": time.time()}
try:
    with open(outbox_file, "w") as f:
        json.dump(outbox, f)
except Exception as e:
    print(f"Failed to write to outbox: {e}")
    os._exit(1)

print("Question sent instantly. Waiting for Boss's reaction on Discord (👍/👎/🌟)...")

# Poll inbox

while True:
    if os.path.exists(inbox_file):
        try:
            with open(inbox_file, "r") as f:
                inbox = json.load(f)
            if req_id in inbox:
                status = inbox[req_id]["status"]

                # Cleanup inbox
                del inbox[req_id]
                try:
                    with open(inbox_file, "w") as f:
                        json.dump(inbox, f)
                except Exception:
                    pass

                if status == "approved":
                    print("Approved")
                    os._exit(0)
                elif status == "approved_always":
                    print("Approved Always (🌟)")
                    os._exit(0)
                else:
                    print("Rejected")
                    os._exit(1)
        except Exception:
            time.sleep(1)
    time.sleep(1)
