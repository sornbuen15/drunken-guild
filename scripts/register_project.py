#!/usr/bin/env python3
import json
import os
import sys
import uuid

DEFAULT_JIRA_URL = ""
DEFAULT_JIRA_EMAIL = ""
DEFAULT_JIRA_PROJECT = ""
DEFAULT_DISCORD_CHANNEL = ""


def get_or_create_project_id(project_path: str) -> str:
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
                    print(
                        f"[+] Project configuration already registered in Dashboard. ID: {data.get('id')}"
                    )
                    return str(data.get("id"))
        except Exception:
            pass

    # Generate new uuid and write config
    project_id = str(uuid.uuid4())
    project_file = os.path.join(projects_dir, f"{project_id}.json")

    reg_data = {
        "id": project_id,
        "name": abs_path,
        "projectResources": {"resources": [{"folderUri": f"file://{abs_path}"}]},
    }

    with open(project_file, "w", encoding="utf-8") as f:
        json.dump(reg_data, f, indent=2)

    print(f"[+] Successfully registered new project on Dashboard. ID: {project_id}")
    return project_id


def main() -> None:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    print("====================================================")
    # Drunken programmer style hiccup header
    print("🍺 *hic* Drunken Team Project Registration & Setup")
    print("====================================================")

    # 1. Resolve Project Path
    target_path = os.getcwd()
    if len(sys.argv) > 1:
        target_path = sys.argv[1]

    abs_project_path = os.path.abspath(target_path)
    if not os.path.exists(abs_project_path):
        print(
            f"[-] Error: Project folder path not found: {abs_project_path}, Boss.",
            file=sys.stderr,
        )
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

    # 4. Gather JIRA Credentials (Local Isolation)
    if not jira_token:
        print("[*] Please provide JIRA Credentials details for local .env, Boss:")

        jira_url_input = input(
            f"JIRA URL (e.g. https://your-domain.atlassian.net) [{jira_url}]: "
        ).strip()
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

        while not jira_token:
            jira_token = input("JIRA API Token (Secret): ").strip()
            if not jira_token:
                print("[-] JIRA API Token is required!")

    # 5. Resolve Discord Configuration
    discord_token = None
    discord_channel_id = DEFAULT_DISCORD_CHANNEL

    # Try backup config from drunken-team if token not found
    backup_d_conf = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".agents",
        "discord_config.json",
    )
    if os.path.exists(backup_d_conf):
        try:
            with open(backup_d_conf, "r") as f:
                d_data = json.load(f)
                discord_token = d_data.get("bot_token")
        except Exception:
            pass

    if not discord_token:
        discord_token = input("Discord Bot Token (Secret): ").strip()

    chan_input = input(f"[?] Enter Discord Channel ID [{discord_channel_id}]: ").strip()
    if chan_input:
        discord_channel_id = chan_input

    # 6. Generate project-specific JSON configs
    jira_config_path = os.path.join(agents_dir, "jira.json")
    jira_data = {}
    if os.path.exists(jira_config_path):
        try:
            with open(jira_config_path, "r", encoding="utf-8") as f:
                jira_data = json.load(f)
        except Exception:
            pass
    if jira_url:
        jira_data["jira_url"] = jira_url
    if jira_email:
        jira_data["jira_email"] = jira_email
    if project_key:
        jira_data["project_key"] = project_key
    if jira_token:
        jira_data["jira_token"] = jira_token

    with open(jira_config_path, "w", encoding="utf-8") as f:
        json.dump(jira_data, f, indent=2)
    print(f"[+] Generated local project JIRA configuration at: {jira_config_path}")

    discord_config_path = os.path.join(agents_dir, "discord_config.json")
    discord_data = {}
    if os.path.exists(discord_config_path):
        try:
            with open(discord_config_path, "r", encoding="utf-8") as f:
                discord_data = json.load(f)
        except Exception:
            pass
    if discord_token:
        discord_data["bot_token"] = discord_token
    if discord_channel_id:
        discord_data["channel_id"] = discord_channel_id

    with open(discord_config_path, "w", encoding="utf-8") as f:
        json.dump(discord_data, f, indent=2)
    print(
        f"[+] Generated local project Discord configuration at: {discord_config_path}"
    )

    # 8. Register in Dashboard
    get_or_create_project_id(abs_project_path)

    print(
        "\n[+] Project registration completed successfully, Boss! You can now start the dashboard. 🍹🍺"
    )


if __name__ == "__main__":
    main()
