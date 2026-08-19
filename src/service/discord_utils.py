import json
import os
import sys
import time
import urllib.request
from typing import TYPE_CHECKING, Any

from core.http import open_url

if TYPE_CHECKING:
    from core.registry import ProjectConfig


def packaged_script(name: str) -> str:
    """Absolute path to a helper that ships inside the ``scripts`` package.

    The counterpart to the rule in :mod:`core.paths`, and the other half of it:
    *state* must never be located relative to the code, but *packaged code*
    must be — that is what makes it move correctly when installed. `scripts` is
    a declared package, so this resolves inside the virtualenv under
    ``uv tool install`` and inside the checkout when run from one, which is
    right in both cases.

    Neither `os.getcwd()` nor a walk up from ``__file__`` does that: the first
    depends on where the daemon happened to be launched, the second on the
    source layout surviving installation.
    """
    import scripts

    package_dir = os.path.dirname(os.path.abspath(scripts.__file__))
    return os.path.join(package_dir, name)


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
        with open_url(req, timeout=10) as response:
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


def _discord_project() -> "ProjectConfig | None":
    """The registered project this daemon acts for, or ``None``.

    One traversal, shared by the credential lookup and the ``.agents/`` lookup,
    so the two cannot disagree — reading a channel id out of one project while
    writing activity into another's directory is the kind of split nobody
    notices until the logs are needed.

    There is one Discord identity, not one per project (the multi-tenant daemon
    was cut), so the first registered project declaring a channel wins.

    Never raises: an absent registry is a first run before ``drunken-init``, and
    the daemon must not die on the way up (principle 8).
    """
    try:
        from core.registry import ProjectRegistry, parse_project

        for project_id, entry in ProjectRegistry().get_projects().items():
            if not isinstance(entry, dict) or "discord" not in entry:
                continue
            config = parse_project(project_id, entry)
            if config.discord and config.discord.channel_id:
                return config
    except Exception as exc:
        print(
            f"[config] Registry unreadable ({exc}); using the environment.",
            file=sys.stderr,
        )
    return None


def project_root() -> str:
    """The directory whose ``.agents/`` this daemon reads and writes.

    The registry answers this, or the working directory does. What it must
    never do is *climb*: DT-254. The previous version walked up from
    ``DRUNKEN_WORKSPACE`` or the cwd until something matched, which meant that
    running the daemon from anywhere under ``$HOME`` could adopt an unrelated
    project's ``.agents/`` — or, for ``.env``, an unrelated project's
    credentials, which then outranked the registry that had resolved correctly.

    Falling back to the cwd is bounded and visible: it creates ``.agents/``
    where you are standing, rather than silently binding to a stranger's.
    """
    config = _discord_project()
    if config and config.path and os.path.isdir(config.path):
        return config.path
    return os.getcwd()


def find_config() -> str | None:
    """Path to this project's ``discord_config.json``, if it has one.

    ``.agents/`` belongs to the project it is in. Locating one by climbing until
    something matches is the same defect as the ``.env`` walk wearing different
    clothes, so this resolves exactly one candidate and reports its absence
    rather than searching upward for a substitute.
    """
    config_path = os.path.join(project_root(), ".agents", "discord_config.json")
    return config_path if os.path.exists(config_path) else None


def log_activity(event_type: str, author: str, content: str) -> None:
    activity_file = os.path.join(project_root(), ".agents", "discord_activity.jsonl")

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
        config_file = os.path.join(project_root(), ".agents", "discord_config.json")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def load_config() -> dict[str, Any]:
    """The daemon's Discord identity, and the order that decides it.

    Precedence, per field, highest first — DT-254 made this a decision rather
    than an accident:

    1. **An environment variable**, read directly from the process environment.
       Explicit and named: it is how a container passes a different bot in
       without rewriting the registry, and the operator setting it can see that
       they did.
    2. **The registry**, resolved through :mod:`core.secrets`. The supported
       path since DT-247, and the only one ``drunken-doctor`` can verify.
    3. **This project's own** ``.agents/discord_config.json``.

    Per field, not both-or-neither: a file holding a stale ``bot_token`` must
    not shadow a freshly set ``DISCORD_BOT_TOKEN`` merely because
    ``DISCORD_CHANNEL_ID`` was not also set. (``dict.setdefault`` gets this
    wrong — it only fills keys the file omits entirely.)

    What is **not** in the list, and used to sit above all three: a ``.env``
    discovered by walking up the directory tree. It was loaded into
    ``os.environ`` first, so it arrived disguised as rule 1 and outranked the
    registry — from any working directory under ``$HOME``, a stranger's
    credential could win. That is the mechanism a dead token in ALPHA's ``.env``
    used to answer Jira with an empty board for months, and it is invisible
    precisely because it fails as success: HTTP 200 with an empty list (S4).

    A ``.env`` is now a thing an operator sources deliberately before starting
    the daemon, which makes it rule 1 and leaves it visible.
    """
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")

    file_config: dict[str, Any] = {}
    config_file = find_config()
    if config_file:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                file_config = dict(json.load(f))
        except Exception:
            file_config = {}

    registry_config = _discord_from_registry()

    return {
        "bot_token": bot_token
        or registry_config.get("bot_token")
        or file_config.get("bot_token"),
        "channel_id": channel_id
        or registry_config.get("channel_id")
        or file_config.get("channel_id"),
    }


def _discord_from_registry() -> dict[str, Any]:
    """Discord credentials from the registry, or nothing.

    Jira moved to the registry in DT-246; Discord staying behind meant
    ``drunken-init`` wrote a ``discord.channel_id`` that nothing ever read, and
    ``drunken-doctor`` reported two projects as having no channel while a single
    channel was in fact serving all three.

    Which project is consulted is :func:`_discord_project`'s decision, shared
    with :func:`project_root` so credentials and ``.agents/`` always come from
    the same place.

    Never raises. A credential reference that no longer resolves is a bad
    configuration, not a reason for the daemon to die on the way up
    (principle 8); it falls through to the environment, and ``drunken-doctor``
    is what says so out loud.
    """
    config = _discord_project()
    if config is None or config.discord is None:
        return {}

    resolved: dict[str, Any] = {"channel_id": config.discord.channel_id}
    if config.discord.credential:
        try:
            from core import secrets

            resolved["bot_token"] = secrets.resolve(config.discord.credential).reveal()
        except Exception as exc:
            print(
                f"[config] Discord credential for {config.project_id!r} did not "
                f"resolve ({exc}); falling back to the environment.",
                file=sys.stderr,
            )
    return resolved
