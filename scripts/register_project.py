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
                    print(f"[+] พบคอนฟิกโครงการในแดชบอร์ดอยู่แล้ว ID: {data.get('id')}")
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
        
    print(f"[+] ลงทะเบียนโครงการใหม่บน Dashboard สำเร็จ ID: {project_id}")
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
        print(f"[-] ข้อผิดพลาด: ไม่พบตำแหน่งโฟลเดอร์ {abs_project_path} ครับบอส", file=sys.stderr)
        sys.exit(1)
        
    print(f"[*] กำลังจัดเตรียมโครงการที่: {abs_project_path}")
    
    # 2. Ensure .agents directory exists
    agents_dir = os.path.join(abs_project_path, ".agents")
    if not os.path.exists(agents_dir):
        os.makedirs(agents_dir, exist_ok=True)
        print("[+] สร้างโฟลเดอร์ .agents/ เรียบร้อย")
    else:
        print("[*] มีโฟลเดอร์ .agents/ อยู่แล้ว")
        
    # 3. Check and Create ANTIGRAVITY.md if missing
    antigravity_md_path = os.path.join(abs_project_path, "ANTIGRAVITY.md")
    if not os.path.exists(antigravity_md_path):
        default_antigravity_content = """# Antigravity Project Configuration

<system_prompt>
  <role>
    You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team, pairing with "The Boss" (บอส / นายท่าน / Boss) who expects clean, production-ready code.
  </role>

  <core_directives>
    <directive priority="FATAL" name="Tone & Persona">
      CRITICAL: The user is 'The Boss' (บอส / นายท่าน / Boss). Always address the user with respect as 'The Boss' or 'นายท่าน'. Never address them as adventurer, traveler, or patron.
    </directive>
    <directive priority="FATAL" name="Workspace Environment">
      Always prioritize reading configuration variables from the local `.env` file. Do not commit `.env` to git.
    </directive>
  </core_directives>
</system_prompt>
"""
        with open(antigravity_md_path, "w", encoding="utf-8") as f:
            f.write(default_antigravity_content)
        print("[+] สร้างไฟล์เทมเพลต ANTIGRAVITY.md เรียบร้อย")
    else:
        print("[*] มีไฟล์ ANTIGRAVITY.md อยู่แล้ว")
        
    # 4. Check for 1Password CLI
    jira_email = DEFAULT_JIRA_EMAIL
    jira_url = DEFAULT_JIRA_URL
    project_key = DEFAULT_JIRA_PROJECT
    jira_token = None
    
    op_bin = shutil.which("op")
    if op_bin:
        print("[*] พบ 1Password CLI (op) ในระบบ กำลังตรวจสอบสิทธิ์ Biometric...")
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
                    print(f"[+] ดึง Token จาก 1Password ({uri}) สำเร็จ!")
                    break
            except Exception:
                continue
        
        if not op_success:
            print("[!] ไม่พบ Token ที่ต้องการใน 1Password")
            
    # Fallback to Global agy config if no 1Password or 1Password read failed
    if not jira_token:
        print("[!] ไม่พบ 1Password CLI หรือดึงข้อมูลล้มเหลว")
        
        global_config_path = os.path.expanduser("~/.gemini/config/jira_config.json")
        use_global = False
        
        # Ask for consent to use global or save to global
        consent = input("[?] ต้องการจัดเก็บ/ใช้งานข้อมูล JIRA ใน Global Config ของ agy แทนหรือไม่? (~/.gemini/config/jira_config.json) (y/n): ").strip().lower()
        if consent in ["y", "yes"]:
            use_global = True
            
        if not use_global:
            print("[-] ผู้ใช้ปฏิเสธการเซฟใน Global Config และไม่มี 1Password. ยุติการทำงานครับบอส", file=sys.stderr)
            sys.exit(1)
            
        # Check if global file exists
        if os.path.exists(global_config_path):
            try:
                with open(global_config_path, "r", encoding="utf-8") as f:
                    g_data = json.load(f)
                    print(f"[+] พบค่าคอนฟิกเดิมใน Global JIRA Config:")
                    print(f"    URL: {g_data.get('jira_url')}")
                    print(f"    Email: {g_data.get('jira_email')}")
                    
                    confirm_use = input("[?] ต้องการใช้ข้อมูลที่พบนี้เลยหรือไม่? (y/n): ").strip().lower()
                    if confirm_use in ["y", "yes"]:
                        jira_url = g_data.get("jira_url", jira_url)
                        jira_email = g_data.get("jira_email", jira_email)
                        jira_token = g_data.get("jira_token")
                        project_key = g_data.get("project_key", project_key)
            except Exception as e:
                print(f"[-] ไม่สามารถอ่าน Global Config เก่าได้: {e}")
                
        # Prompt user manually if still missing
        if not jira_token:
            print("[*] กรุณาระบุรายละเอียด JIRA Credentials ด้านล่างนี้เพื่อบันทึกลง Global Config ค่ะบอส:")
            jira_url_input = input(f"JIRA URL (เช่น https://your-domain.atlassian.net) [{jira_url}]: ").strip()
            if jira_url_input:
                jira_url = jira_url_input
            while not jira_url:
                jira_url = input("JIRA URL (จำเป็น): ").strip()
                
            jira_email_input = input(f"JIRA Email [{jira_email}]: ").strip()
            if jira_email_input:
                jira_email = jira_email_input
            while not jira_email:
                jira_email = input("JIRA Email (จำเป็น): ").strip()
                
            project_key_input = input(f"Project Key [{project_key}]: ").strip()
            if project_key_input:
                project_key = project_key_input
            while not project_key:
                project_key = input("Project Key (จำเป็น): ").strip()
                
            # Loop until we get a token
            while not jira_token:
                jira_token = input("JIRA API Token (Secret): ").strip()
                if not jira_token:
                    print("[-] จำเป็นต้องใช้ API Token ค่ะ!")
            
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
                print(f"[+] บันทึกประวัติลง Global Config เรียบร้อยที่: {global_config_path}")
            except Exception as e:
                print(f"[-] ไม่สามารถเขียนไฟล์ Global Config ได้: {e}")
                
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
    chan_input = input(f"[?] ระบุหมายเลขห้อง Discord Channel ID [{discord_channel_id}]: ").strip()
    if chan_input:
        discord_channel_id = chan_input
        
    # Save Discord Bot Token to Global Config instead of local project
    global_d_conf = os.path.expanduser("~/.gemini/config/discord_config.json")
    if discord_token:
        try:
            with open(global_d_conf, "w", encoding="utf-8") as f:
                json.dump({"bot_token": discord_token}, f, indent=2)
            print(f"[+] บันทึก Discord Bot Token สำเร็จที่ Global Config: {global_d_conf}")
        except Exception as e:
            print(f"[-] ไม่สามารถเขียนไฟล์ Global Discord Config ได้: {e}")

    # 6. Generate project-specific non-sensitive .env file
    env_content = f"""# ⚠️ CONFIGURATION - GENERATED BY DRUNKEN-REGISTER
# Project-specific non-sensitive configurations. SENSITIVE CREDENTIALS ARE STORED GLOBALLY.

DISCORD_CHANNEL_ID="{discord_channel_id}"
JIRA_PROJECT_KEY="{project_key}"
"""
    
    env_path = os.path.join(abs_project_path, ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content.strip() + "\n")
    print(f"[+] สร้างไฟล์คอนฟิก .env ท้องถิ่นเรียบร้อยที่: {env_path}")
    
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
        print("[+] เพิ่ม .env เข้าสู่ .gitignore เรียบร้อย (ปลอดภัย)")
    else:
        print("[*] มี .env ใน .gitignore อยู่แล้ว")
        
    # 8. Register in Dashboard
    get_or_create_project_id(abs_project_path)
    
    print("\n[+] เสร็จสิ้นการลงทะเบียนโครงการด่วนค่ะนายท่าน! บอสสามารถรันคำสั่งแดชบอร์ดต่อได้เลยนะคะ 🍹🍺")

if __name__ == "__main__":
    main()

