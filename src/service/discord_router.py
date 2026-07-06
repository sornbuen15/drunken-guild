import asyncio
import json
import os
import re
from typing import Any

import discord
from core.registry import ProjectRegistry

from service.discord_runner import RAW_LOG_FILE, AgentRunner
from service.discord_utils import find_config, log_activity

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


async def _handle_detail_command(message: discord.Message) -> None:
    if os.path.exists(RAW_LOG_FILE) and os.path.getsize(RAW_LOG_FILE) > 0:
        try:
            await message.channel.send(
                content="Here is the raw execution log file, Boss:",
                file=discord.File(RAW_LOG_FILE),
            )
        except Exception as e:
            await message.channel.send(
                f"Agy failed to upload raw log file due to error: {e}"
            )
    else:
        await message.channel.send(
            "No raw execution history found in the system logs, Boss."
        )


async def _handle_slash_command(
    agent_runner: AgentRunner, message: discord.Message, content_str: str
) -> None:
    parts = content_str.split(None, 1)
    slash_cmd = parts[0].lower()
    if slash_cmd == "/help":
        help_text = (
            "Hello, Boss! 🚀 Agy, your system router, welcomes you to the **Antigravity Workspace**!\n"
            "I coordinate tasks in the backroom office so you don't have to wait. Grab a pint of ale and relax!\n\n"
            "**Available Commands:**\n"
            "   - `/help` : Show this help menu.\n"
            "   - `/list-cmd` : View list of fast executable system commands.\n"
            "   - `/status` : Check the real-time status and logs of the active agent.\n"
            "   - `/stop` or `/kill` : Emergency stop all running agents instantly.\n\n"
            "*(Note: Task creation and direct agent chatting via Discord is currently disabled. Please use the CLI.)*\n\n"
            "Agy is always waiting for your order at the counter! ⚡"
        )
        await message.channel.send(help_text)
        return
    elif slash_cmd == "/status":
        if agent_runner.is_busy():
            import glob
            import os

            logs = glob.glob("agy_discord_*_raw.log")
            if logs:
                latest_log = max(logs, key=os.path.getmtime)
                try:
                    with open(latest_log, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    filtered = [
                        line
                        for line in lines
                        if line.strip() not in ("<thinking>", "</thinking>")
                    ]
                    tail = "".join(filtered[-15:])
                    if not tail.strip():
                        tail = "(Just started or thinking deeply...)"
                    await message.channel.send(
                        f"🟢 **Workspace Status: BUSY**\nAn agent is currently active in the dungeon!\n**Latest Action:**\n```text\n{tail}\n```"
                    )
                except Exception as e:
                    await message.channel.send(
                        f"🟢 **Workspace Status: BUSY**\n(Agent is running, but couldn't read log: {e})"
                    )
            else:
                await message.channel.send(
                    "🟢 **Workspace Status: BUSY**\n(Agent just dispatched, waiting for first log entry...)"
                )
        else:
            await message.channel.send(
                "💤 **Workspace Status: IDLE**\nThe guild hall is quiet. No active quests."
            )
        return
    elif slash_cmd in ("/stop", "/kill"):
        import subprocess

        try:
            subprocess.run(["pkill", "-f", "agy"], check=False)
            await message.channel.send(
                "🛑 **Emergency Stop!** All active agents in the dungeon have been killed immediately."
            )
        except Exception as e:
            await message.channel.send(f"⚠️ Failed to kill agents: {e}")
        return
    elif slash_cmd == "/list-cmd":
        list_text = (
            "Boss! Here is the menu of quick commands:\n"
            "1. `/status` : Check the real-time status and logs of the active agent.\n"
            "2. `/stop` or `/kill` : Emergency stop all running agents instantly.\n\n"
            "You can type `/<command>` to execute it immediately!"
        )
        await message.channel.send(list_text)
        return
    await message.channel.send(
        "⚡ **Agy [System]:** คำสั่งนี้ถูกปิดใช้งานบน Discord แล้วค่ะ รบกวนสั่งงานผ่าน Terminal (CLI) แทนนะคะ ⚙️"
    )


def _parse_router_response(direct_response: str, content_str: str) -> dict[str, Any]:
    import re

    try:
        # Extract everything between the first { and the last }
        match = re.search(r"\{.*\}", direct_response, flags=re.DOTALL)
        if match:
            res = json.loads(match.group(0))
            return res if isinstance(res, dict) else {}
        # Fallback to pure json load
        fallback = json.loads(direct_response)
        return fallback if isinstance(fallback, dict) else {}
    except Exception as e:
        print(
            f"[Debug] Failed to parse router response: {direct_response} | Error: {e}",
            flush=True,
        )
        agy_match = re.search(r'"agy_response"\s*:\s*"([^"]+)', direct_response)
        agent_match = re.search(r'"target_agent"\s*:\s*"([^"]+)', direct_response)
        if agent_match:
            return {
                "is_task": True,
                "target_agent": agent_match.group(1),
                "refined_prompt": content_str,
            }
        elif agy_match:
            return {
                "is_task": False,
                "agy_response": agy_match.group(1),
            }
        else:
            return {
                "is_task": False,
                "agy_response": f"เอ่อ... บอสคะ สัญญาณขาดหาย มิน่าประมวลผลคำสั่งไม่ได้เลยค่ะ (Error JSON: {e})\nรบกวนบอสพิมพ์ใหม่อีกรอบได้ไหมคะ? 😅",
            }


def _build_agent_suffix(meta: dict[str, str]) -> str:
    return (
        f"\n\n(Instructions: You are {meta['name']} [Job: {meta['job']}]. "
        f"Personality: {meta['description']}. Respond like a human software developer in character. "
        "Address the user as 'The Boss'. Be extremely brief, conversational, and direct. "
        "Explain in 1-2 short sentences exactly what you did. Do not use AI clichés or preamble. Start directly.\n"
        "CRITICAL MINDSET: 100% Quality & Security Shift-Left. Design before coding. "
        "Write clean, anti-spaghetti SOLID code. Handle edge cases. "
        "Pre-commit is just a typo-catcher; the code MUST be structurally perfect and fully tested "
        "before you finish the task. Zero defects!\n"
        "IMPORTANT: If you need to start a server or long-running process, use run_command with a small WaitMsBeforeAsync so it goes to the background. Do NOT block your execution!\n"
        "ANTI-LOOP PROTOCOL (ค.ว.ย.): If you execute a command and it fails, and a subsequent fix results in the exact same failure, STOP IMMEDIATELY! Do NOT loop blindly. Return a failure report to the Boss explaining the roadblock.\n"
        "SILENT WAIT PROTOCOL (CRITICAL): If you need permission for ANYTHING, you MUST write your question in JSON to `.agents/discord_outbox.json` (e.g. `{\"req_1\": {\"question\": \"your question\"}}`). Then use the `schedule` tool to wait for the Boss's answer in `.agents/discord_inbox.json`, and IMMEDIATELY END YOUR TURN. Do NOT use `run_command` for approvals!)"
    )


async def _dispatch_swarm(
    agent_runner: AgentRunner,
    router_data: dict[str, Any],
    content_str: str,
    message: discord.Message,
) -> None:
    sub_tasks = router_data["sub_tasks"]
    ack_msg = router_data.get(
        "agy_response",
        f"⚡ **Agy [System]:** Whoa, that's a big quest! I'm breaking it down into {len(sub_tasks)} sub-tasks and deploying the Swarm!",
    )

    target_project = router_data.get("target_project")
    project_cwd = None
    if target_project:
        proj_data = ProjectRegistry().get_project(target_project)
        if proj_data:
            project_cwd = proj_data["path"]

    log_activity("agent", "Agy", ack_msg)
    await message.channel.send(ack_msg)
    tasks_to_run = []
    for st in sub_tasks:
        ta = st.get("target_agent", "fullstack-engineer")
        if ta not in AGENTS_METADATA:
            ta = "fullstack-engineer"
        meta = AGENTS_METADATA[ta]
        p = st.get("prompt", content_str)
        sfx = _build_agent_suffix(meta)
        esc_p = p + sfx
        env_vars = (
            {"GITHUB_TOKEN": os.environ.get("GITHUB_MINABOT", "")}
            if os.environ.get("GITHUB_MINABOT")
            else None
        )
        cmd_args = [
            "agy",
            "--dangerously-skip-permissions",
            "--new-project",
            "--print",
            esc_p,
        ]
        tasks_to_run.append(
            agent_runner.run_command_async(
                message.channel,
                message.author.mention,
                p,
                cmd_args,
                meta["name"],
                env_vars=env_vars,
                cwd=project_cwd,
                project_id=target_project or "drunken-team",
            )
        )
    for t in tasks_to_run:
        asyncio.create_task(t)


async def _dispatch_single_agent(
    agent_runner: AgentRunner,
    router_data: dict[str, Any],
    content_str: str,
    message: discord.Message,
) -> None:
    target_agent = router_data.get("target_agent", "fullstack-engineer")
    if target_agent not in AGENTS_METADATA:
        target_agent = "fullstack-engineer"
    agent_meta = AGENTS_METADATA[target_agent]
    refined_prompt = router_data.get("refined_prompt", content_str)

    target_project = router_data.get("target_project")
    project_cwd = None
    if target_project:
        proj_data = ProjectRegistry().get_project(target_project)
        if proj_data:
            project_cwd = proj_data["path"]

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
    suffix = _build_agent_suffix(agent_meta)
    escaped_prompt = refined_prompt + suffix
    env_vars = (
        {"GITHUB_TOKEN": os.environ.get("GITHUB_MINABOT", "")}
        if os.environ.get("GITHUB_MINABOT")
        else None
    )
    cmd_args = [
        "agy",
        "--dangerously-skip-permissions",
        "--new-project",
        "--print",
        escaped_prompt,
    ]
    asyncio.create_task(
        agent_runner.run_command_async(
            message.channel,
            message.author.mention,
            refined_prompt,
            cmd_args,
            agent_meta["name"],
            env_vars=env_vars,
            cwd=project_cwd,
            project_id=target_project or "drunken-team",
        )
    )


async def _handle_conversational_response(
    router_data: dict[str, Any], direct_response: str, message: discord.Message
) -> None:
    resp = router_data.get("agy_response", direct_response)
    if isinstance(resp, dict):
        resp = str(resp)
    resp = (
        resp.replace('{"is_task": false, "agy_response": "', "")
        .replace('"}', "")
        .strip()
    )
    log_activity("agent", "Agy", resp)
    await message.channel.send(f"⚡ **Agy [System]:** {resp}")


async def _handle_reply_continuation(
    client: discord.Client, agent_runner: AgentRunner, message: discord.Message
) -> bool:
    if not message.reference or not message.reference.message_id:
        return False
    try:
        original_message = await message.channel.fetch_message(
            message.reference.message_id
        )
        if original_message.author != client.user:
            return False

        import re

        # Look for the footer: *Reply to this message to continue working with **{agent_name}** in `{project_id}`*
        match = re.search(r"with \*\*(.*?)\*\* in `([^`]+)`", original_message.content)
        if not match:
            return False

        agent_name = match.group(1)
        target_project = match.group(2)

        project_info = ProjectRegistry().get_project(target_project)
        project_cwd = project_info.get("path") if project_info else None

        await message.channel.send(
            "⚡ **Agy [System]:** บอสคะ การสนทนาต่อเนื่องผ่าน Discord ถูกปิดใช้งานแล้วค่ะ รบกวนสั่งงานผ่าน Terminal (CLI) แทนนะคะ ⚙️"
        )
        return True
    except Exception as e:
        print(f"Error handling reply: {e}", flush=True)
        return False


class DiscordRouter:
    def __init__(
        self, client: discord.Client, agent_runner: AgentRunner, channel_id: int
    ):
        self.client = client
        self.agent_runner = agent_runner
        self.CHANNEL_ID = int(channel_id) if channel_id else 0

    async def route(self, message: discord.Message) -> None:
        if message.author == self.client.user:
            return
        print(
            f"[Debug] Received message in channel {message.channel.id} (Configured: {self.CHANNEL_ID}) from {message.author}: {message.content[:50]}",
            flush=True,
        )

        print(
            f"[Debug] Check Channel ID: message {int(message.channel.id)} vs self {self.CHANNEL_ID}",
            flush=True,
        )
        if int(message.channel.id) != self.CHANNEL_ID:
            print("[Debug] Channel ID mismatch! Returning early.", flush=True)
            return

        print("[Debug] Channel ID matches, logging activity...", flush=True)
        log_activity("user", message.author.name, message.content.strip())
        content_str = message.content.strip()
        if not content_str:
            return

        if content_str == "!detail":
            print("[Debug] matched !detail command", flush=True)
            await _handle_detail_command(message)
            return

        print(f"[Debug] processing content_str: {content_str}", flush=True)
        if content_str.startswith("/"):
            await _handle_slash_command(self.agent_runner, message, content_str)
            return

        if await _handle_reply_continuation(self.client, self.agent_runner, message):
            return

        # Deterministic Router
        content_lower = content_str.lower()
        first_word = content_lower.split()[0] if content_lower else ""

        # Strip leading punctuation for agent routing
        if first_word.startswith("!") or first_word.startswith("@"):
            first_word = first_word[1:]

        is_task = False
        target_agent = "fullstack-engineer"
        if first_word in PERSONA_MAPPING:
            target_agent = PERSONA_MAPPING[first_word]
            is_task = True

        target_project = "drunken-team"
        projects = ProjectRegistry().get_projects()
        for proj_key in projects.keys():
            if f"project-{proj_key.lower()}" in content_lower or re.search(
                rf"\b{proj_key.lower()}\b", content_lower
            ):
                target_project = proj_key
                break

        if is_task:
            await message.channel.send(
                "⚡ **Agy [System]:** บอสคะ ตอนนี้ระบบสั่งงานผ่าน Discord ถูกปิดใช้งานแล้วค่ะ\n"
                "รบกวนบอสสั่งงานผ่าน Terminal (CLI) แทนนะคะ!\n"
                "(รองรับแค่การเช็คสถานะด้วย `/status` และการกด Approve เท่านั้นค่ะ) ⚙️"
            )
            return
        else:
            await message.channel.send(
                "⚡ **Agy [System]:** Boss, if you want to assign a quest, please start your message with an agent's name!\n"
                "*(Example: `principal project-twa do something`)*\n"
                "Since I am now running on deterministic rules (no LLM), I need you to be specific! ⚙️"
            )
            return
