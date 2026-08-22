#!/usr/bin/env python3
"""
Setup utility for the drunken-guild approval daemon (`discord_listener.py`)
as a macOS launchd LaunchAgent: starts at login, restarts on crash, keeps
running independent of any particular terminal/CLI session.

This is local-machine-only persistence — if the Mac is off or asleep,
approvals won't reach Discord. Moving the daemon to a VPS is a separate,
later step.

Usage:
    python scripts/setup_daemon_service.py install
    python scripts/setup_daemon_service.py uninstall
    python scripts/setup_daemon_service.py status
"""

import os
import shutil
import subprocess
import sys

LABEL = "com.drunkenteam.daemon"
#: What the label was before DG-244 retired the old product name. Kept only so
#: install() can unload and delete it: launchd keys on the label, so writing
#: the new plist without removing the old one leaves two definitions
#: registered, and the old one keeps restarting a stale daemon under KeepAlive.
LEGACY_LABEL = "com.drunkenteam.agy-daemon"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_PATH = os.path.join(REPO_ROOT, ".agents", "discord_listener.log")
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
LEGACY_PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LEGACY_LABEL}.plist")

# launchd resolves ProgramArguments[0] using its own minimal default PATH
# (/usr/bin:/bin:/usr/sbin:/sbin), NOT the EnvironmentVariables dict below —
# that dict only applies to the spawned process's own environment. A bare
# "uv" here silently fails with exit 78 (EX_CONFIG) because launchd can
# never find it. Must be an absolute path.
_UV_FALLBACK_CANDIDATES = [
    "/opt/homebrew/bin/uv",  # Homebrew, Apple Silicon
    "/usr/local/bin/uv",  # Homebrew, Intel
    os.path.expanduser("~/.local/bin/uv"),  # official curl installer
    os.path.expanduser("~/.cargo/bin/uv"),  # cargo install
]


def _resolve_uv_path() -> str:
    found = shutil.which("uv")
    if found:
        return found
    for candidate in _UV_FALLBACK_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    # Nothing found — fall back to the most common default so `install`
    # still produces a plist; `status` will surface exit 78 if this guess
    # is wrong, at which point re-running `install` after fixing PATH picks
    # up the right path.
    return _UV_FALLBACK_CANDIDATES[0]


UV_PATH = _resolve_uv_path()

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv_path}</string>
        <string>run</string>
        <string>python</string>
        <string>src/service/discord_listener.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{repo_root}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def _plist_content() -> str:
    return PLIST_TEMPLATE.format(
        label=LABEL, uv_path=UV_PATH, repo_root=REPO_ROOT, log_path=LOG_PATH
    )


def _remove_legacy_agent() -> None:
    """Unload and delete the pre-DG-244 agent, if one is still installed.

    Without this, upgrading leaves two launch agents pointing at the same
    daemon. Both have KeepAlive, so the old one keeps resurrecting a second
    process that binds — or fails to bind — the same socket.
    """
    if not os.path.exists(LEGACY_PLIST_PATH):
        return
    subprocess.run(["launchctl", "unload", LEGACY_PLIST_PATH], capture_output=True)
    os.remove(LEGACY_PLIST_PATH)
    print(f"[+] Removed the previous agent, {LEGACY_LABEL}")


def install() -> None:
    if sys.platform != "darwin":
        print(
            "[-] This script only supports macOS launchd. "
            "Set up the equivalent for your platform (systemd, etc.) manually.",
            file=sys.stderr,
        )
        sys.exit(1)

    _remove_legacy_agent()

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)

    with open(PLIST_PATH, "w", encoding="utf-8") as f:
        f.write(_plist_content())
    print(f"[+] Wrote {PLIST_PATH}")

    subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
    result = subprocess.run(
        ["launchctl", "load", "-w", PLIST_PATH], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[-] Failed to load launch agent: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Loaded {LABEL} — it will now start at login and restart if it crashes.")
    print(f"[+] Logs: {LOG_PATH}")
    print(
        "[+] Check status any time with: python scripts/setup_daemon_service.py status"
    )


def uninstall() -> None:
    _remove_legacy_agent()
    subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
    if os.path.exists(PLIST_PATH):
        os.remove(PLIST_PATH)
        print(f"[+] Removed {PLIST_PATH}")
    else:
        print("[+] Nothing installed.")


def status() -> None:
    result = subprocess.run(
        ["launchctl", "list", LABEL], capture_output=True, text=True
    )
    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"[-] {LABEL} is not currently loaded.")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("install", "uninstall", "status"):
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    if action == "install":
        install()
    elif action == "uninstall":
        uninstall()
    else:
        status()


if __name__ == "__main__":
    main()
