#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
from typing import Dict, Optional


def get_bootstrap_paths() -> Dict[str, str]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bootstrap_dir = os.path.dirname(script_dir)
    return {
        "root": bootstrap_dir,
        "skills": os.path.join(bootstrap_dir, "skills"),
        "agents": os.path.join(bootstrap_dir, "agents"),
        "bridge": os.path.join(bootstrap_dir, "scripts", "jira_bridge.py"),
    }


def find_workspace_root() -> Optional[str]:
    curr_dir = os.getcwd()
    while True:
        agents_dir = os.path.join(curr_dir, ".agents")
        if os.path.exists(agents_dir) and os.path.isdir(agents_dir):
            return agents_dir
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None


def sync_dir(src: str, dst: str) -> None:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    if not os.path.exists(src):
        return

    os.makedirs(dst, exist_ok=True)

    # 1. Sync skills (directories)
    src_skills = os.path.join(src, "skills")
    dst_skills = os.path.join(dst, "skills")
    if os.path.exists(src_skills):
        os.makedirs(dst_skills, exist_ok=True)
        for item in os.listdir(src_skills):
            s_item = os.path.join(src_skills, item)
            d_item = os.path.join(dst_skills, item)
            if os.path.isdir(s_item):
                if os.path.lexists(d_item):
                    print(f"[-] Updating skill: {item}")
                    if os.path.islink(d_item):
                        os.unlink(d_item)
                    elif os.path.isdir(d_item):
                        shutil.rmtree(d_item)
                    else:
                        os.remove(d_item)
                else:
                    print(f"[+] Installing skill: {item}")
                shutil.copytree(s_item, d_item, symlinks=False)
            elif os.path.isfile(s_item) and item.endswith(".md"):
                # E.g. INDEX.md
                shutil.copy2(s_item, d_item)
                print(f"[+] Syncing {item}")

    # 2. Sync agents (files or templates)
    src_agents = os.path.join(src, "agents")
    dst_agents = os.path.join(dst, "agents")
    if os.path.exists(src_agents):
        os.makedirs(dst_agents, exist_ok=True)
        for item in os.listdir(src_agents):
            s_item = os.path.join(src_agents, item)
            d_item = os.path.join(dst_agents, item)
            if os.path.isfile(s_item):
                if os.path.exists(d_item):
                    print(f"[-] Updating agent: {item}")
                else:
                    print(f"[+] Installing agent: {item}")
                shutil.copy2(s_item, d_item)

    # 3. Sync scripts
    src_scripts = os.path.join(src, "scripts")
    if os.path.exists(src_scripts):
        dst_scripts = os.path.join(dst, "scripts")
        os.makedirs(dst_scripts, exist_ok=True)
        for item in os.listdir(src_scripts):
            s_item = os.path.join(src_scripts, item)
            d_item = os.path.join(dst_scripts, item)
            if os.path.isfile(s_item) and item.endswith(".py"):
                if os.path.exists(d_item):
                    print(f"[-] Updating script: {item}")
                else:
                    print(f"[+] Installing script: {item}")
                shutil.copy2(s_item, d_item)
                os.chmod(d_item, 0o755)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Antigravity skills, agents, and bridge script."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--global",
        action="store_true",
        help="Sync to global configuration (~/.gemini/config)",
    )
    group.add_argument(
        "--workspace", action="store_true", help="Sync to local workspace (.agents)"
    )

    args = parser.parse_args()
    bootstrap = get_bootstrap_paths()

    # Resolve target destination
    target_type = None
    target_path = None

    if getattr(args, "global"):
        target_type = "global"
        target_path = os.path.expanduser("~/.gemini/config")
    elif args.workspace:
        target_type = "workspace"
        target_path = find_workspace_root()
        if not target_path:
            print(
                "Error: Local workspace (.agents) directory not found.", file=sys.stderr
            )
            sys.exit(1)
    else:
        # Auto-detect: if in a workspace, use workspace, else global
        workspace = find_workspace_root()
        if workspace:
            target_type = "workspace"
            target_path = workspace
        else:
            target_type = "global"
            target_path = os.path.expanduser("~/.gemini/config")

    print(f"[*] Target destination: {target_type.upper()} -> {target_path}")

    try:
        sync_dir(
            bootstrap["root"] if isinstance(bootstrap, dict) else bootstrap, target_path
        )
        print("[*] Sync completed successfully!")
    except Exception as e:
        print(f"Error during sync: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
