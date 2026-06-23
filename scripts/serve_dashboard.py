#!/usr/bin/env python3
import os
import sys
import glob
import json
import subprocess
import urllib.request
import webbrowser
import http.server
import socketserver
from threading import Timer

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

def send_to_discord(project_path, user_msg, bot_msg):
    env_path = os.path.join(project_path, '.env')
    if not os.path.exists(env_path):
        return
        
    bot_token = None
    channel_id = None
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('DISCORD_BOT_TOKEN='):
                    bot_token = line.split('=', 1)[1].strip().strip('"').strip("'")
                elif line.startswith('DISCORD_CHANNEL_ID='):
                    channel_id = line.split('=', 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
                
    if bot_token and channel_id:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        
        # Format the message
        # Discord has a 2000 character limit per message
        content = f"**[Dashboard Terminal] The Boss:**\n> {user_msg}\n\n**Agent Response:**\n{bot_msg}"
        if len(content) > 1900:
            content = content[:1900] + "... (truncated)"
            
        data = {"content": content}
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            print(f"Failed to send to discord: {e}")

# Automatically load local .env variables at startup
load_dotenv()


AGENTS_METADATA = {
    "principal-engineer": {
        "name": "ARCHMAGE",
        "job": "Principal Eng",
        "model": "Gemini 2.5 Pro",
        "description": "High-level architecture, design standards, task delegation, and codebase rules checker. Speaks like a wise wizard, loves beer and lager.",
    },
    "devops-engineer": {
        "name": "KNIGHT",
        "job": "DevOps Eng",
        "model": "Gemini 2.5 Flash",
        "description": "Delivery pipelines, K8s orchestration, Docker, IaC. Speaks like an armored guardian, loves green IPAs and pipeline monitoring.",
    },
    "laravel-developer": {
        "name": "ALCHEMIST",
        "job": "Laravel Dev",
        "model": "Gemini 2.5 Flash",
        "description": "PHP, Laravel, migrations, blade templates. Speaks like a potion brewer, loves Artisan commands and caching whiskey in Redis.",
    },
    "qa-engineer": {
        "name": "RANGER",
        "job": "QA Eng",
        "model": "Gemini 2.5 Flash",
        "description": "Testing, Cypress, E2E suites. Speaks like a sharp shooter, likes finding bugs and ordering 0, 9999, or -1 beers.",
    },
    "security-engineer": {
        "name": "ROGUE",
        "job": "Security Eng",
        "model": "Gemini 2.5 Pro",
        "description": "Vulnerability scanning, secret detection. Speaks like a rogue hiding in shadows, likes encrypted rum and SQL injection menu cards.",
    },
    "voice-ai-specialist": {
        "name": "BARD",
        "job": "Voice Specialist",
        "model": "Gemini 2.5 Pro",
        "description": "Speech, WebRTC, Whisper. Speaks like a bard playing lute, singing sea shanties and audio tuning.",
    },
    "agentic-systems-specialist": {
        "name": "SUMMONER",
        "job": "Agentic Specialist",
        "model": "Gemini 2.5 Pro",
        "description": "Multi-agent coordination, workspaces. Speaks like a summoner controling subagents, using low-power screensaver mode.",
    },
    "fullstack-engineer": {
        "name": "BLADE",
        "job": "Fullstack Eng",
        "model": "Gemini 2.5 Flash",
        "description": "Frontend, backend, CSS, responsive layout. Speaks like a dual-wielding warrior, struggling to center divs and styling with HSL colors.",
    }
}

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


PORT = int(os.environ.get("PORT", 8081))
DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")

# Global in-memory storage for project mappings and Discord processes
project_paths = {}
discord_processes = {}

def get_running_discord_pid(project_path):
    try:
        normalized_path = os.path.normpath(project_path)
        # Use ps aux on macOS
        res = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            # Check for either scripts/discord_listener.py or global CLI binary "drunken-listen"
            if ("discord_listener.py" in line or "drunken-listen" in line) and "grep" not in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = parts[1]
                    cwd_res = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid], capture_output=True, text=True, timeout=2)
                    if normalized_path in cwd_res.stdout or normalized_path in line:
                        return int(pid)
    except Exception:
        pass
    return None

