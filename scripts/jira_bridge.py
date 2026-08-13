#!/usr/bin/env python3
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


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
    # Look for .env in the current directory or any parent directory.
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


def add_comment(config: Dict[str, Any], issue_key: str, body: str) -> None:
    paragraphs = []
    for line in body.split("\n"):
        # rstrip, not strip: preserves leading indentation (tracebacks,
        # pytest output, code snippets) while still dropping trailing
        # whitespace/newline artifacts.
        line = line.rstrip()
        if line:
            paragraphs.append(
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            )
    if not paragraphs:
        paragraphs.append(
            {"type": "paragraph", "content": [{"type": "text", "text": ""}]}
        )
    payload = {"body": {"version": 1, "type": "doc", "content": paragraphs}}
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}/comment"
    make_request(
        url,
        method="POST",
        payload=payload,
        email=config["jira_email"],
        token=config["jira_token"],
    )
    print(json.dumps({"ok": True, "message": f"Commented on {issue_key}"}))


def add_label(config: Dict[str, Any], issue_key: str, label: str) -> None:
    payload = {"update": {"labels": [{"add": label}]}}
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}"
    make_request(
        url,
        method="PUT",
        payload=payload,
        email=config["jira_email"],
        token=config["jira_token"],
    )
    print(json.dumps({"ok": True, "message": f"Labeled {issue_key} with '{label}'"}))


def delete_issue(config: Dict[str, Any], issue_key: str) -> None:
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}"
    make_request(
        url,
        method="DELETE",
        email=config["jira_email"],
        token=config["jira_token"],
    )
    print(json.dumps({"ok": True, "message": f"Deleted {issue_key}"}))


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


def config_for_project(project_id: str) -> Dict[str, Any]:
    """Resolve one project's Jira config through the registry.

    This is the route the daemon takes. It exists because selecting a project
    by *working directory* — which is what the caller used to do — meant this
    script walked up from wherever it was standing and read whatever ``.env``
    it found. ALPHA's checkout held an expired token, a Jira search answers an
    expired token with ``200`` and an empty list, and so its board read as
    empty for months while the same project returned 39 issues over MCP.

    Named project, single source, no fallback: falling back to ``.env`` here
    would restore exactly the ambiguity this removes.
    """
    sys.path.insert(
        0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
    )
    from core.context import ProjectContext
    from core.errors import DrunkenError

    try:
        ctx = ProjectContext.build(project_id)
    except DrunkenError as exc:
        message = f"Error: {exc}"
        if exc.remediation:
            message += f"\n  -> {exc.remediation}"
        raise SystemExit(message) from None

    if not ctx.jira:
        raise SystemExit(
            f"Error: project {project_id!r} is registered but has no Jira "
            "identity, so there is nothing to query.\n"
            f"  -> Add one: drunken-init --project {project_id} --jira-url ... "
            "--jira-email ... --jira-project-key ... --jira-credential ..."
        )

    return {
        "jira_url": ctx.jira.url,
        "jira_email": ctx.jira.email,
        "project_key": ctx.jira.project_key,
        "jira_token": ctx.jira.token.reveal(),
    }


def project_for_directory(directory: str) -> Optional[str]:
    """The registered project whose checkout contains *directory*, if any.

    Standing inside a project's checkout is a perfectly clear statement of
    which project you mean, and until now it was answered by walking up to
    whatever ``.env`` turned up. In ALPHA's case that was an expired token, and
    a Jira search with an expired token returns ``200`` and an empty list —
    so the board simply read as empty.

    Matching the directory against the registry answers the same question
    correctly, without a second copy of the credential anywhere.
    """
    sys.path.insert(
        0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
    )
    try:
        from core.registry import ProjectRegistry

        here = os.path.realpath(directory)
        for project_id, entry in ProjectRegistry().get_projects().items():
            path = entry.get("path") if isinstance(entry, dict) else None
            if not path:
                continue
            root = os.path.realpath(os.path.expanduser(path))
            if here == root or here.startswith(root + os.sep):
                return str(project_id)
    except Exception:
        # An unreadable registry is not a reason to refuse to run: the
        # environment route below still works, which is what it was for.
        return None
    return None


def resolve_config(project_id: Optional[str]) -> Dict[str, Any]:
    """Registry when a project is named or implied, environment otherwise."""
    if project_id:
        return config_for_project(project_id)

    implied = project_for_directory(os.getcwd())
    if implied:
        return config_for_project(implied)

    return config_from_environment()


def config_from_environment() -> Dict[str, Any]:  # noqa: C901
    """The original route, for running this by hand from a checkout.

    Kept because that is a genuinely convenient thing to do and breaking it to
    fix the daemon would be a poor trade. The daemon no longer uses it.
    """
    jira_config: Dict[str, Any] = {
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
                    "project_key"
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
        raise SystemExit("Error: Jira token not found in environment.")

    jira_config["jira_token"] = token

    if (
        not jira_config.get("jira_url")
        or not jira_config.get("jira_email")
        or not jira_config.get("project_key")
    ):
        raise SystemExit(
            "Error: Missing Jira configuration (JIRA_URL, JIRA_EMAIL, or "
            "JIRA_PROJECT_KEY).\n"
            "  -> Set them in .env, or name a registered project instead: "
            "jira_bridge.py --project <id> <action>"
        )
    return jira_config


def main() -> None:  # noqa: C901  # long dispatch chain; splitting it buys nothing here
    argv = sys.argv[1:]

    # `--project <id>` selects the project explicitly, ahead of the action.
    # Everything after it is the action and its arguments, unchanged.
    project_id = None
    if argv and argv[0] == "--project":
        if len(argv) < 2:
            raise SystemExit("Usage: jira_bridge.py --project <id> <action> [args]")
        project_id = argv[1]
        argv = argv[2:]

    if not argv:
        raise SystemExit(
            "Usage: jira_bridge.py [--project <id>] <action> [args]\n"
            "  With --project, config comes from the registry.\n"
            "  Without it, from the environment and .env."
        )

    jira_config = resolve_config(project_id)
    sys.argv = [sys.argv[0], *argv]
    action = argv[0]

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
        # This project has no native 'Backlog' status (team-managed/next-gen Jira
        # projects don't expose the Board's Backlog panel via API). Backlog here
        # means: not Done, and not tagged into an active round via label.
        jql = f"project = {jira_config['project_key']} AND status != 'Done' AND labels is EMPTY ORDER BY priority DESC"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))

    elif action == "get-by-label":
        if len(sys.argv) < 3:
            print("Usage: jira_bridge.py get-by-label <label>", file=sys.stderr)
            sys.exit(1)
        label = sys.argv[2]
        jql = f"project = {jira_config['project_key']} AND labels = '{label}' AND status != 'Done' ORDER BY priority DESC"
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

    elif action == "comment":
        if len(sys.argv) < 4:
            print("Usage: jira_bridge.py comment <issue_key> <body>", file=sys.stderr)
            sys.exit(1)
        issue_key = sys.argv[2]
        body = sys.argv[3]
        add_comment(jira_config, issue_key, body)

    elif action == "label":
        if len(sys.argv) < 4:
            print("Usage: jira_bridge.py label <issue_key> <label>", file=sys.stderr)
            sys.exit(1)
        issue_key = sys.argv[2]
        label = sys.argv[3]
        add_label(jira_config, issue_key, label)

    elif action == "delete":
        if len(sys.argv) < 3:
            print("Usage: jira_bridge.py delete <issue_key>", file=sys.stderr)
            sys.exit(1)
        issue_key = sys.argv[2]
        delete_issue(jira_config, issue_key)

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
