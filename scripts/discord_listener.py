#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import subprocess
import urllib.request
import discord

def query_gemini_direct(prompt, system_instruction=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    contents = [{"parts": [{"text": prompt}]}]
    data = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 400,
            "temperature": 0.7
        }
    }
    
    if system_instruction:
        data["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
        
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Direct API call error: {e}", file=sys.stderr)
        return None

# Defaults
DEFAULT_BOT_TOKEN = None
DEFAULT_CHANNEL_ID = 123456789012345678
RAW_LOG_FILE = 'agy_discord_raw.log'

current_process = None
current_status_msg = None
is_cancelled = False

def extract_clean_response(log_content):
    lines = log_content.split('\n')
    cleaned_lines = []
    in_thinking = False
    
    for line in lines:
        stripped = line.strip()
        
        # Track thinking tags
        if stripped == "<thinking>":
            in_thinking = True
            continue
        if stripped == "</thinking>":
            in_thinking = False
            continue
        if in_thinking:
            continue
            
        # Filter out system logs or tool output marker lines
        if (stripped.startswith("I will ") or 
            stripped.startswith("I'm checking ") or 
            stripped.startswith("I'm initializing ") or
            stripped.startswith("I am initializing ") or
            stripped.startswith("Executing command: ") or
            stripped.startswith("Running command: ") or
            stripped.startswith("[System]") or
            stripped.startswith("[Warning]") or
            stripped.startswith("Warning:") or
            stripped.startswith("[Info]")):
            continue
            
        cleaned_lines.append(line)
        
    # Clean up consecutive blank lines
    result_lines = []
    prev_blank = False
    for line in "\n".join(cleaned_lines).strip().split('\n'):
        if not line.strip():
            if not prev_blank:
                result_lines.append(line)
                prev_blank = True
        else:
            result_lines.append(line)
            prev_blank = False
            
    return "\n".join(result_lines).strip()

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

import time
def log_activity(event_type, author, content):
    config_file = find_config()
    project_path = os.path.dirname(os.path.dirname(config_file)) if config_file else os.getcwd()
    activity_file = os.path.join(project_path, ".agents", "discord_activity.jsonl")
    
    event = {
        "timestamp": time.time(),
        "type": event_type,
        "author": author,
        "content": content
    }
    
    try:
        with open(activity_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass

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
        try:
            res = subprocess.run(["op", "read", "op://Private/Discord-TFF/token"], capture_output=True, text=True, check=True)
            token = res.stdout.strip()
            if token:
                config["bot_token"] = token
        except Exception:
            pass

    # Fallback to default channel ID if not set
    if config["channel_id"] is None:
        config["channel_id"] = DEFAULT_CHANNEL_ID

    return config

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
    print(f"Logged in as {client.user.name}", flush=True)

@client.event
async def on_reaction_add(reaction, user):
    global current_process, current_status_msg, is_cancelled
    if user.id == client.user.id:
        return
        
    if str(reaction.emoji) == "❌":
        if current_status_msg and reaction.message.id == current_status_msg.id:
            if current_process and current_process.returncode is None:
                try:
                    print(f"[Debug] Terminating running task due to ❌ reaction by {user.name}", flush=True)
                    is_cancelled = True
                    current_process.terminate()
                    await asyncio.sleep(1)
                    if current_process.returncode is None:
                        current_process.kill()
                except Exception as e:
                    print(f"Error terminating task: {e}", flush=True)

@client.event
async def on_message(message):
    global current_process, current_status_msg, is_cancelled
    if message.author == client.user:
        return

    print(f"[Debug] Received message in channel {message.channel.id} (Configured: {CHANNEL_ID}) from {message.author}: {message.content[:50]}", flush=True)

    if message.channel.id != CHANNEL_ID:
        return

    # Write to activity log
    log_activity("user", message.author.name, message.content.strip())

    # Check for !detail command
    if message.content.strip() == "!detail":
        if os.path.exists(RAW_LOG_FILE) and os.path.getsize(RAW_LOG_FILE) > 0:
            try:
                await message.channel.send(
                    content="Here is the full unfiltered log file:",
                    file=discord.File(RAW_LOG_FILE)
                )
            except Exception as e:
                await message.channel.send(f"Error sending log file: {e}")
        else:
            await message.channel.send("No detailed raw log available or file is empty.")
        return

    command_str = message.content.strip()
    if not command_str:
        return

    # Check direct conversational query first to reduce latency
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # Determine command prefix
    subcommands_and_flags = {
        "models", "help", "plugin", "plugins", "install", 
        "update", "changelog", "-p", "--print", "--prompt", 
        "-i", "--prompt-interactive", "-c", "--continue"
    }
    words = command_str.split()
    first_word = words[0] if words else ""
    
    is_direct_chat = False
    direct_response = None
    
    if first_word not in subcommands_and_flags and api_key:
        barkeep_instruction = (
            "You are the Tavern Keeper (Barkeep) of the Drunken AGY Inn, a helpful AI assistant bridge.\n"
            "Review the user's message/command. You have two choices:\n"
            "1. If the user request asks you to write code, edit files, create scripts, run tests, run shell/terminal commands, search the codebase, or do engineering tasks that require actual workspace tools/actions, you MUST respond with exactly '[EXECUTE_AGY]' (nothing else).\n"
            "2. If it is a greeting, general question, explanation of code/concepts, conversation, status check, or tavern chat, reply directly as the friendly Barkeep. Keep it extremely brief (1-2 sentences), friendly, human-like, and JRPG-themed. Do not say '[EXECUTE_AGY]' if you can answer it yourself."
        )
        
        # Query in a worker thread to keep the asyncio event loop free
        direct_response = await asyncio.to_thread(query_gemini_direct, command_str, barkeep_instruction)
        
        if direct_response and "[EXECUTE_AGY]" not in direct_response:
            is_direct_chat = True

    if is_direct_chat and direct_response:
        log_activity("agent", "Agent", direct_response)
        await message.channel.send(direct_response)
        return

    if first_word in subcommands_and_flags:
        full_cmd = f"agy {command_str}"
    else:
        # Append instruction to keep final response concise, human-like, and focus on what was done
        suffix = (
            "\n\n(Instructions: Respond like a human software developer, not an AI. "
            "Be extremely brief, conversational, and direct. Explain in 1-2 short sentences "
            "exactly what you did. Do not use AI clichés or preamble. Start directly.)"
        )
        escaped_prompt = (command_str + suffix).replace('"', '\\"')
        full_cmd = f'agy --dangerously-skip-permissions --print "{escaped_prompt}"'

    is_cancelled = False

    # Binary status UI: Quest Accepted (Background running)
    status_msg = await message.channel.send(
        f"🎯 **Quest Accepted:** `{message.content}`\n"
        f"🧙‍♂️ *\"Understood, traveler! The party has set out on this quest. I will notify you once they return.\"*\n"
        f"⏳ **Status:** Quest in progress... (Est. time: 1-2 minutes) ❌ React to cancel."
    )
    try:
        await status_msg.add_reaction("❌")
    except Exception:
        pass

    try:
        # Redirect the entire process stdout and stderr directly to a local file
        log_redirect_cmd = f"{full_cmd} > {RAW_LOG_FILE} 2>&1"
        
        process = await asyncio.create_subprocess_shell(
            log_redirect_cmd,
            stdin=asyncio.subprocess.DEVNULL
        )
        
        current_process = process
        current_status_msg = status_msg
        
        await process.wait()
    except Exception as e:
        with open(RAW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\nError executing command: {e}\n")
        log_activity("agent", "Agent", f"Failed: {e}")
        await status_msg.edit(
            content=f"❌ **Quest Failed:** `{message.content}`\n🏁 **Status:** Failed to start. (Type !detail for logs)"
        )
        try:
            await status_msg.clear_reactions()
        except Exception:
            pass
        current_process = None
        current_status_msg = None
        return

    current_process = None
    current_status_msg = None

    if is_cancelled:
        log_activity("agent", "Agent", "Task cancelled by user.")
        await status_msg.edit(
            content=f"🛑 **Quest Cancelled:** `{message.content}`\n🏁 **Status:** Cancelled by user."
        )
        try:
            await status_msg.clear_reactions()
        except Exception:
            pass
        is_cancelled = False
        return

    # Read log and extract cleaned response
    clean_resp = ""
    if os.path.exists(RAW_LOG_FILE):
        try:
            with open(RAW_LOG_FILE, "r", encoding="utf-8") as f:
                raw_log = f.read()
                clean_resp = extract_clean_response(raw_log)
        except Exception:
            pass

    # Clean up reactions from the status message
    try:
        await status_msg.clear_reactions()
    except Exception:
        pass

    # Update status message to done, and send a brand new message with the actual result
    await status_msg.edit(
        content=f"🎯 **Quest Completed:** `{message.content}`\n🏁 **Status:** Done! Report sent below."
    )

    if clean_resp:
        log_activity("agent", "Agent", clean_resp)
        formatted_content = f"🏁 **Quest Report:** `{message.content}`\n\n{clean_resp}"
        if len(formatted_content) > 1950:
            formatted_content = formatted_content[:1950] + "...\n*(Content truncated. Type !detail for full logs)*"
        await message.channel.send(formatted_content)
    else:
        log_activity("agent", "Agent", "Completed.")
        await message.channel.send(
            f"🏁 **Quest Report:** `{message.content}`\n🏁 **Status:** Completed. (Type !detail for logs)"
        )

try:
    client.run(BOT_TOKEN)
except Exception as e:
    print(f"Error: {e}", flush=True)
