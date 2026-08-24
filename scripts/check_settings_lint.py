#!/usr/bin/env python3
import json
import re
import sys


def check_settings(filepath: str) -> int:
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return 0
    except json.JSONDecodeError:
        print(f"Error parsing {filepath}")
        return 1

    allow_rules = data.get("permissions", {}).get("allow", [])
    errors = 0
    # Match bare Tool(*) e.g. Bash(*), Read(*), etc.
    # The requirement is "rejecting bare Tool(*) rules."
    pattern = re.compile(r"^[a-zA-Z0-9_]+\(\*\)$")
    for rule in allow_rules:
        if pattern.match(rule):
            print(f"Error: {filepath} contains bare wildcard rule: {rule}")
            errors += 1
    return errors


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    args = parser.parse_args()

    exit_code = 0
    if not args.filenames:
        filenames = [".claude/settings.json"]
    else:
        filenames = args.filenames

    for filename in filenames:
        if filename.endswith("settings.json"):
            if check_settings(filename) > 0:
                exit_code = 1
    sys.exit(exit_code)
