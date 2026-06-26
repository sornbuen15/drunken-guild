#!/usr/bin/env python3
import os
import sys
import json
import subprocess

def find_config(filename):
    curr_dir = os.getcwd()
    while True:
        path = os.path.join(curr_dir, '.agents', filename)
        if os.path.exists(path):
            return path
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None

def main():
    print("====================================================")
    print("🔑 Drunken Team Inn Environment Setup & Biometric Auth")
    print("====================================================")
    print("[*] Boss, I am performing Biometric authentication via 1Password CLI...")
    print("[*] ...to unlock and fetch the required credentials to compile your local .env")
    print("----------------------------------------------------")
    
    # Load config template details (defaults to empty/generic)
    jira_email = ""
    jira_url = ""
    project_key = ""
    discord_channel_id = ""
    jira_token = None
    discord_token = None
    gemini_api_key = os.environ.get("GEMINI_API_KEY") or ""
    
    # Try reading existing local configs to preserve details
    jira_conf_file = find_config("jira_config.json")
    if jira_conf_file:
        try:
            with open(jira_conf_file, "r") as f:
                data = json.load(f)
                project_key = data.get("project_key", project_key)
                jira_url = data.get("jira_url", jira_url)
                jira_email = data.get("jira_email", jira_email)
                jira_token = data.get("jira_token") or data.get("token")
        except Exception:
            pass
            
    discord_conf_file = find_config("discord_config.json")
    if discord_conf_file:
        try:
            with open(discord_conf_file, "r") as f:
                data = json.load(f)
                discord_channel_id = data.get("channel_id", discord_channel_id)
                discord_token = data.get("bot_token") or data.get("token")
        except Exception:
            pass

    # Try reading from global configurations
    global_jira = os.path.expanduser("~/.gemini/config/jira_config.json")
    if os.path.exists(global_jira):
        try:
            with open(global_jira, "r") as f:
                g_data = json.load(f)
                jira_url = jira_url or g_data.get("jira_url")
                jira_email = jira_email or g_data.get("jira_email")
                project_key = project_key or g_data.get("project_key")
                jira_token = jira_token or g_data.get("jira_token") or g_data.get("token")
        except Exception:
            pass

    global_discord = os.path.expanduser("~/.gemini/config/discord_config.json")
    if os.path.exists(global_discord):
        try:
            with open(global_discord, "r") as f:
                g_data = json.load(f)
                discord_channel_id = discord_channel_id or g_data.get("channel_id")
                discord_token = discord_token or g_data.get("bot_token") or g_data.get("token")
        except Exception:
            pass

    # Prompt interactive inputs if still missing
    if not jira_url:
        jira_url = input("[?] Enter JIRA URL (e.g. https://your-domain.atlassian.net): ").strip()
    if not jira_email:
        jira_email = input("[?] Enter JIRA Email: ").strip()
    if not project_key:
        project_key = input("[?] Enter JIRA Project Key: ").strip()
    if not discord_channel_id:
        discord_channel_id = input("[?] Enter Discord Channel ID: ").strip()

    # Always attempt to pull from 1Password CLI as biometric check
    print("[*] Verifying biometric authentication (Touch ID / Passkey) via 1Password...")
    # Target the correct reference format: op://Personal/Jira/credential
    JIRA_PASS_URIS = os.environ.get("JIRA_PASS_URIS", "").split(",") if os.environ.get("JIRA_PASS_URIS") else [
        "op://Personal/Jira/credential",
        "op://Private/Jira/credential",
        "op://Personal/Jira/password",
        "op://Private/Jira/password"
    ]
    
    op_success = False
    for uri in JIRA_PASS_URIS:
        try:
            print(f"[*] Trying to fetch: {uri} (Scan fingerprint if prompted)...")
            res = subprocess.run(["op", "read", uri], capture_output=True, text=True, check=True)
            fetched_token = res.stdout.strip()
            if fetched_token:
                jira_token = fetched_token
                op_success = True
                print(f"[+] Successfully fetched Jira Token from 1Password ({uri})!")
                
                # Cache the token directly to the global config!
                global_config_path = os.path.expanduser("~/.gemini/config/jira_config.json")
                try:
                    os.makedirs(os.path.dirname(global_config_path), exist_ok=True)
                    existing_data = {}
                    if os.path.exists(global_config_path):
                        with open(global_config_path, "r") as f:
                            existing_data = json.load(f)
                    existing_data["jira_token"] = jira_token
                    with open(global_config_path, "w") as f:
                        json.dump(existing_data, f, indent=2)
                    print("[+] Saved 1Password token to Global Config automatically.")
                except Exception as e:
                    print(f"Warning: Could not save to global config: {e}")
                    
                break
        except Exception:
            continue

    if not op_success:
        if jira_token:
            print("[!] Failed to communicate with 1Password CLI. Falling back to the existing JIRA token from local config.")
        else:
            print("[-] Error: Failed biometric check and no token found in 1Password or local config, Boss.", file=sys.stderr)
            sys.exit(1)
            
    # Write to .env
    env_content = f"""# ⚠️ PRIVATE CREDENTIALS - GENERATED BY SETUP UTILITY
# DO NOT COMMIT THIS FILE TO GIT

GEMINI_API_KEY="{gemini_api_key}"
DISCORD_BOT_TOKEN="{discord_token}"
DISCORD_CHANNEL_ID="{discord_channel_id}"
JIRA_EMAIL="{jira_email}"
JIRA_TOKEN="{jira_token}"
JIRA_URL="{jira_url}"
JIRA_PROJECT_KEY="{project_key}"
"""
    
    env_path = os.path.join(os.getcwd(), ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content.strip() + "\n")
    print("[+] Local environment file .env compiled successfully at:", env_path)
    
    # Check and update .gitignore
    gitignore_path = os.path.join(os.getcwd(), ".gitignore")
    ensure_gitignore = ".env"
    
    gitignore_content = ""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gitignore_content = f.read()
            
    if ensure_gitignore not in gitignore_content.splitlines():
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write(f"\n# Drunken Team local credentials\n{ensure_gitignore}\n")
        print("[+] Added .env to .gitignore successfully (git-ignored for safety)")
    else:
        print("[*] .env is already present in .gitignore")
        
    print("[+] Setup complete! AGY services will now load parameters directly from the local .env file, Boss!")

if __name__ == "__main__":
    main()
