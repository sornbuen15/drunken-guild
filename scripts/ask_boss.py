#!/usr/bin/env python3
import json
import os
import sys
import time
import uuid
from typing import Any, Dict


def load_dotenv() -> None:
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


def load_config() -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "bot_token": os.environ.get("DISCORD_BOT_TOKEN"),
        "channel_id": None,
    }

    env_channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if env_channel_id:
        try:
            config["channel_id"] = int(env_channel_id)
        except ValueError:
            pass

    return config


if __name__ == "__main__":
    print("WARNING: ask_boss.py is DEPRECATED! Do NOT use this script.")
    print("Instead, use the Silent Wait Protocol:")
    print("1. Write your question to .agents/discord_outbox.json")
    print("2. Set a schedule timer and end your turn.")
    print("This script will now exit with an error.")
    sys.exit(1)

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
