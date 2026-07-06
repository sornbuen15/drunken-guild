import json
import os
import sys
import time
import urllib.request
from typing import Any


def load_dotenv() -> None:
    curr_dir = os.getcwd()
    while True:
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
            except Exception as e:
                print(f"Warning: Failed to load .env file: {e}", file=sys.stderr)
            break
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent


def query_gemini_direct(
    prompt: str, system_instruction: str | None = None
) -> str | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        global_gemini = os.path.expanduser("~/.gemini/config/gemini_config.json")
        if os.path.exists(global_gemini):
            try:
                with open(global_gemini, "r") as f:
                    api_key = json.load(f).get("gemini_api_key")
            except Exception:
                pass
    if not api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    contents = [{"parts": [{"text": prompt}]}]
    data = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 2000,
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }
    if system_instruction:
        data["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return str(res_data["candidates"][0]["content"]["parts"][0]["text"].strip())
    except Exception as e:
        print(f"Direct API call error: {e}", file=sys.stderr)
        return None


def _parse_log_json(log_content: str) -> str | None:
    try:
        data = json.loads(log_content)
        if not isinstance(data, dict):
            return "Fallback: Invalid JSON format"
    except Exception:
        pass
    return None


def _filter_log_lines(lines: list[str]) -> list[str]:
    cleaned_lines = []
    in_thinking = False
    for line in lines:
        stripped = line.strip()
        if stripped == "<thinking>":
            in_thinking = True
            continue
        if stripped == "</thinking>":
            in_thinking = False
            continue
        if in_thinking:
            continue
        if (
            stripped.startswith("I will ")
            or stripped.startswith("I'm checking ")
            or stripped.startswith("I'm initializing ")
            or stripped.startswith("I am initializing ")
            or stripped.startswith("Executing command: ")
            or stripped.startswith("Running command: ")
            or stripped.startswith("[System]")
            or stripped.startswith("[Warning]")
            or stripped.startswith("Warning:")
            or stripped.startswith("[Info]")
        ):
            continue
        cleaned_lines.append(line)
    return cleaned_lines


def _remove_consecutive_blank_lines(lines: list[str]) -> str:
    result_lines = []
    prev_blank = False
    for line in "\n".join(lines).strip().split("\n"):
        if not line.strip():
            if not prev_blank:
                result_lines.append(line)
                prev_blank = True
        else:
            result_lines.append(line)
            prev_blank = False
    return "\n".join(result_lines).strip()


def extract_clean_response(log_content: str) -> str:
    json_err = _parse_log_json(log_content)
    if json_err:
        return json_err
    lines = log_content.split("\n")
    cleaned_lines = _filter_log_lines(lines)
    return _remove_consecutive_blank_lines(cleaned_lines)


def find_config() -> str | None:
    curr_dir = os.getcwd()
    while True:
        config_path = os.path.join(curr_dir, ".agents", "discord_config.json")
        if os.path.exists(config_path):
            return config_path
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None


def log_activity(event_type: str, author: str, content: str) -> None:
    config_file = find_config()
    project_path = (
        os.path.dirname(os.path.dirname(config_file)) if config_file else os.getcwd()
    )
    activity_file = os.path.join(project_path, ".agents", "discord_activity.jsonl")

    event = {
        "timestamp": time.time(),
        "type": event_type,
        "author": author,
        "content": content,
    }

    try:
        with open(activity_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def save_config(config: dict[str, Any]) -> None:
    config_file = find_config()
    if not config_file:
        config_file = os.path.join(os.getcwd(), ".agents", "discord_config.json")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def load_config() -> dict[str, Any]:
    config_file = find_config()
    if config_file:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return dict(json.load(f))
        except Exception:
            pass
    return {"bot_token": None, "channel_id": None}
