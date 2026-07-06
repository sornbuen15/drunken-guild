#!/usr/bin/env python3
import json
import os
import sys
from typing import Optional


def load_dotenv() -> None:
    curr_dir = os.getcwd()
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
        except Exception:
            pass


load_dotenv()


def find_config(filename: str) -> Optional[str]:
    curr_dir = os.getcwd()
    while True:
        path = os.path.join(curr_dir, ".agents", filename)
        if os.path.exists(path):
            return path
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None


def main() -> None:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    print("====================================================")
    print("🔑 Drunken Team Inn Environment Setup")
    print("====================================================")
    print("[*] Boss, I am fetching the required credentials to compile your local .env")
    print("----------------------------------------------------")

    # Load config template details (defaults to empty/generic)
    jira_email = os.environ.get("JIRA_EMAIL") or ""
    jira_url = os.environ.get("JIRA_URL") or ""
    project_key = os.environ.get("JIRA_PROJECT_KEY") or ""
    discord_channel_id = os.environ.get("DISCORD_CHANNEL_ID") or ""
    jira_token = os.environ.get("JIRA_TOKEN") or None
    discord_token = os.environ.get("DISCORD_BOT_TOKEN") or None
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
                jira_token = (
                    jira_token or g_data.get("jira_token") or g_data.get("token")
                )
        except Exception:
            pass

    global_discord = os.path.expanduser("~/.gemini/config/discord_config.json")
    if os.path.exists(global_discord):
        try:
            with open(global_discord, "r") as f:
                g_data = json.load(f)
                discord_channel_id = discord_channel_id or g_data.get("channel_id")
                discord_token = (
                    discord_token or g_data.get("bot_token") or g_data.get("token")
                )
        except Exception:
            pass

    # Prompt interactive inputs if still missing
    if not jira_url:
        jira_url = input(
            "[?] Enter JIRA URL (e.g. https://your-domain.atlassian.net): "
        ).strip()
    if not jira_email:
        jira_email = input("[?] Enter JIRA Email: ").strip()
    if not project_key:
        project_key = input("[?] Enter JIRA Project Key: ").strip()
    if not discord_channel_id:
        discord_channel_id = input("[?] Enter Discord Channel ID: ").strip()

    if not jira_token:
        jira_token = input("[?] Enter JIRA API Token: ").strip()
        if not jira_token:
            print("[-] Error: No JIRA token provided.", file=sys.stderr)
            sys.exit(1)

    if not discord_token:
        discord_token = input("[?] Enter Discord Bot Token: ").strip()
        if not discord_token:
            print(
                "[-] Warning: No Discord Bot token provided. Discord integration may fail.",
                file=sys.stderr,
            )

    if not gemini_api_key:
        print("[!] GEMINI_API_KEY is required to bypass Keychain/1Password.")
        gemini_api_key = input("[?] Enter GEMINI API KEY (AI Studio): ").strip()
        if not gemini_api_key:
            print("[-] Error: No GEMINI API KEY provided.", file=sys.stderr)
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

    print(
        "[+] Setup complete! AGY services will now load parameters directly from the local .env file, Boss!"
    )


if __name__ == "__main__":
    main()
