#!/usr/bin/env python3
import json
import os
import subprocess
import sys

LOCAL_SETTINGS = ".claude/settings.local.json"
TRACKED_SETTINGS = ".claude/settings.json"


def main() -> int:
    if not os.path.exists(LOCAL_SETTINGS):
        print("No local permissions to promote.")
        return 0

    try:
        with open(LOCAL_SETTINGS, "r") as f:
            local_data = json.load(f)
    except json.JSONDecodeError:
        print("Error reading local settings.")
        return 1

    local_allow = local_data.get("permissions", {}).get("allow", [])
    if not local_allow:
        print("No local allow rules to promote.")
        return 0

    try:
        with open(TRACKED_SETTINGS, "r") as f:
            tracked_data = json.load(f)
    except FileNotFoundError:
        tracked_data = {}

    if "permissions" not in tracked_data:
        tracked_data["permissions"] = {}
    if "allow" not in tracked_data["permissions"]:
        tracked_data["permissions"]["allow"] = []

    tracked_allow = set(tracked_data["permissions"]["allow"])
    added = 0
    for rule in local_allow:
        if rule not in tracked_allow:
            tracked_data["permissions"]["allow"].append(rule)
            added += 1

    if added == 0:
        print("All local rules are already in tracked settings.")
        return 0

    with open(TRACKED_SETTINGS, "w") as f:
        json.dump(tracked_data, f, indent=2)
        f.write("\n")

    # Empty out local settings since they are promoted
    local_data["permissions"]["allow"] = []
    with open(LOCAL_SETTINGS, "w") as f:
        json.dump(local_data, f, indent=2)
        f.write("\n")

    print(f"Promoted {added} rules to tracked settings. Please review the diff:")
    subprocess.run(["git", "diff", TRACKED_SETTINGS])
    return 0


if __name__ == "__main__":
    sys.exit(main())
