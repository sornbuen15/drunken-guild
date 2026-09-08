#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
from typing import Dict, Optional, Tuple


def get_bootstrap_paths() -> Dict[str, str]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bootstrap_dir = os.path.dirname(script_dir)
    return {
        "root": bootstrap_dir,
        "skills": os.path.join(bootstrap_dir, "skills"),
        "agents": os.path.join(bootstrap_dir, "agents"),
        "bridge": os.path.join(bootstrap_dir, "scripts", "jira_bridge.py"),
    }


#: Where `--global` writes. Named here rather than inline so the two callers
#: that need it -- the resolver and its own error message -- cannot drift.
GLOBAL_TARGET = "~/.gemini/config"


def resolve_target(global_target: bool, workspace: Optional[str]) -> Tuple[str, str]:
    """Where this sync writes, from what the caller named and nothing else.

    DG-276. This used to climb: `find_workspace_root()` walked `os.getcwd()` up
    through `os.path.dirname` until some `.agents/` existed, and that directory
    became the **write** target for the synced skills and agents. With none
    found it fell back to `~/.gemini/config` silently. So where an install
    landed was decided by whichever directory the shell happened to be in --
    the discovery-by-climbing pattern DG-254 removed from config loading and
    DG-275 removed from both Jira bridges, here choosing a destination rather
    than a credential.

    There is deliberately no default. A sync that guesses is the failure; one
    that refuses costs a flag.
    """
    if global_target:
        return "global", os.path.expanduser(GLOBAL_TARGET)
    if workspace:
        return "workspace", os.path.abspath(os.path.expanduser(workspace))

    print(
        "Error: no destination named. Pass one:\n"
        f"  --global             sync to {GLOBAL_TARGET}\n"
        "  --workspace PATH     sync to PATH\n"
        "\nThere is no default on purpose: this writes skills and agents into "
        "the destination, and it used to choose one by walking up from the "
        "current directory (DG-276).",
        file=sys.stderr,
    )
    raise SystemExit(2)


def sync_dir(src: str, dst: str) -> None:  # noqa: C901  # long dispatch chain; splitting it buys nothing here
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
                # 0o700, not 0o755. These are installed into the operator's own
                # config directory and run by that one account, so group and
                # world need neither read nor execute (DG-325, bandit B103).
                os.chmod(d_item, 0o700)


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
        "--workspace",
        metavar="PATH",
        help="Sync to PATH. An explicit directory -- this never searches for one.",
    )

    args = parser.parse_args()
    bootstrap = get_bootstrap_paths()

    target_type, target_path = resolve_target(getattr(args, "global"), args.workspace)

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
