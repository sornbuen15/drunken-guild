#!/usr/bin/env python3
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


def load_dotenv() -> None:
    # Look for .env in current directory or parent directories
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


# Automatically load local .env variables at startup
load_dotenv()


def get_jira_token() -> Optional[str]:
    return os.environ.get("JIRA_TOKEN") or os.environ.get("JIRA_API_TOKEN")


def make_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if not email or not token:
        print("Error: Missing credentials (email or token).", file=sys.stderr)
        sys.exit(1)

    req = urllib.request.Request(url, method=method)
    auth_str = f"{email}:{token}"
    encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

    req.add_header("Authorization", f"Basic {encoded_auth}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        data = json.dumps(payload).encode("utf-8") if payload else None
        with urllib.request.urlopen(req, data=data, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            return dict(json.loads(res_body)) if res_body else {}
    except Exception as e:
        print(f"Jira API Request failed: {e}", file=sys.stderr)
        if hasattr(e, "read"):
            print(e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)


def minify_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    minified = []
    for issue in issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        minified.append(
            {
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": (fields.get("status") or {}).get("name"),
                "priority": (fields.get("priority") or {}).get("name"),
                "description": fields.get("description"),
                "assignee": assignee.get("displayName")
                or assignee.get("emailAddress")
                or "Unassigned",
            }
        )
    return minified


def search_issues(config: Dict[str, Any], jql: str) -> List[Dict[str, Any]]:
    url = f"{config['jira_url']}/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}&fields=summary,description,status,priority,assignee"
    res = make_request(url, email=config["jira_email"], token=config["jira_token"])
    return minify_issues(res.get("issues", []))


def get_transitions(config: Dict[str, Any], issue_key: str) -> Dict[str, Any]:
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}/transitions"
    return make_request(url, email=config["jira_email"], token=config["jira_token"])


def transition_issue(
    config: Dict[str, Any], issue_key: str, target_status: str
) -> None:
    transitions_res = get_transitions(config, issue_key)
    transitions = transitions_res.get("transitions", [])

    transition_id = None
    available_statuses = []
    for t in transitions:
        status_name = t.get("to", {}).get("name")
        available_statuses.append(status_name)
        if status_name.lower() == target_status.lower():
            transition_id = t.get("id")
            break

    if not transition_id:
        print(
            f"Error: Transition to '{target_status}' not found for issue {issue_key}.",
            file=sys.stderr,
        )
        print(
            f"Available target statuses: {', '.join(available_statuses)}",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = {"transition": {"id": transition_id}}
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}/transitions"
    make_request(
        url,
        method="POST",
        payload=payload,
        email=config["jira_email"],
        token=config["jira_token"],
    )
    print(
        json.dumps(
            {
                "ok": True,
                "message": f"Successfully transitioned {issue_key} to '{target_status}'",
            }
        )
    )


def create_issue(config: Dict[str, Any], summary: str, description: Any) -> None:
    if isinstance(description, str):
        paragraphs = []
        for line in description.split("\n"):
            line = line.strip()
            if line:
                paragraphs.append(
                    {"type": "paragraph", "content": [{"type": "text", "text": line}]}
                )
        if not paragraphs:
            paragraphs.append(
                {"type": "paragraph", "content": [{"type": "text", "text": ""}]}
            )
        description = {"version": 1, "type": "doc", "content": paragraphs}
    payload = {
        "fields": {
            "project": {"key": config["project_key"]},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Task"},
        }
    }
    url = f"{config['jira_url']}/rest/api/3/issue"
    res = make_request(
        url,
        method="POST",
        payload=payload,
        email=config["jira_email"],
        token=config["jira_token"],
    )
    print(json.dumps({"ok": True, "key": res.get("key"), "self": res.get("self")}))


def main() -> None:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    if len(sys.argv) < 2:
        print("Usage: jira_bridge.py <action> [args]", file=sys.stderr)
        sys.exit(1)

    jira_config = {
        "jira_url": os.environ.get("JIRA_URL") or "",
        "jira_email": os.environ.get("JIRA_EMAIL") or "",
        "project_key": os.environ.get("JIRA_PROJECT_KEY") or "",
    }

    # Fallback to local and global JSON configs if env variables are missing
    local_jira = os.path.join(os.getcwd(), ".agents", "jira.json")
    if os.path.exists(local_jira):
        try:
            with open(local_jira, "r") as f:
                l_data = json.load(f)
                jira_config["project_key"] = jira_config["project_key"] or l_data.get(
                    "projectKey"
                )
                jira_config["jira_url"] = jira_config["jira_url"] or l_data.get(
                    "jira_url"
                )
                jira_config["jira_email"] = jira_config["jira_email"] or l_data.get(
                    "jira_email"
                )
        except Exception:
            pass

    global_jira = os.path.expanduser("~/.gemini/config/jira_config.json")
    if os.path.exists(global_jira):
        try:
            with open(global_jira, "r") as f:
                g_data = json.load(f)
                jira_config["jira_url"] = jira_config["jira_url"] or g_data.get(
                    "jira_url"
                )
                jira_config["jira_email"] = jira_config["jira_email"] or g_data.get(
                    "jira_email"
                )
                jira_config["project_key"] = jira_config["project_key"] or g_data.get(
                    "project_key"
                )
        except Exception:
            pass

    token = get_jira_token()
    if not token and os.path.exists(global_jira):
        try:
            with open(global_jira, "r") as f:
                g_data = json.load(f)
                token = g_data.get("jira_token") or g_data.get("token")
        except Exception:
            pass

    if not token:
        print("Error: Jira token not found in environment.", file=sys.stderr)
        sys.exit(1)

    jira_config["jira_token"] = token

    if (
        not jira_config.get("jira_url")
        or not jira_config.get("jira_email")
        or not jira_config.get("project_key")
    ):
        print(
            "Error: Missing Jira configuration (JIRA_URL, JIRA_EMAIL, or JIRA_PROJECT_KEY). Please set them in your .env file or JSON configs.",
            file=sys.stderr,
        )
        sys.exit(1)
    action = sys.argv[1]

    if action == "get-todo":
        jql = f"project = {jira_config['project_key']} AND status in ('To Do', 'Selected for Development') ORDER BY priority DESC, created ASC"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))

    elif action == "get-in-progress":
        jql = f"project = {jira_config['project_key']} AND status = 'In Progress'"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))

    elif action == "get-in-review":
        jql = f"project = {jira_config['project_key']} AND status = 'In Review'"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))

    elif action == "get-backlog":
        jql = f"project = {jira_config['project_key']} AND status = 'Backlog' ORDER BY priority DESC"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))

    elif action == "transition":
        if len(sys.argv) < 4:
            print(
                "Usage: jira_bridge.py transition <issue_key> <target_status>",
                file=sys.stderr,
            )
            sys.exit(1)
        issue_key = sys.argv[2]
        target_status = sys.argv[3]
        transition_issue(jira_config, issue_key, target_status)

    elif action == "create":
        if len(sys.argv) < 4:
            print(
                "Usage: jira_bridge.py create <summary> <description>", file=sys.stderr
            )
            sys.exit(1)
        summary = sys.argv[2]
        description = sys.argv[3]
        create_issue(jira_config, summary, description)

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
