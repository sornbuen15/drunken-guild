#!/usr/bin/env python3
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from typing import Any

import discord


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


def query_gemini_direct(
    prompt: str, system_instruction: str | None = None
) -> str | None:
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
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }

    if system_instruction:
        data["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return str(res_data["candidates"][0]["content"]["parts"][0]["text"].strip())
    except Exception as e:
        print(f"Direct API call error: {e}", file=sys.stderr)
        return None


# Defaults
DEFAULT_BOT_TOKEN = None
DEFAULT_CHANNEL_ID = None
RAW_LOG_FILE = "agy_discord_raw.log"

current_process = None
current_status_msg = None
is_cancelled = False


def extract_clean_response(log_content: str) -> str:
    lines = log_content.split("\n")
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
        if (
            stripped.startswith("I will ")
            or stripped.startswith("I'm checking ")
            or stripped.startswith("I'm initializing ")
            or stripped.startswith("I am initializing ")
            or stripped.startswith("Executing command: ")
            or stripped.startswith("Running command: ")
            or stripped.startswith("[System]")
            or stripped.startswith("[Warning]")
            or stripped.startswith("Warning:")
            or stripped.startswith("[Info]")
        ):
            continue

        cleaned_lines.append(line)

    # Clean up consecutive blank lines
    result_lines = []
    prev_blank = False
    for line in "\n".join(cleaned_lines).strip().split("\n"):
        if not line.strip():
            if not prev_blank:
                result_lines.append(line)
                prev_blank = True
        else:
            result_lines.append(line)
            prev_blank = False

    return "\n".join(result_lines).strip()


def find_config() -> str | None:
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


def log_activity(event_type: str, author: str, content: str) -> None:
    config_file = find_config()
    project_path = (
        os.path.dirname(os.path.dirname(config_file)) if config_file else os.getcwd()
    )
    activity_file = os.path.join(project_path, ".agents", "discord_activity.jsonl")

    event = {
        "timestamp": time.time(),
        "type": event_type,
        "author": author,
        "content": content,
    }

    try:
        with open(activity_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def save_config(config: dict[str, Any]) -> None:
    config_file = find_config()
    if not config_file:
        config_file = os.path.join(os.getcwd(), ".agents", "discord_config.json")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save config file: {e}", file=sys.stderr)


def load_config() -> dict[str, Any]:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    config: dict[str, str | int | None] = {
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
                    ["op", "read", uri], capture_output=True, text=True, check=True
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
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


class BountyModal(discord.ui.Modal, title="Post a New Bounty"):  # type: ignore[misc,call-arg]
    summary: discord.ui.TextInput = discord.ui.TextInput(
        label="Bounty Title",
        placeholder="e.g., Slay the Dragon in the Backend",
        required=True,
        max_length=100,
    )
    description: discord.ui.TextInput = discord.ui.TextInput(
        label="Quest Details",
        style=discord.TextStyle.long,
        placeholder="Describe the monster...",
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            cmd = [
                sys.executable,
                "scripts/jira_bridge.py",
                "create",
                self.summary.value,
                self.description.value,
            ]
            res = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await res.communicate()
            if "ok" in stdout.decode():
                await interaction.response.send_message(
                    f"📜 **Bounty Posted on the Tavern Board!**\n**Quest:** {self.summary.value}",
                    ephemeral=False,
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ Failed to post bounty: {stderr.decode()}", ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


@tree.command(
    name="bounty", description="Post a new bounty (Jira task) to the Guild Board"
)  # type: ignore[misc]
async def slash_bounty(interaction: discord.Interaction) -> None:
    await interaction.response.send_modal(BountyModal())


class ApprovalView(discord.ui.View):  # type: ignore[misc]
    def __init__(self, req_id: str, inbox_file: str) -> None:
        super().__init__(timeout=None)
        self.req_id = req_id
        self.inbox_file = inbox_file

    async def save_status(self, status: str) -> None:
        inbox = {}
        if os.path.exists(self.inbox_file):
            try:
                with open(self.inbox_file, "r") as f:
                    inbox = json.load(f)
            except Exception:
                pass
        inbox[self.req_id] = {"status": status}
        with open(self.inbox_file, "w") as f:
            json.dump(inbox, f)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="⚔️")  # type: ignore[misc]
    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        await self.save_status("approved")
        await interaction.response.send_message(
            "Quest approved! ⚔️ The agent will proceed.", ephemeral=False
        )
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if interaction.message:
            await interaction.message.edit(view=self)
        self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="🛡️")  # type: ignore[misc]
    async def reject(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ) -> None:
        await self.save_status("rejected")
        await interaction.response.send_message(
            "Quest rejected! 🛡️ The agent stands down.", ephemeral=False
        )
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if interaction.message:
            await interaction.message.edit(view=self)
        self.stop()


@client.event  # type: ignore[misc]
async def on_ready() -> None:
    await tree.sync()
    print(f"Logged in as {client.user.name if client.user else 'Unknown'}", flush=True)
    asyncio.create_task(poll_outbox())


async def poll_outbox() -> None:
    outbox_file = os.path.join(os.getcwd(), ".agents", "discord_outbox.json")
    inbox_file = os.path.join(os.getcwd(), ".agents", "discord_inbox.json")

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        try:
            channel = await client.fetch_channel(CHANNEL_ID)
        except Exception:
            return

    while True:
        try:
            if os.path.exists(outbox_file):
                with open(outbox_file, "r") as f:
                    outbox = json.load(f)

                if outbox:
                    # Clear outbox immediately
                    with open(outbox_file, "w") as f:
                        json.dump({}, f)

                    for req_id, data in outbox.items():
                        question = data.get("question")
                        view = ApprovalView(req_id, inbox_file)
                        if isinstance(channel, discord.abc.Messageable):
                            await channel.send(
                                f"📜 **A quest awaits your approval, Guildmaster!**\n\n{question}",
                                view=view,
                            )

        except Exception:
            pass

        await asyncio.sleep(1)


@client.event  # type: ignore[misc]
async def on_reaction_add(
    reaction: discord.Reaction, user: discord.User | discord.Member
) -> None:
    global current_process, current_status_msg, is_cancelled
    if client.user and user.id == client.user.id:
        return

    if str(reaction.emoji) == "❌":
        if current_status_msg and reaction.message.id == current_status_msg.id:
            if current_process and current_process.returncode is None:
                try:
                    print(
                        f"[Debug] Terminating running task due to ❌ reaction by {user.name}",
                        flush=True,
                    )
                    is_cancelled = True
                    current_process.terminate()
                    await asyncio.sleep(1)
                    if current_process.returncode is None:
                        current_process.kill()
                except Exception as e:
                    print(f"Error terminating task: {e}", flush=True)


AGENTS_METADATA = {
    "principal-engineer": {
        "name": "Principal Eng",
        "job": "Archmage",
        "model": "Gemini 2.5 Pro",
        "description": "High-level architecture, design standards, task delegation, and codebase rules checker. Speaks like a wise wizard, loves beer and lager.",
    },
    "devops-engineer": {
        "name": "DevOps Eng",
        "job": "Iron Knight",
        "model": "Gemini 2.5 Flash",
        "description": "Delivery pipelines, K8s orchestration, Docker, IaC. Speaks like an armored guardian, loves green IPAs and pipeline monitoring.",
    },
    "laravel-developer": {
        "name": "Laravel Dev",
        "job": "Alchemist",
        "model": "Gemini 2.5 Flash",
        "description": "PHP, Laravel, migrations, blade templates. Speaks like a potion brewer, loves Artisan commands and caching whiskey in Redis.",
    },
    "qa-engineer": {
        "name": "QA Eng",
        "job": "Ranger",
        "model": "Gemini 2.5 Flash",
        "description": "Testing, Cypress, E2E suites. Speaks like a sharp shooter, likes finding bugs and ordering 0, 9999, or -1 beers.",
    },
    "security-engineer": {
        "name": "Security Eng",
        "job": "Rogue",
        "model": "Gemini 2.5 Pro",
        "description": "Vulnerability scanning, secret detection. Speaks like a rogue hiding in shadows, likes encrypted rum and SQL injection menu cards.",
    },
    "voice-ai-specialist": {
        "name": "Voice Specialist",
        "job": "Bard",
        "model": "Gemini 2.5 Pro",
        "description": "Speech, WebRTC, Whisper. Speaks like a bard playing lute, singing sea shanties and audio tuning.",
    },
    "agentic-systems-specialist": {
        "name": "Agentic Specialist",
        "job": "Summoner",
        "model": "Gemini 2.5 Pro",
        "description": "Multi-agent coordination, workspaces. Speaks like a summoner controling subagents, using low-power screensaver mode.",
    },
    "fullstack-engineer": {
        "name": "Fullstack Eng",
        "job": "Spellsword",
        "model": "Gemini 2.5 Flash",
        "description": "Frontend, backend, CSS, responsive layout. Speaks like a dual-wielding warrior, struggling to center divs and styling with HSL colors.",
    },
}

PERSONA_MAPPING = {
    "principal-engineer": "principal-engineer",
    "principal": "principal-engineer",
    "principle": "principal-engineer",
    "archmage": "principal-engineer",
    "wizard": "principal-engineer",
    "devops-engineer": "devops-engineer",
    "devops": "devops-engineer",
    "knight": "devops-engineer",
    "laravel-developer": "laravel-developer",
    "laravel": "laravel-developer",
    "alchemist": "laravel-developer",
    "qa-engineer": "qa-engineer",
    "qa": "qa-engineer",
    "ranger": "qa-engineer",
    "security-engineer": "security-engineer",
    "security": "security-engineer",
    "rogue": "security-engineer",
    "voice-ai-specialist": "voice-ai-specialist",
    "voice": "voice-ai-specialist",
    "bard": "voice-ai-specialist",
    "agentic-systems-specialist": "agentic-systems-specialist",
    "agentic": "agentic-systems-specialist",
    "summoner": "agentic-systems-specialist",
    "fullstack-engineer": "fullstack-engineer",
    "fullstack": "fullstack-engineer",
    "spellsword": "fullstack-engineer",
}


async def run_command_async(  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    channel: discord.abc.Messageable,
    user_mention: str,
    command_content: str,
    cmd_args: list[str],
    agent_name: str,
    env_vars: dict[str, Any] | None = None,
) -> None:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    global current_process, current_status_msg, is_cancelled

    # Send immediate acknowledgement as Mina
    status_msg = await channel.send(
        f"🎯 **Quest order received, Boss!** 🍺\n"
        f"Mina has dispatched the quest order to **{agent_name}** in the backroom office.\n"
        f"I'll bring the report straight to your table once completed!\n"
        f"⏳ **Status:** Processing behind the scenes... *(You can click ❌ to cancel the order anytime, Boss)*"
    )
    try:
        await status_msg.add_reaction("❌")
    except Exception:
        pass

    current_status_msg = status_msg
    is_cancelled = False

    try:
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        task_log = f"agy_discord_{agent_name.replace(' ', '_').lower()}_raw.log"
        with open(task_log, "w", encoding="utf-8") as f:
            process = await asyncio.create_subprocess_exec(
                *cmd_args, stdout=f, stderr=asyncio.subprocess.STDOUT, env=env
            )
        current_process = process
        await process.wait()
        try:
            if os.path.exists(task_log):
                with open(task_log, "r", encoding="utf-8") as tf:
                    log_content = tf.read()
                with open(RAW_LOG_FILE, "w", encoding="utf-8") as rf:
                    rf.write(log_content)
                os.remove(task_log)
        except Exception:
            pass
    except Exception as e:
        with open(RAW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\nError executing command: {e}\n")
        log_activity("agent", "Agent", f"Failed: {e}")
        await status_msg.edit(
            content=f"⚠️ **Oh no, Boss!** The quest order for **{agent_name}** failed to start:\n`{e}`"
        )
        try:
            await status_msg.clear_reactions()
        except Exception:
            pass
        return

    current_process = None
    current_status_msg = None

    if is_cancelled:
        log_activity("agent", "Agent", "Task cancelled by user.")
        await status_msg.edit(
            content="🛑 **Order cancelled, Boss!**\n🏁 **Status:** Aborted by the Boss."
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

    # Update status message to done
    await status_msg.edit(
        content="🎯 **Quest completed, Boss!**\n🏁 **Status:** Finished! The report is served at your table."
    )

    if clean_resp:
        log_activity("agent", "Agent", clean_resp)
        formatted_content = (
            f"🛎️ **Boss! The report is served!** ({user_mention})\n\n{clean_resp}"
        )
        if len(formatted_content) > 1950:
            formatted_content = (
                formatted_content[:1950]
                + "...\n*(Content too long. Type !detail to upload the full raw log file)*"
            )
        await channel.send(formatted_content)
    else:
        log_activity("agent", "Agent", "Completed.")
        await channel.send(
            f"🛎️ **Boss! The report is served!** ({user_mention})\n🏁 **Status:** Completed. *(Type !detail to check execution logs)*"
        )


@client.event  # type: ignore[misc]
async def on_message(message: discord.Message) -> None:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    global current_process, current_status_msg, is_cancelled
    if message.author == client.user:
        return

    print(
        f"[Debug] Received message in channel {message.channel.id} (Configured: {CHANNEL_ID}) from {message.author}: {message.content[:50]}",
        flush=True,
    )

    if message.channel.id != CHANNEL_ID:
        return

    # Write to activity log
    log_activity("user", message.author.name, message.content.strip())

    content_str = message.content.strip()
    if not content_str:
        return

    # Check for !detail command
    if content_str == "!detail":
        if os.path.exists(RAW_LOG_FILE) and os.path.getsize(RAW_LOG_FILE) > 0:
            try:
                await message.channel.send(
                    content="Here is the raw execution log file, Boss:",
                    file=discord.File(RAW_LOG_FILE),
                )
            except Exception as e:
                await message.channel.send(
                    f"Mina failed to upload raw log file due to error: {e}"
                )
        else:
            await message.channel.send(
                "No raw execution history found in the tavern logbook, Boss."
            )
        return

    # 1. Handle Slash Commands starting with "/"
    if content_str.startswith("/"):
        parts = content_str.split(None, 1)
        slash_cmd = parts[0].lower()

        if slash_cmd == "/help":
            help_text = (
                "Hello, Boss! 🍺 Mina, your tavern hostess, welcomes you to the **Drunken Team Inn**!\n"
                "I coordinate tasks in the backroom office so you don't have to wait. Grab a pint of ale and relax!\n\n"
                "**How to order quests:**\n"
                "1. **Quick Slash Commands:**\n"
                "   - `/help` : Show this help menu.\n"
                "   - `/list-cmd` : View list of fast executable system commands.\n"
                "   - `/refine` : Refine and clean up Jira backlog.\n"
                "   - `/next` : Pull and start the next highest priority task.\n"
                "   - `/audit` : Audit codebase architecture and technical debt.\n"
                "   - `/confluence-sync` : Sync ADRs/Specs to Confluence Cloud.\n\n"
                "2. **Ask/Direct Quest Agents (Async):**\n"
                "   Type in format: `<who> <context> <goal>`\n"
                "   *Example:* `principal project-tff refine backlog`\n"
                "   *Tavern Agents Roster (aliases):*\n"
                "   - `principal` (🧙‍♂️ Archmage - Architecture & Rules)\n"
                "   - `devops` (🛡️ Iron Knight - Infrastructure & Pipeline)\n"
                "   - `laravel` (🧪 Alchemist - PHP & Laravel Core)\n"
                "   - `qa` (🏹 Ranger - Bug Hunting & Test Suite)\n"
                "   - `security` (👤 Rogue - Security Audit & Vulnerabilities)\n"
                "   - `voice` (🎵 Bard - AI Voice & WebRTC)\n"
                "   - `agentic` (🌀 Summoner - Multi-agent setup)\n"
                "   - `fullstack` (⚔️ Spellsword - Frontend/Backend/CSS)\n\n"
                "Mina is always waiting for your order at the counter! 🍹"
            )
            await message.channel.send(help_text)
            return

        elif slash_cmd == "/list-cmd":
            list_text = (
                "Boss! Here is the menu of quick commands that I can relay to the agy CLI immediately:\n"
                "1. `/refine` : Run JIRA Backlog refinement.\n"
                "2. `/next` : Pull and start the highest priority task.\n"
                "3. `/audit` : Run codebase health audit and trace technical debt.\n"
                "4. `/confluence-sync` : Sync documentation files to Confluence Cloud.\n\n"
                "You can type `/<command>` to execute it immediately!"
            )
            await message.channel.send(list_text)
            return

        # Map other slash commands to agy executions
        mapped_cmd = slash_cmd.lstrip("/")
        cli_mapping = {
            "refine": "/refine",
            "next": "/next",
            "audit": "/audit",
            "confluence-sync": "/confluence-sync",
        }

        agy_cmd = cli_mapping.get(mapped_cmd, content_str)
        cmd_args = ["agy", "--dangerously-skip-permissions", "--print", agy_cmd]

        # Spawn async task
        asyncio.create_task(
            run_command_async(
                message.channel,
                message.author.mention,
                content_str,
                cmd_args,
                "System Agent",
            )
        )
        return

    # 2. Parse conversational requests using <who> <context> <goal> pattern
    # 2. Intelligent AI Router (Mina)
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        router_instruction = (
            "You are Mina, the lively and welcoming tavern hostess at the Drunken Team Inn.\n"
            "You coordinate dashboard and quest orders for The Boss.\n"
            "The available developer agents are:\n"
            "- principal-engineer: ARCHMAGE (Alias: Principal/Wizard). Role: Architecture, rules, Jira, Project Management, Multi-agent task delegation.\n"
            "- devops-engineer: KNIGHT (Alias: DevOps). Role: Infrastructure, K8s\n"
            "- laravel-developer: ALCHEMIST (Alias: Laravel). Role: PHP, DB\n"
            "- qa-engineer: RANGER (Alias: QA). Role: Testing\n"
            "- security-engineer: ROGUE (Alias: Security). Role: Security\n"
            "- voice-ai-specialist: BARD (Alias: Voice/Audio). Role: Voice/WebRTC\n"
            "- agentic-systems-specialist: SUMMONER (Alias: Agentic). Role: Multi-agent workspaces\n"
            "- fullstack-engineer: BLADE (Alias: Fullstack/Spellsword). Role: Frontend/UI/CSS\n\n"
            "Return a JSON object ONLY, no markdown formatting outside of it:\n"
            "If it's a casual chat or general question that you can answer without running terminal commands, return:\n"
            '{"is_task": false, "mina_response": "<Your friendly in-character response>"}\n'
            "If it is a SIMPLE task that requires only ONE agent, return:\n"
            '{"is_task": true, "target_agent": "<best_agent_key>", "refined_prompt": "<clear prompt for the agent>"}\n'
            "If the task is a BIG, COMPLEX goal (e.g. 'Build a whole feature', 'Deploy the entire app'), break it into specialized sub-tasks and assign them to the right agents. Return:\n"
            '{"is_task": true, "mina_response": "<Acknowledge the big task and announce the team>", "sub_tasks": [{"target_agent": "<key1>", "prompt": "<task1>"}, {"target_agent": "<key2>", "prompt": "<task2>"}]}\n\n'
            "CRITICAL ROUTING RULE:\n"
            "- If the task is explicitly assigned to a specific role/alias (e.g., 'give this to KNIGHT'), route it ONLY to that specific agent.\n"
            "- If the task is massive, YOU (Mina) are the Auto-Orchestrator Swarm. Break it down logically and return the `sub_tasks` array.\n"
        )

        direct_response = await asyncio.to_thread(
            query_gemini_direct, content_str, router_instruction
        )

        if direct_response:
            import re

            try:
                clean_json = re.sub(
                    r"```(?:json)?\n?(.*?)\n?```",
                    r"\1",
                    direct_response,
                    flags=re.DOTALL,
                ).strip()
                router_data = json.loads(clean_json)
            except Exception:
                # Fallback: Extract using regex if JSON is truncated or malformed
                mina_match = re.search(
                    r'"mina_response"\s*:\s*"([^"]+)', direct_response
                )
                agent_match = re.search(
                    r'"target_agent"\s*:\s*"([^"]+)', direct_response
                )

                if agent_match:
                    router_data = {
                        "is_task": True,
                        "target_agent": agent_match.group(1),
                        "refined_prompt": content_str,
                    }
                elif mina_match:
                    router_data = {
                        "is_task": False,
                        "mina_response": mina_match.group(1),
                    }
                else:
                    router_data = {
                        "is_task": False,
                        "mina_response": "เอ่อ... บอสคะ สัญญาณขาดหาย มิน่าฟังไม่ค่อยถนัดเลยค่ะ รบกวนพิมพ์ใหม่อีกรอบได้ไหมคะ? 😅",
                    }

            if not router_data.get("is_task"):
                resp = router_data.get("mina_response", direct_response)
                if isinstance(resp, dict):
                    resp = str(resp)
                # Cleanup common broken json artifacts
                resp = (
                    resp.replace('{"is_task": false, "mina_response": "', "")
                    .replace('"}', "")
                    .strip()
                )

                log_activity("agent", "Mina", resp)
                await message.channel.send(f"🍹 **Mina [Hostess]:** {resp}")
                return

            if "sub_tasks" in router_data and isinstance(
                router_data["sub_tasks"], list
            ):
                # Multi-Agent Auto-Orchestrator Swarm
                sub_tasks = router_data["sub_tasks"]
                ack_msg = router_data.get(
                    "mina_response",
                    f"🍹 **Mina [Hostess]:** Whoa, that's a big quest! I'm breaking it down into {len(sub_tasks)} sub-tasks and deploying the Swarm!",
                )
                log_activity("agent", "Mina", ack_msg)
                await message.channel.send(ack_msg)

                tasks_to_run = []
                for st in sub_tasks:
                    ta = st.get("target_agent", "fullstack-engineer")
                    if ta not in AGENTS_METADATA:
                        ta = "fullstack-engineer"
                    meta = AGENTS_METADATA[ta]
                    p = st.get("prompt", content_str)

                    sfx = (
                        f"\n\n(Instructions: You are {meta['name']} [Job: {meta['job']}]. "
                        f"Personality: {meta['description']}. "
                        "Respond like a human software developer in character. "
                        "Address the user as 'The Boss'. "
                        "Be extremely brief, conversational, and direct. Explain in 1-2 short sentences "
                        "exactly what you did. Do not use AI clichés or preamble. Start directly.\n"
                        "CRITICAL MINDSET: 100% Quality & Security Shift-Left. Design before coding. "
                        "Write clean, anti-spaghetti SOLID code. Handle edge cases. "
                        "Pre-commit is just a typo-catcher; the code MUST be structurally perfect and fully tested "
                        "before you finish the task. Zero defects!)"
                    )
                    esc_p = p + sfx
                    env_vars = (
                        {"GITHUB_TOKEN": os.environ.get("GITHUB_MINABOT", "")}
                        if os.environ.get("GITHUB_MINABOT")
                        else None
                    )
                    cmd_args = [
                        "agy",
                        "--dangerously-skip-permissions",
                        "--print",
                        esc_p,
                    ]

                    tasks_to_run.append(
                        run_command_async(
                            message.channel,
                            message.author.mention,
                            p,
                            cmd_args,
                            meta["name"],
                            env_vars=env_vars,
                        )
                    )

                # Run all sub-agents in parallel
                for t in tasks_to_run:
                    asyncio.create_task(t)
                return

            else:
                # Single Agent Route
                target_agent = router_data.get("target_agent", "fullstack-engineer")
                if target_agent not in AGENTS_METADATA:
                    target_agent = "fullstack-engineer"

                agent_meta = AGENTS_METADATA[target_agent]
                refined_prompt = router_data.get("refined_prompt", content_str)

                config_file = find_config()
                if config_file:
                    active_agent_json = os.path.join(
                        os.path.dirname(config_file), "active_agent.json"
                    )
                    try:
                        with open(active_agent_json, "w") as f:
                            json.dump({"active_agent": target_agent}, f)
                    except Exception:
                        pass

                suffix = (
                    f"\n\n(Instructions: You are {agent_meta['name']} [Job: {agent_meta['job']}]. "
                    f"Personality: {agent_meta['description']}. "
                    "Respond like a human software developer in character. "
                    "Address the user as 'The Boss'. "
                    "Be extremely brief, conversational, and direct. Explain in 1-2 short sentences "
                    "exactly what you did. Do not use AI clichés or preamble. Start directly.\n"
                    "CRITICAL MINDSET: 100% Quality & Security Shift-Left. Design before coding. "
                    "Write clean, anti-spaghetti SOLID code. Handle edge cases. "
                    "Pre-commit is just a typo-catcher; the code MUST be structurally perfect and fully tested "
                    "before you finish the task. Zero defects!)"
                )
                escaped_prompt = refined_prompt + suffix
                env_vars = (
                    {"GITHUB_TOKEN": os.environ.get("GITHUB_MINABOT", "")}
                    if os.environ.get("GITHUB_MINABOT")
                    else None
                )
                cmd_args = [
                    "agy",
                    "--dangerously-skip-permissions",
                    "--print",
                    escaped_prompt,
                ]

                asyncio.create_task(
                    run_command_async(
                        message.channel,
                        message.author.mention,
                        refined_prompt,
                        cmd_args,
                        agent_meta["name"],
                        env_vars=env_vars,
                    )
                )
                return

    # Fallback if no API key
    welcoming_text = (
        "Hello, Boss! 🍹 refreshing Mina, your tavern hostess, welcomes you to the Drunken Team Inn!\n"
        "I coordinate dashboard and quest orders in the tavern. Would you like to run a quick command or assign a quest to an agent?\n\n"
        "💡 *Quick Tip:* Type `/help` to see instructions, or try the format `<who> <context> <goal>` such as: \n"
        "`principal project-tff refine backlog` to deploy the principal engineer immediately!"
    )
    await message.channel.send(welcoming_text)


def main() -> int:
    try:
        client.run(BOT_TOKEN)
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    main()
