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


PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")

# Global in-memory storage for project mappings and Discord processes
project_paths = {}
discord_processes = {}

def load_projects_mapping():
    global project_paths
    project_paths = {}
    projects_dir = "/Users/operator/.gemini/config/projects"
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
                
    # Ensure current workspace is mapped
    curr_workspace = "/Users/operator/Projects/drunken-agy"
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

            # Check if already running
            proc = discord_processes.get(project_id)
            if proc and proc.poll() is None:
                self.send_json_response({"ok": True, "message": "Discord listener is already running."})
                return

            # Path to script
            script_path = os.path.join(project_path, ".agents", "scripts", "discord_listener.py")
            # Fallback path if it's not synchronized yet
            if not os.path.exists(script_path):
                script_path = os.path.join(project_path, "scripts", "discord_listener.py")
                
            if not os.path.exists(script_path):
                self.send_error_response("discord_listener.py not found in project scripts. Please run sync first.")
                return

            try:
                log_dir = os.path.join(project_path, ".agents")
                os.makedirs(log_dir, exist_ok=True)
                log_file_path = os.path.join(log_dir, "discord_listener.log")
                log_file = open(log_file_path, "w", encoding="utf-8")
                
                p = subprocess.Popen(
                    [sys.executable, script_path],
                    cwd=project_path,
                    stdout=log_file,
                    stderr=log_file
                )
                discord_processes[project_id] = p
                self.send_json_response({"ok": True, "message": "Discord listener started."})
            except Exception as e:
                self.send_error_response(f"Failed to start process: {e}")

        # 3. API: Stop Discord Listener
        elif self.path == "/api/discord/stop":
            project_id = payload.get("project_id")
            proc = discord_processes.get(project_id)
            
            if proc:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                discord_processes[project_id] = None
                self.send_json_response({"ok": True, "message": "Discord listener stopped."})
            else:
                self.send_json_response({"ok": True, "message": "Discord listener is not running."})

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
                    f"You are {agent_meta['name']}, a JRPG tavern companion in the Drunken AGY Inn, working as a developer agent in the project workspace.\n"
                    f"Your JRPG Job is: {agent_meta['job']}. Your model type is: {agent_meta['model']}.\n"
                    f"Personality description: {agent_meta['description']}\n"
                    f"Your current status is: {agent_status}.\n\n"
                    "Your task is to review the user's message/command. You have two choices:\n"
                    "1. If the user request asks you to edit code, create/modify files, run tests, run shell/terminal commands, search the codebase, or do engineering tasks that require actual workspace tools/actions, you MUST respond with exactly '[EXECUTE_AGY]' (nothing else).\n"
                    "2. If it is a greeting, general question, explanation of code/concepts, conversation, status check, or tavern chat, reply directly as the character. Keep it extremely brief (1-2 sentences), friendly, human-like, and JRPG-themed. Do not say '[EXECUTE_AGY]' if you can answer it yourself."
                )
                
                response_text = query_gemini_direct(command, system_instruction)
            
            if not response_text or "[EXECUTE_AGY]" in response_text:
                try:
                    args = ["agy", "--dangerously-skip-permissions", "--print", command]
                    res = subprocess.run(
                        args,
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    raw_out = res.stdout + "\n" + res.stderr
                    clean_resp = extract_clean_response(raw_out)
                    if not clean_resp:
                        clean_resp = raw_out.strip() or "Task completed without output."
                    response_text = clean_resp
                except subprocess.TimeoutExpired:
                    response_text = "Task execution timed out (60 seconds)."
                except Exception as e:
                    response_text = f"Failed to execute task: {e}"
            
            self.send_json_response({"ok": True, "output": response_text})

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

            proc = discord_processes.get(project_id)
            is_running = proc is not None and proc.poll() is None

            self.send_json_response({
                "is_running": is_running,
                "has_token": has_token,
                "channel_id": channel_id
            })

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
    load_projects_mapping()
    if not os.path.exists(DIRECTORY):
        print(f"Error: Dashboard directory not found at {DIRECTORY}", file=sys.stderr)
        sys.exit(1)
        
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"[*] Drunken AGY Inn JRPG Dashboard running at http://localhost:{PORT}/")
        print("[*] Press Ctrl+C to close the Inn.")
        
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
