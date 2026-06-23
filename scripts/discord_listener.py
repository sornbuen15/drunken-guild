#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import subprocess
import urllib.request
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
DEFAULT_CHANNEL_ID = 1518206617336811573
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
    }
}

PERSONA_MAPPING = {
    "principal-engineer": "principal-engineer",
    "principal": "principal-engineer",
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
    "spellsword": "fullstack-engineer"
}

async def run_command_async(channel, user_mention, command_content, full_cmd, agent_name):
    global current_process, current_status_msg, is_cancelled
    
    # Send immediate acknowledgement as Mina
    status_msg = await channel.send(
        f"🎯 **รับออเดอร์ด่วนค่ะนายท่าน!** 🍺\n"
        f"มินาส่งใบสั่งงานให้ **{agent_name}** ในห้องทำงานลับเรียบร้อยแล้วค่ะ \n"
        f"เดี๋ยวเขาทำเสร็จแล้วมินาจะรีบวิ่งคาบรายงานมาแจ้งที่โต๊ะทันทีเลยค่ะ! \n"
        f"⏳ **สถานะ:** กำลังทำงานหลังบ้าน... *(นายท่านกด ❌ เพื่อยกเลิกงานได้นะคะ)*"
    )
    try:
        await status_msg.add_reaction("❌")
    except Exception:
        pass
        
    current_status_msg = status_msg
    is_cancelled = False
    
    try:
        # Redirect stdout and stderr directly to raw log file
        log_redirect_cmd = f"{full_cmd} > {RAW_LOG_FILE} 2>&1"
        process = await asyncio.create_subprocess_shell(
            log_redirect_cmd,
            stdin=asyncio.subprocess.DEVNULL
        )
        current_process = process
        await process.wait()
    except Exception as e:
        with open(RAW_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\nError executing command: {e}\n")
        log_activity("agent", "Agent", f"Failed: {e}")
        await status_msg.edit(
            content=f"⚠️ **แย่แล้วค่ะนายท่าน!** งานของ **{agent_name}** เกิดข้อผิดพลาดเริ่มทำงานไม่ได้ค่ะ:\n`{e}`"
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
            content=f"🛑 **ออเดอร์ถูกยกเลิกแล้วค่ะนายท่าน!**\n🏁 **สถานะ:** นายท่านยกเลิกงานเรียบร้อยแล้วค่ะ"
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
        content=f"🎯 **ออเดอร์เสร็จสิ้นแล้วค่ะนายท่าน!**\n🏁 **สถานะ:** เสร็จสมบูรณ์! รายงานผลส่งตรงถึงโต๊ะบอสเรียบร้อยค่ะ"
    )

    if clean_resp:
        log_activity("agent", "Agent", clean_resp)
        formatted_content = f"🛎️ **นายท่านคะ! รายงานผลงานเสร็จแล้วค่ะ!** ({user_mention})\n\n{clean_resp}"
        if len(formatted_content) > 1950:
            formatted_content = formatted_content[:1950] + "...\n*(เนื้อหารายงานยาวเกินไป พิมพ์ !detail เพื่อดึงไฟล์ประวัติการทำงานแบบเต็มนะคะ)*"
        await channel.send(formatted_content)
    else:
        log_activity("agent", "Agent", "Completed.")
        await channel.send(
            f"🛎️ **นายท่านคะ! รายงานผลงานเสร็จแล้วค่ะ!** ({user_mention})\n🏁 **สถานะ:** เสร็จสิ้นเรียบร้อยแล้วค่ะ! *(พิมพ์ !detail เพื่อดู log เพิ่มเติมนะคะ)*"
        )

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

    content_str = message.content.strip()
    if not content_str:
        return

    # Check for !detail command
    if content_str == "!detail":
        if os.path.exists(RAW_LOG_FILE) and os.path.getsize(RAW_LOG_FILE) > 0:
            try:
                await message.channel.send(
                    content="นี่คือล็อกการทำงานดิบแบบเต็มรูปแบบค่ะนายท่าน:",
                    file=discord.File(RAW_LOG_FILE)
                )
            except Exception as e:
                await message.channel.send(f"มินาส่งล็อกไฟล์ดิบไม่ได้ค่ะเนื่องจากเกิดข้อผิดพลาด: {e}")
        else:
            await message.channel.send("ยังไม่มีประวัติการทำงานดิบในระบบค่ะบอส")
        return

    # 1. Handle Slash Commands starting with "/"
    if content_str.startswith("/"):
        parts = content_str.split(None, 1)
        slash_cmd = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        if slash_cmd == "/help":
            help_text = (
                "สวัสดีค่ะนายท่าน! 🍺 มินา สาวดูแลโรงเตี๊ยมยินดีต้อนรับบอสสู่ **Drunken AGY Inn** ค่ะ!\n"
                "หนูคอยช่วยประสานงานในห้องลับให้เอง นายท่านไม่ต้องนั่งรอผลลัพธ์ให้เหนื่อยค่ะ สั่งเสร็จไปนั่งจิบเบียร์รอได้เลยค่ะ!\n\n"
                "**วิธีการสั่งงานมินามีดังนี้ค่ะ:**\n"
                "1. **คำสั่งด่วนระบบ (Slash Commands):**\n"
                "   - `/help` : แสดงความช่วยเหลือนี้ค่ะ\n"
                "   - `/list-cmd` : ดูเมนูคำสั่งงานระบบด่วนที่รันได้ทันที\n"
                "   - `/refine` : เริ่มจัดระเบียบ/กลั่นกรอง Backlog ของโครงการ\n"
                "   - `/next` : ดึงงานความสำคัญสูงสุดถัดไปมาเริ่มทำทันที\n"
                "   - `/audit` : ตรวจสอบความสมบูรณ์และสถาปัตยกรรมของโครงการ\n"
                "   - `/confluence-sync` : ซิงค์เอกสาร ADRs/สเปกขึ้นระบบคลาวด์ Confluence\n\n"
                "2. **สั่งงานทั่วไป/ชวนคุย (Async):**\n"
                "   พิมพ์ในรูปแบบ: `<ใคร> <บริบท> <เป้าหมาย>`\n"
                "   *ตัวอย่างเช่น:* `principal project-tff refine backlog`\n"
                "   *รายชื่อสมาชิกในโรงเตี๊ยมที่สั่งงานได้ ( aliases ):*\n"
                "   - `principal` (🧙‍♂️ Archmage - สถาปัตยกรรม & กฎระบบ)\n"
                "   - `devops` (🛡️ Iron Knight - Server & K8s & Pipeline)\n"
                "   - `laravel` (🧪 Alchemist - โค้ด PHP & Laravel)\n"
                "   - `qa` (🏹 Ranger - ค้นหาบั๊ก & เขียน Test Suite)\n"
                "   - `security` (👤 Rogue - ค้นหาช่องโหว่ความปลอดภัย)\n"
                "   - `voice` (🎵 Bard - เสียง AI & WebRTC)\n"
                "   - `agentic` (🌀 Summoner - ระบบ multi-agent)\n"
                "   - `fullstack` (⚔️ Spellsword - หน้าบ้าน/หลังบ้าน/CSS)\n\n"
                "มินารอรับออเดอร์อยู่ที่เคาน์เตอร์บาร์เสมอนะคะ! 🍹"
            )
            await message.channel.send(help_text)
            return

        elif slash_cmd == "/list-cmd":
            list_text = (
                "นายท่านคะ! นี่คือเมนูคำสั่งด่วนที่มินาสามารถส่งคำสั่งตรงถึง agy ได้เลยค่ะ:\n"
                "1. `/refine` : สั่งให้กลั่นกรองและเลื่อนสถานะ Backlog JIRA\n"
                "2. `/next` : สั่งดึงงานสำคัญที่สุดมาทำทันที\n"
                "3. `/audit` : สั่งรัน codebase health audit ตรวจเช็ค technical debt\n"
                "4. `/confluence-sync` : สั่งอัปโหลด/ซิงค์เอกสารสเปกขึ้นระบบ Confluence Cloud\n\n"
                "บอสสามารถพิมพ์ `/<คำสั่ง>` เพื่อรันได้ทันทีค่ะ!"
            )
            await message.channel.send(list_text)
            return

        # Map other slash commands to agy executions
        mapped_cmd = slash_cmd.lstrip("/")
        cli_mapping = {
            "refine": "/refine",
            "next": "/next",
            "audit": "/audit",
            "confluence-sync": "/confluence-sync"
        }
        
        agy_cmd = cli_mapping.get(mapped_cmd, content_str)
        full_cmd = f'agy --dangerously-skip-permissions --print "{agy_cmd}"'
        
        # Spawn async task
        asyncio.create_task(run_command_async(
            message.channel, 
            message.author.mention, 
            content_str, 
            full_cmd, 
            "System Agent"
        ))
        return

    # 2. Parse conversational requests using <who> <context> <goal> pattern
    words = content_str.split()
    first_word = words[0].lower() if words else ""

    if first_word in PERSONA_MAPPING:
        agent_key = PERSONA_MAPPING[first_word]
        query_text = " ".join(words[1:]) if len(words) > 1 else ""
        
        if not query_text:
            await message.channel.send(
                f"สวัสดีค่ะนายท่าน! บอสต้องการคุยหรือสั่งอะไรกับ **{agent_key}** ดีคะ? \n"
                f"กรุณาพิมพ์เพิ่มในรูปแบบ: `{words[0]} <คำสั่งหรือเรื่องที่อยากถาม>` นะคะ"
            )
            return

        agent_meta = AGENTS_METADATA.get(agent_key, {
            "name": "Developer Persona",
            "job": "Guild Member",
            "model": "Gemini 2.5 Pro",
            "description": "Software engineer working in the project workspace.",
        })

        # Load active configuration & set active agent json dynamically
        config_file = find_config()
        if config_file:
            active_agent_json = os.path.join(os.path.dirname(config_file), "active_agent.json")
            try:
                with open(active_agent_json, "w") as f:
                    json.dump({"active_agent": agent_key}, f)
            except Exception:
                pass

        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            agent_instruction = (
                f"You are {agent_meta['name']}, a developer agent working in the project workspace.\n"
                f"Your Job role is: {agent_meta['job']}. Your personality: {agent_meta['description']}\n\n"
                "CRITICAL: The user is 'The Boss' (บอส / นายท่าน / Boss). Never address the user as 'adventurer', 'traveler', 'patron', 'young adventurer', or 'friend'. Address them with respect as 'The Boss'.\n\n"
                "Your task is to review the user's message/command. You have two choices:\n"
                "1. If the user request asks you to write code, edit files, create scripts, run tests, run shell/terminal commands, search the codebase, or do engineering tasks, OR IF THE USER ASKS ABOUT JIRA TASKS, JIRA BOARDS, BACKLOGS, ACTIVE FILES, OR WORKSPACE STATUS, you MUST respond with exactly '[EXECUTE_AGY]' (nothing else).\n"
                "2. If it is a greeting, general question, explanation of code/concepts, conversation, or greeting chat, reply directly as the character. Keep it extremely brief (1-2 sentences), friendly, in-character, and respectful. Do not say '[EXECUTE_AGY]' if you can answer it yourself."
            )
            
            # Query Gemini directly for the conversational check
            direct_response = await asyncio.to_thread(query_gemini_direct, query_text, agent_instruction)
            
            if direct_response and "[EXECUTE_AGY]" not in direct_response:
                log_activity("agent", agent_meta['name'], direct_response)
                # Format response with agent name/job for clarity
                await message.channel.send(f"💬 **{agent_meta['name']} [{agent_meta['job']}]:** {direct_response}")
                return

        # Fallback to agy execution if [EXECUTE_AGY] returned or if no API key
        suffix = (
            f"\n\n(Instructions: You are {agent_meta['name']} [Job: {agent_meta['job']}]. "
            f"Personality: {agent_meta['description']}. "
            "Respond like a human software developer in character, not an AI. "
            "Address the user as 'The Boss' (บอส / นายท่าน / Boss) with respect. Never refer to them as adventurer or traveler. "
            "Be extremely brief, conversational, and direct. Explain in 1-2 short sentences "
            "exactly what you did. Do not use AI clichés or preamble. Start directly.)"
        )
        escaped_prompt = (query_text + suffix).replace('"', '\\"')
        full_cmd = f'agy --dangerously-skip-permissions --print "{escaped_prompt}"'

        # Spawn async task
        asyncio.create_task(run_command_async(
            message.channel, 
            message.author.mention, 
            query_text, 
            full_cmd, 
            agent_meta['name']
        ))
        return

    # 3. Message does not match any known command pattern
    welcoming_text = (
        f"สวัสดีค่ะนายท่าน! 🍹 มินา สาวดูแลโรงเตี๊ยมยินดีต้อนรับบอสสู่ Drunken AGY Inn ค่ะ!\n"
        f"หนูคอยดูแลกระดานและออเดอร์ในโรงเตี๊ยมนี้ให้เองค่ะ บอสต้องการให้สั่งคำสั่งด่วนหรือมอบหมายงานให้นักผจญภัยคะ?\n\n"
        f"💡 *คำแนะนำด่วน:* พิมพ์ `/help` เพื่อดูวิธีใช้และคำสั่งระบบ หรือลองใช้รูปแบบ `<ใคร> <บริบท> <เป้าหมาย>` เช่น: \n"
        f"`principal project-tff refine backlog` เพื่อสั่งสถาปัตย์สูงสุดรันงานได้เลยค่ะ!"
    )
    await message.channel.send(welcoming_text)

def main():
    try:
        client.run(BOT_TOKEN)
    except Exception as e:
        print(f"Error: {e}", flush=True)

if __name__ == "__main__":
    main()


