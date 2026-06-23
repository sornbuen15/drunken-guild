#!/usr/bin/env python3
import os
import sys
import json
import uuid
import shutil
import subprocess

DEFAULT_JIRA_URL = ""
DEFAULT_JIRA_EMAIL = ""
DEFAULT_JIRA_PROJECT = ""
DEFAULT_DISCORD_CHANNEL = ""

def get_or_create_project_id(project_path):
    projects_dir = os.path.expanduser("~/.gemini/config/projects")
    os.makedirs(projects_dir, exist_ok=True)
    abs_path = os.path.abspath(project_path)
    
    # Check if project already registered
    import glob
    for fpath in glob.glob(os.path.join(projects_dir, "*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if os.path.abspath(data.get("name", "")) == abs_path:
                    print(f"[+] Project configuration already registered in Dashboard. ID: {data.get('id')}")
                    return data.get("id")
        except Exception:
            pass
            
    # Generate new uuid and write config
    project_id = str(uuid.uuid4())
    project_file = os.path.join(projects_dir, f"{project_id}.json")
    
    reg_data = {
        "id": project_id,
        "name": abs_path,
        "projectResources": {
            "resources": [
                { "folderUri": f"file://{abs_path}" }
            ]
        }
    }
    
    with open(project_file, "w", encoding="utf-8") as f:
        json.dump(reg_data, f, indent=2)
        
    print(f"[+] Successfully registered new project on Dashboard. ID: {project_id}")
    return project_id

def main():
    print("====================================================")
    # Drunken programmer style hiccup header
    print("🍺 *hic* Drunken AGY Project Registration & Setup")
    print("====================================================")
    
    # 1. Resolve Project Path
    target_path = os.getcwd()
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        
    abs_project_path = os.path.abspath(target_path)
    if not os.path.exists(abs_project_path):
        print(f"[-] Error: Project folder path not found: {abs_project_path}, Boss.", file=sys.stderr)
        sys.exit(1)
        
    print(f"[*] Provisioning project at: {abs_project_path}")
    
    # 2. Ensure .agents directory exists
    agents_dir = os.path.join(abs_project_path, ".agents")
    if not os.path.exists(agents_dir):
        os.makedirs(agents_dir, exist_ok=True)
        print("[+] Created .agents/ workspace directory successfully.")
    else:
        print("[*] Directory .agents/ already exists.")
        
    # 3. Check and Create ANTIGRAVITY.md if missing
    antigravity_md_path = os.path.join(abs_project_path, "ANTIGRAVITY.md")
    if not os.path.exists(antigravity_md_path):
        default_antigravity_content = """# Antigravity Project Configuration

<system_prompt>
  <role>
    You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team, pairing with "The Boss" who expects clean, production-ready code.
  </role>

  <core_directives>
    <directive priority="FATAL" name="Tone & Persona">
      CRITICAL: The user is 'The Boss'. Always address the user with respect as 'The Boss'. Never address them as adventurer, traveler, or patron.
    </directive>
    <directive priority="FATAL" name="Workspace Environment">
      Always prioritize reading configuration variables from the local `.env` file. Do not commit `.env` to git.
    </directive>
  </core_directives>
</system_prompt>
"""
        with open(antigravity_md_path, "w", encoding="utf-8") as f:
            f.write(default_antigravity_content)
        print("[+] Template ANTIGRAVITY.md created successfully.")
    else:
        print("[*] File ANTIGRAVITY.md already exists.")
        
    # 4. Check for 1Password CLI
    jira_email = DEFAULT_JIRA_EMAIL
    jira_url = DEFAULT_JIRA_URL
    project_key = DEFAULT_JIRA_PROJECT
    jira_token = None
    
    op_bin = shutil.which("op")
    if op_bin:
        print("[*] Found 1Password CLI (op). Checking biometric privileges...")
        JIRA_PASS_URIS = os.environ.get("JIRA_PASS_URIS", "").split(",") if os.environ.get("JIRA_PASS_URIS") else [
            "op://Personal/Jira/credential",
            "op://Private/Jira/credential",
            "op://Personal/Jira/password",
            "op://Private/Jira/password"
        ]
        
        op_success = False
        for uri in JIRA_PASS_URIS:
            try:
                res = subprocess.run(["op", "read", uri], capture_output=True, text=True, check=True)
                fetched_token = res.stdout.strip()
                if fetched_token:
                    jira_token = fetched_token
                    op_success = True
                    print(f"[+] Successfully fetched Token from 1Password ({uri})!")
                    break
            except Exception:
                continue
        
        if not op_success:
            print("[!] Target Token not found in 1Password")
            
    # Fallback to Global agy config if no 1Password or 1Password read failed
    if not jira_token:
        print("[!] 1Password CLI not found or biometric retrieve failed")
        
        global_config_path = os.path.expanduser("~/.gemini/config/jira_config.json")
        use_global = False
        
        # Ask for consent to use global or save to global
        consent = input("[?] Store/Use JIRA credentials in agy Global Config instead? (~/.gemini/config/jira_config.json) (y/n): ").strip().lower()
        if consent in ["y", "yes"]:
            use_global = True
            
        if not use_global:
            print("[-] User declined Global Config saving and 1Password is missing. Terminating execution, Boss.", file=sys.stderr)
            sys.exit(1)
            
        # Check if global file exists
        if os.path.exists(global_config_path):
            try:
                with open(global_config_path, "r", encoding="utf-8") as f:
                    g_data = json.load(f)
                    print(f"[+] Existing Global JIRA Config details found:")
                    print(f"    URL: {g_data.get('jira_url')}")
                    print(f"    Email: {g_data.get('jira_email')}")
                    
                    confirm_use = input("[?] Use these existing configurations? (y/n): ").strip().lower()
                    if confirm_use in ["y", "yes"]:
                        jira_url = g_data.get("jira_url", jira_url)
                        jira_email = g_data.get("jira_email", jira_email)
                        jira_token = g_data.get("jira_token")
                        project_key = g_data.get("project_key", project_key)
            except Exception as e:
                print(f"[-] Failed to read global config: {e}")
                
        # Prompt user manually if still missing
        if not jira_token:
            print("[*] Please provide JIRA Credentials details to save in Global Config, Boss:")
            jira_url_input = input(f"JIRA URL (e.g. https://your-domain.atlassian.net) [{jira_url}]: ").strip()
            if jira_url_input:
                jira_url = jira_url_input
            while not jira_url:
                jira_url = input("JIRA URL (Required): ").strip()
                
            jira_email_input = input(f"JIRA Email [{jira_email}]: ").strip()
            if jira_email_input:
                jira_email = jira_email_input
            while not jira_email:
                jira_email = input("JIRA Email (Required): ").strip()
                
            project_key_input = input(f"Project Key [{project_key}]: ").strip()
            if project_key_input:
                project_key = project_key_input
            while not project_key:
                project_key = input("Project Key (Required): ").strip()
                
            # Loop until we get a token
            while not jira_token:
                jira_token = input("JIRA API Token (Secret): ").strip()
                if not jira_token:
                    print("[-] JIRA API Token is required!")
            
            # Save to global config
            try:
                g_save_data = {
                    "jira_url": jira_url,
                    "jira_email": jira_email,
                    "jira_token": jira_token,
                    "project_key": project_key
                }
                with open(global_config_path, "w", encoding="utf-8") as f:
                    json.dump(g_save_data, f, indent=2)
                print(f"[+] Global JIRA credentials saved successfully at: {global_config_path}")
            except Exception as e:
                print(f"[-] Failed to write global config: {e}")
                
    # 5. Resolve Discord Configuration
    discord_token = None
    discord_channel_id = DEFAULT_DISCORD_CHANNEL
    
    # Try reading local or central config first
    d_conf_file = os.path.join(agents_dir, "discord_config.json")
    if os.path.exists(d_conf_file):
        try:
            with open(d_conf_file, "r") as f:
                d_data = json.load(f)
                discord_token = d_data.get("bot_token")
                discord_channel_id = d_data.get("channel_id", discord_channel_id)
        except Exception:
            pass
            
    # Try backup config from drunken-agy if token not found
    if not discord_token:
        backup_d_conf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".agents", "discord_config.json")
        if os.path.exists(backup_d_conf):
            try:
                with open(backup_d_conf, "r") as f:
                    d_data = json.load(f)
                    discord_token = d_data.get("bot_token")
            except Exception:
                pass

    # Prompt for Discord Channel ID
    chan_input = input(f"[?] Enter Discord Channel ID [{discord_channel_id}]: ").strip()
    if chan_input:
        discord_channel_id = chan_input
        
    # Save Discord Bot Token to Global Config instead of local project
    global_d_conf = os.path.expanduser("~/.gemini/config/discord_config.json")
    if discord_token:
        try:
            with open(global_d_conf, "w", encoding="utf-8") as f:
                json.dump({"bot_token": discord_token}, f, indent=2)
            print(f"[+] Saved Discord Bot Token successfully in Global Config: {global_d_conf}")
        except Exception as e:
            print(f"[-] Failed to write global Discord config: {e}")

    # 6. Generate project-specific non-sensitive .env file
    env_content = f"""# ⚠️ CONFIGURATION - GENERATED BY DRUNKEN-REGISTER
# Project-specific non-sensitive configurations. SENSITIVE CREDENTIALS ARE STORED GLOBALLY.

DISCORD_CHANNEL_ID="{discord_channel_id}"
JIRA_PROJECT_KEY="{project_key}"
"""
    
    env_path = os.path.join(abs_project_path, ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content.strip() + "\n")
    print(f"[+] Generated local project configuration .env at: {env_path}")
    
    # 7. Check and update gitignore
    gitignore_path = os.path.join(abs_project_path, ".gitignore")
    ensure_gitignore = ".env"
    
    gitignore_content = ""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gitignore_content = f.read()
            
    if ensure_gitignore not in gitignore_content.splitlines():
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write(f"\n# Drunken AGY local configuration\n{ensure_gitignore}\n")
        print("[+] Added .env to .gitignore successfully (git-ignored for safety)")
    else:
        print("[*] .env is already present in .gitignore")
        
    # 8. Register in Dashboard
    get_or_create_project_id(abs_project_path)
    
    print("\n[+] Project registration completed successfully, Boss! You can now start the dashboard. 🍹🍺")

if __name__ == "__main__":
    main()