def start_discord_listener_for_project(project_id, project_path):
    pid = get_running_discord_pid(project_path)
    if pid is not None:
        return True

    script_path = os.path.join(project_path, ".agents", "scripts", "discord_listener.py")
    if not os.path.exists(script_path):
        script_path = os.path.join(project_path, "scripts", "discord_listener.py")

    if not os.path.exists(script_path):
        return False

    try:
        log_dir = os.path.join(project_path, ".agents")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "discord_listener.log")
        log_file = open(log_file_path, "w", encoding="utf-8")

        # Prefer running the globally installed CLI command if present
        import shutil
        listen_cmd = shutil.which("drunken-listen")

        if listen_cmd:
            print(f"[*] Starting Discord listener using global binary: {listen_cmd} in {project_path}")
            p = subprocess.Popen(
                [listen_cmd],
                cwd=project_path,
                stdout=log_file,
                stderr=log_file
            )
        else:
            print(f"[*] Starting Discord listener using fallback script: {script_path}")
            p = subprocess.Popen(
                [sys.executable, script_path],
                cwd=project_path,
                stdout=log_file,
                stderr=log_file
            )
        discord_processes[project_id] = p
        return True
    except Exception as e:
        print(f"Failed to start process for {project_id}: {e}", file=sys.stderr)
        return False

def is_discord_configured_for_project(p_path):
    # 1. Check config JSON file
    config_path = os.path.join(p_path, ".agents", "discord_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("bot_token") and data.get("channel_id"):
                    return True
        except Exception:
            pass

    # 2. Check local .env file
    env_path = os.path.join(p_path, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Simple substring checks to detect if token and channel variables are populated
                if "DISCORD_BOT_TOKEN=" in content and "DISCORD_CHANNEL_ID=" in content:
                    return True
        except Exception:
            pass
            
    return False

def start_all_discord_listeners():
    load_projects_mapping()
    print("[*] Checking and auto-starting Discord transceivers for all realms...")
    for p_id, p_path in project_paths.items():
        if is_discord_configured_for_project(p_path):
            if get_running_discord_pid(p_path) is None:
                started = start_discord_listener_for_project(p_id, p_path)
                if started:
                    print(f"[+] Automatically started Discord transceiver for Realm: {p_id}")
                else:
                    print(f"[-] Could not find listener script to start for Realm: {p_id}")


def is_agy_running(project_path):
    try:
        normalized_path = os.path.normpath(project_path)
        res = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            # Check if "agy" is anywhere in the command string (column 10 onwards)
            parts = line.split()
            if len(parts) > 10:
                cmd_full = " ".join(parts[10:])
                # Filter out grep and ensure we are matching agy execution
                if ("agy " in cmd_full or cmd_full.endswith("agy") or "/agy" in cmd_full) and "grep" not in cmd_full and "serve_dashboard" not in cmd_full:
                    pid = parts[1]
                    cwd_res = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid], capture_output=True, text=True, timeout=2)
                    if normalized_path in cwd_res.stdout:
                        return True
    except Exception:
        pass
    return False

