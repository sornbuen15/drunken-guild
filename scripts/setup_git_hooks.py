#!/usr/bin/env python3
"""
Setup utility for Drunken Team local Git hooks.
Installs a pre-push hook to prevent accidental direct pushes to protected branches.
"""

import os
import stat
import sys

HOOK_CONTENT = """#!/usr/bin/env python3
import sys

# Drunken Team Git Pre-Push Hook
# Prevents direct pushes to protected branches (main, develop)

PROTECTED_REFS = {"refs/heads/main", "refs/heads/develop"}

lines = sys.stdin.read().splitlines()
for line in lines:
    parts = line.split()
    if len(parts) < 4:
        continue
    local_ref, local_sha, remote_ref, remote_sha = parts[:4]

    # If remote branch being updated is main or develop, abort the push
    if remote_ref in PROTECTED_REFS:
        branch_name = remote_ref.split('/')[-1]
        print(f"\\n[Drunken Team Hook] 🛑 ERROR: Direct push to protected branch '{branch_name}' is prohibited!")
        print("Please follow the standard Git workflow:")
        print("  1. Create a feature branch off 'develop'")
        print("  2. Push your feature branch to remote")
        print("  3. Open a Pull Request (PR) using GitHub CLI 'gh pr create' or online")
        print("  4. Merge the PR after approval and CI verification.")
        print("\\nRefer to CONTRIBUTING.md for details.")
        print("If you are an admin and must bypass this check, append '--no-verify' to git push.\\n")
        sys.exit(1)

sys.exit(0)
"""


def main() -> None:
    git_dir = os.path.join(os.getcwd(), ".git")
    if not os.path.isdir(git_dir):
        print(
            "[-] Error: Not a git repository or not in the project root directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    pre_push_path = os.path.join(hooks_dir, "pre-push")

    # Write hook file
    try:
        with open(pre_push_path, "w", encoding="utf-8") as f:
            f.write(HOOK_CONTENT)

        # Make the hook executable
        st = os.stat(pre_push_path)
        os.chmod(pre_push_path, st.st_mode | stat.S_IEXEC)
        print(f"[+] Local Git pre-push hook installed successfully at: {pre_push_path}")
        print("[+] Direct pushes to 'main' and 'develop' will now be blocked locally.")
    except Exception as e:
        print(f"[-] Failed to install git hook: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
