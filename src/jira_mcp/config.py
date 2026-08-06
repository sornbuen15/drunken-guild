import json
import os
import sys
from typing import Dict


def _load_env_file(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
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
    except Exception as e:
        print(f"Warning: Failed to load {path}: {e}", file=sys.stderr)


def load_dotenv() -> None:
    # Look for .env in the workspace or current directory.
    curr_dir = os.environ.get("DRUNKEN_WORKSPACE", os.getcwd())
    if not os.path.isdir(curr_dir):
        print(
            f"Warning: Workspace {curr_dir} is not a valid directory.", file=sys.stderr
        )
        curr_dir = os.getcwd()

    while True:
        dotenv_path = os.path.join(curr_dir, ".env")
        if os.path.exists(dotenv_path):
            _load_env_file(dotenv_path)
            return
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent


def get_jira_config() -> Dict[str, str]:
    load_dotenv()

    jira_config = {
        "jira_url": os.environ.get("JIRA_URL", ""),
        "jira_email": os.environ.get("JIRA_EMAIL", ""),
        "project_key": os.environ.get("JIRA_PROJECT_KEY", ""),
        "jira_token": os.environ.get("JIRA_TOKEN", "")
        or os.environ.get("JIRA_API_TOKEN", ""),
    }

    # Fallback to local and global JSON configs if env variables are missing
    curr_dir = os.environ.get("DRUNKEN_WORKSPACE", os.getcwd())
    if not os.path.isdir(curr_dir):
        curr_dir = os.getcwd()

    local_jira = os.path.join(curr_dir, ".agents", "jira.json")
    if os.path.exists(local_jira):
        try:
            with open(local_jira, "r") as f:
                l_data = json.load(f)
                jira_config["project_key"] = jira_config["project_key"] or l_data.get(
                    "project_key", ""
                )
                jira_config["jira_url"] = jira_config["jira_url"] or l_data.get(
                    "jira_url", ""
                )
                jira_config["jira_email"] = jira_config["jira_email"] or l_data.get(
                    "jira_email", ""
                )
        except Exception:
            pass

    global_jira = os.path.expanduser("~/.gemini/config/jira_config.json")
    if os.path.exists(global_jira):
        try:
            with open(global_jira, "r") as f:
                g_data = json.load(f)
                jira_config["jira_url"] = jira_config["jira_url"] or g_data.get(
                    "jira_url", ""
                )
                jira_config["jira_email"] = jira_config["jira_email"] or g_data.get(
                    "jira_email", ""
                )
                jira_config["project_key"] = jira_config["project_key"] or g_data.get(
                    "project_key", ""
                )
                if not jira_config["jira_token"]:
                    jira_config["jira_token"] = g_data.get("jira_token") or g_data.get(
                        "token", ""
                    )
        except Exception:
            pass

    if not jira_config.get("jira_token"):
        print("Error: Jira token not found in environment or configs.", file=sys.stderr)

    return jira_config