def load_projects_mapping():
    global project_paths
    project_paths = {}
    projects_dir = os.path.expanduser("~/.gemini/config/projects")
    os.makedirs(projects_dir, exist_ok=True)
    if os.path.exists(projects_dir):
        for fpath in glob.glob(os.path.join(projects_dir, "*.json")):
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                    p_id = data.get("id")
                    p_path = data.get("name")
                    if p_id and p_path:
                        project_paths[p_id] = p_path
            except Exception:
                pass

    # Automatically register current working directory (CWD) if not already registered
    cwd_path = os.getcwd()
    cwd_registered_id = None
    for p_id, p_path in list(project_paths.items()):
        if os.path.abspath(p_path) == os.path.abspath(cwd_path):
            cwd_registered_id = p_id
            break

    if not cwd_registered_id:
        import uuid
        cwd_id = str(uuid.uuid4())
        project_file = os.path.join(projects_dir, f"{cwd_id}.json")
        reg_data = {
            "id": cwd_id,
            "name": os.path.abspath(cwd_path),
            "projectResources": {
                "resources": [
                    { "folderUri": f"file://{os.path.abspath(cwd_path)}" }
                ]
            }
        }
        try:
            with open(project_file, "w", encoding="utf-8") as f:
                json.dump(reg_data, f, indent=2)
            project_paths[cwd_id] = os.path.abspath(cwd_path)
            print(f"[+] Automatically registered active directory in Dashboard: {cwd_path}")
        except Exception as e:
            print(f"[-] Failed to auto-register current directory: {e}", file=sys.stderr)

    # Ensure current workspace is mapped
    curr_workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "drunken-agy" not in project_paths:
        project_paths["drunken-agy"] = curr_workspace

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            payload = json.loads(post_data)
        except Exception:
            payload = {}

        # 1. API: Save Discord Configuration
        if self.path == "/api/discord/save":
            project_id = payload.get("project_id")
            bot_token = payload.get("bot_token")
            channel_id = payload.get("channel_id")
            
            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return

            agents_dir = os.path.join(project_path, ".agents")
            os.makedirs(agents_dir, exist_ok=True)
            config_path = os.path.join(agents_dir, "discord_config.json")
            
            config_data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config_data = json.load(f)
                except Exception:
                    pass
            
            if bot_token:
                config_data["bot_token"] = bot_token
            if channel_id is not None:
                # Clean and save as string to prevent JS 64-bit precision loss
                clean_channel_id = "".join(c for c in str(channel_id) if c.isdigit())
                config_data["channel_id"] = clean_channel_id

            try:
                with open(config_path, "w") as f:
                    json.dump(config_data, f, indent=2)
                self.send_json_response({"ok": True, "message": "Discord config saved successfully."})
            except Exception as e:
                self.send_error_response(f"Failed to write config: {e}")

        # 2. API: Start Discord Listener
        elif self.path == "/api/discord/start":
            project_id = payload.get("project_id")
            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return

            success = start_discord_listener_for_project(project_id, project_path)
            if success:
                self.send_json_response({"ok": True, "message": "Discord listener started."})
            else:
                self.send_error_response("discord_listener.py not found in project scripts. Please run sync first.")


        # 3. API: Stop Discord Listener
        elif self.path == "/api/discord/stop":
            project_id = payload.get("project_id")
            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return
                
            pid = get_running_discord_pid(project_path)
            if pid:
                try:
                    import signal
                    os.kill(pid, signal.SIGTERM)
                    import time
                    for _ in range(20):
                        time.sleep(0.1)
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            break
                    else:
                        os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
                discord_processes[project_id] = None
                self.send_json_response({"ok": True, "message": "Discord listener stopped."})
            else:
                self.send_json_response({"ok": True, "message": "Discord listener is not running."})

        # 3.5. API: Save Active Agent
        elif self.path == "/api/project/active-agent":
            project_id = payload.get("project_id")
            agent_key = payload.get("agent_key")
            project_path = project_paths.get(project_id)
            if project_path and agent_key:
                agents_dir = os.path.join(project_path, ".agents")
                os.makedirs(agents_dir, exist_ok=True)
                active_agent_path = os.path.join(agents_dir, "active_agent.json")
                try:
                    with open(active_agent_path, "w", encoding="utf-8") as f:
                        json.dump({"active_agent": agent_key}, f, indent=2)
                    self.send_json_response({"ok": True})
                except Exception as e:
                    self.send_error_response(str(e))
                return
            self.send_error_response("Invalid request")

        # 4. API: Run dialogue prompt / terminal command
        elif self.path == "/api/terminal/run":
            project_id = payload.get("project_id")
            command = payload.get("command", "").strip()
            agent_key = payload.get("agent", "")
            agent_status = payload.get("status", "ACTIVE")
            
            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return
                
            if not command:
                self.send_error_response("Command is empty.")
                return
                
            api_key = os.environ.get("GEMINI_API_KEY")
            response_text = None
            
            if api_key:
                agent_meta = AGENTS_METADATA.get(agent_key, {
                    "name": "Companion",
                    "job": "Adventurer",
                    "model": "Gemini 2.5 Flash",
                    "description": "A helpful tavern companion."
                })
                
                system_instruction = (
                    f"You are {agent_meta['name']}, a developer agent working in the project workspace.\n"
                    f"Your Job role is: {agent_meta['job']}. Your personality: {agent_meta['description']}\n"
                    f"Your current status is: {agent_status}.\n\n"
                    "CRITICAL: The user is 'The Boss'. Never address the user as 'adventurer', 'traveler', 'patron', 'young adventurer', or 'friend'. Address them with respect as 'The Boss'.\n\n"
                    "Your task is to review the user's message/command. You have two choices:\n"
                    "1. If the user request asks you to write code, edit files, create scripts, run tests, run shell/terminal commands, search the codebase, or do engineering tasks, OR IF THE USER ASKS ABOUT JIRA TASKS, JIRA BOARDS, BACKLOGS, ACTIVE FILES, OR WORKSPACE STATUS (since you do not have direct access to JIRA or the filesystem in this conversational mode), you MUST respond with exactly '[EXECUTE_AGY]' (nothing else).\n"
                    "2. If it is a greeting, general question, explanation of code/concepts, conversation, or greeting chat, reply directly as the character. Keep it extremely brief (1-2 sentences), friendly, in-character, and respectful. Do not say '[EXECUTE_AGY]' if you can answer it yourself."
                )
                
                response_text = query_gemini_direct(command, system_instruction)
            
            if not response_text or "[EXECUTE_AGY]" in response_text:
                agent_meta = AGENTS_METADATA.get(agent_key, {
                    "name": "Principal Eng",
                    "job": "Archmage",
                    "model": "Gemini 2.5 Pro",
                    "description": "High-level architecture, design standards, task delegation, and codebase rules checker. Speaks like a wise wizard, loves beer and lager.",
                })
                
                # Immediate response to UI
                response_text = f"On it, Boss! I'll work on '{command}' asynchronously and let you know when it's done."
                self.send_json_response({"ok": True, "output": response_text})
                
                # Notify Discord that we started it
                import threading
                threading.Thread(
                    target=send_to_discord, 
                    args=(project_path, command, response_text),
                    daemon=True
                ).start()
                
                # Start background thread to run agy
                def run_agy_async():
                    suffix = (
                        f"\n\n(Instructions: You are {agent_meta['name']} [Job: {agent_meta['job']}]. "
                        f"Personality: {agent_meta['description']}. "
                        "Respond like a human software developer in character, not an AI. "
                        "Address the user as 'The Boss' with respect. Never refer to them as adventurer or traveler. "
                        "Be extremely brief, conversational, and direct. Explain in 1-2 short sentences "
                        "exactly what you did. Do not use AI clichés or preamble. Start directly.)"
                    )
                    escaped_prompt = command + suffix
                    args = ["agy", "--dangerously-skip-permissions", "--print", escaped_prompt]
                    try:
                        res = subprocess.run(
                            args,
                            cwd=project_path,
                            capture_output=True,
                            text=True
                            # no timeout so it can run as long as it needs
                        )
                        raw_out = res.stdout + "\n" + res.stderr
                        clean_resp = extract_clean_response(raw_out)
                        if not clean_resp:
                            clean_resp = raw_out.strip() or "Task completed without output."
                        final_result = f"✅ **Task Completed:** `{command}`\n\n{clean_resp}"
                    except Exception as e:
                        final_result = f"❌ **Task Failed:** `{command}`\n\nError: {e}"
                        
                    # Notify Discord of completion!
                    send_to_discord(project_path, "System Update", final_result)
                
                threading.Thread(target=run_agy_async, daemon=True).start()
                return
            
            # If it's just a conversational reply (no EXECUTE_AGY)
            self.send_json_response({"ok": True, "output": response_text})
            
            # Send mirror to Discord
            import threading
            threading.Thread(
                target=send_to_discord, 
                args=(project_path, command, response_text),
                daemon=True
            ).start()

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        # 1. API: List Projects (Without exposing absolute paths to frontend)
        if self.path == "/api/projects":
            load_projects_mapping()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            projects = []
            for p_id, p_path in project_paths.items():
                projects.append({
                    "id": p_id,
                    "name": os.path.basename(p_path)
                })
                
            self.wfile.write(json.dumps(projects).encode('utf-8'))

        # 2. API: Get Discord Status & Redacted Config
        elif self.path.startswith("/api/discord/status"):
            # Parse query params
            project_id = "drunken-agy"
            if "?" in self.path:
                params = self.path.split("?")[1]
                for p in params.split("&"):
                    if "=" in p:
                        k, v = p.split("=")
                        if k == "project_id":
                            project_id = v

            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return

            config_path = os.path.join(project_path, ".agents", "discord_config.json")
            has_token = False
            channel_id = ""
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        data = json.load(f)
                        raw_id = data.get("channel_id", "")
                        channel_id = str(raw_id) if raw_id is not None else ""
                        if data.get("bot_token"):
                            has_token = True
                except Exception:
                    pass

            pid = get_running_discord_pid(project_path)
            is_running = pid is not None

            self.send_json_response({
                "is_running": is_running,
                "has_token": has_token,
                "channel_id": channel_id
            })

        # 2.5 API: Get All Projects Discord Activity Logs
        elif self.path == "/api/discord/activity/all":
            load_projects_mapping()
            all_activities = {}
            for p_id, p_path in project_paths.items():
                activity_file = os.path.join(p_path, ".agents", "discord_activity.jsonl")
                events = []
                if os.path.exists(activity_file):
                    try:
                        with open(activity_file, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                            for line in lines[-20:]:
                                line_stripped = line.strip()
                                if line_stripped:
                                    events.append(json.loads(line_stripped))
                    except Exception:
                        pass
                all_activities[p_id] = events
            self.send_json_response(all_activities)

        # 3. API: Get Discord Activity Logs
        elif self.path.startswith("/api/discord/activity"):
            # Parse query params
            project_id = "drunken-agy"
            if "?" in self.path:
                params = self.path.split("?")[1]
                for p in params.split("&"):
                    if "=" in p:
                        k, v = p.split("=")
                        if k == "project_id":
                            project_id = v

            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return

            activity_file = os.path.join(project_path, ".agents", "discord_activity.jsonl")
            events = []
            if os.path.exists(activity_file):
                try:
                    with open(activity_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line_stripped = line.strip()
                            if line_stripped:
                                events.append(json.loads(line_stripped))
                except Exception:
                    pass

            self.send_json_response(events)

        # 4. API: Get Project Status (whether agy is running)
        elif self.path.startswith("/api/project/status"):
            # Parse query params
            project_id = "drunken-agy"
            if "?" in self.path:
                params = self.path.split("?")[1]
                for p in params.split("&"):
                    if "=" in p:
                        k, v = p.split("=")
                        if k == "project_id":
                            project_id = v

            project_path = project_paths.get(project_id)
            if not project_path:
                self.send_error_response("Project not found.")
                return

            agy_running = is_agy_running(project_path)
            active_agent = None
            try:
                active_agent_path = os.path.join(project_path, ".agents", "active_agent.json")
                if os.path.exists(active_agent_path):
                    with open(active_agent_path, "r") as f:
                        data = json.load(f)
                        active_agent = data.get("active_agent")
            except Exception:
                pass

            self.send_json_response({
                "agy_running": agy_running,
                "active_agent": active_agent
            })

        else:
            super().do_GET()

    def send_json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def send_error_response(self, msg):
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode('utf-8'))

def open_browser():
    webbrowser.open_url = getattr(webbrowser, 'open_url', None) or webbrowser.open
    webbrowser.open_url(f"http://localhost:{PORT}")

def clean_up_subprocesses():
    for p_id, proc in list(discord_processes.items()):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

def main():
    global PORT
    load_projects_mapping()
    if not os.path.exists(DIRECTORY):
        print(f"Error: Dashboard directory not found at {DIRECTORY}", file=sys.stderr)
        sys.exit(1)
        
    # Check if a custom port is passed as a command-line argument
    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except ValueError:
            pass
            
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("", PORT), Handler)
    except OSError as e:
        import errno
        if e.errno == errno.EADDRINUSE:
            print(f"[!] *hic* Port {PORT} is already in use! The Tavern is already open, Boss!")
            print(f"[*] Opening the existing door to welcome the Boss at: http://localhost:{PORT}")
            open_browser()
            sys.exit(0)
        else:
            raise e

    with httpd:
        print(f"[*] Drunken AGY Inn JRPG Dashboard running at http://localhost:{PORT}/")
        print("[*] Press Ctrl+C to close the Inn.")

        # Automatically start all registered Discord listeners
        try:
            start_all_discord_listeners()
        except Exception as e:
            print(f"Error auto-starting Discord listeners: {e}", file=sys.stderr)
        
        # Open browser after 1 second
        Timer(1.0, open_browser).start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Closing Inn. Terminating Discord listeners...")
            clean_up_subprocesses()
            print("[*] Safe travels, hero!")

if __name__ == "__main__":
    main()

