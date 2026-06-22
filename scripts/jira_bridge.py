#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import urllib.request
import urllib.parse
import base64

def find_config():
    curr_dir = os.getcwd()
    while True:
        config_path = os.path.join(curr_dir, '.agents', 'jira_config.json')
        if os.path.exists(config_path):
            return config_path
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent
    return None

def get_jira_token():
    # 1. Try environment variables
    token = os.environ.get("JIRA_TOKEN") or os.environ.get("JIRA_API_TOKEN")
    if token:
        return token
    
    # 2. Try 1Password CLI
    try:
        res = subprocess.run(["op", "read", "op://Private/Jira-TFF/password"], capture_output=True, text=True, check=True)
        token = res.stdout.strip()
        if token:
            return token
    except Exception:
        pass
        
    return None

def make_request(url, method="GET", payload=None, email=None, token=None):
    if not email or not token:
        print("Error: Missing credentials (email or token).", file=sys.stderr)
        sys.exit(1)
        
    req = urllib.request.Request(url, method=method)
    auth_str = f"{email}:{token}"
    encoded_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
    
    req.add_header("Authorization", f"Basic {encoded_auth}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    
    try:
        data = json.dumps(payload).encode('utf-8') if payload else None
        with urllib.request.urlopen(req, data=data, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body) if res_body else {}
    except Exception as e:
        print(f"Jira API Request failed: {e}", file=sys.stderr)
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'), file=sys.stderr)
        sys.exit(1)

def minify_issues(issues):
    minified = []
    for issue in issues:
        fields = issue.get('fields', {})
        assignee = fields.get('assignee') or {}
        minified.append({
            "key": issue.get('key'),
            "summary": fields.get('summary'),
            "status": (fields.get('status') or {}).get('name'),
            "priority": (fields.get('priority') or {}).get('name'),
            "description": fields.get('description'),
            "assignee": assignee.get('displayName') or assignee.get('emailAddress') or "Unassigned"
        })
    return minified

def search_issues(config, jql):
    url = f"{config['jira_url']}/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}&fields=summary,description,status,priority,assignee"
    res = make_request(url, email=config['jira_email'], token=config['jira_token'])
    return minify_issues(res.get('issues', []))

def get_transitions(config, issue_key):
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}/transitions"
    return make_request(url, email=config['jira_email'], token=config['jira_token'])

def transition_issue(config, issue_key, target_status):
    transitions_res = get_transitions(config, issue_key)
    transitions = transitions_res.get('transitions', [])
    
    transition_id = None
    available_statuses = []
    for t in transitions:
        status_name = t.get('to', {}).get('name')
        available_statuses.append(status_name)
        if status_name.lower() == target_status.lower():
            transition_id = t.get('id')
            break
            
    if not transition_id:
        print(f"Error: Transition to '{target_status}' not found for issue {issue_key}.", file=sys.stderr)
        print(f"Available target statuses: {', '.join(available_statuses)}", file=sys.stderr)
        sys.exit(1)
        
    payload = {"transition": {"id": transition_id}}
    url = f"{config['jira_url']}/rest/api/3/issue/{issue_key}/transitions"
    make_request(url, method="POST", payload=payload, email=config['jira_email'], token=config['jira_token'])
    print(json.dumps({"ok": True, "message": f"Successfully transitioned {issue_key} to '{target_status}'"}))

def create_issue(config, summary, description):
    if isinstance(description, str):
        paragraphs = []
        for line in description.split('\n'):
            line = line.strip()
            if line:
                paragraphs.append({
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": line
                        }
                    ]
                })
        if not paragraphs:
            paragraphs.append({
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": ""
                    }
                ]
            })
        description = {
            "version": 1,
            "type": "doc",
            "content": paragraphs
        }
    payload = {
        "fields": {
            "project": {"key": config['project_key']},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Task"}
        }
    }
    url = f"{config['jira_url']}/rest/api/3/issue"
    res = make_request(url, method="POST", payload=payload, email=config['jira_email'], token=config['jira_token'])
    print(json.dumps({"ok": True, "key": res.get("key"), "self": res.get("self")}))

def main():
    if len(sys.argv) < 2:
        print("Usage: jira_bridge.py <action> [args]", file=sys.stderr)
        sys.exit(1)
        
    config_path = find_config()
    if not config_path:
        print("Error: .agents/jira_config.json not found in workspace.", file=sys.stderr)
        sys.exit(1)
        
    with open(config_path, 'r', encoding='utf-8') as f:
        jira_config = json.load(f)
        
    token = get_jira_token()
    if not token:
        print("Error: Jira token not found in environment or 1Password.", file=sys.stderr)
        sys.exit(1)
        
    jira_config['jira_token'] = token
    action = sys.argv[1]
    
    if action == "get-todo":
        jql = f"project = {jira_config['project_key']} AND status = 'To Do' ORDER BY priority DESC, created ASC"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))
        
    elif action == "get-in-progress":
        jql = f"project = {jira_config['project_key']} AND status = 'In Progress'"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))
        
    elif action == "get-backlog":
        jql = f"project = {jira_config['project_key']} AND status = 'Backlog' ORDER BY priority DESC"
        issues = search_issues(jira_config, jql)
        print(json.dumps(issues, indent=2))
        
    elif action == "transition":
        if len(sys.argv) < 4:
            print("Usage: jira_bridge.py transition <issue_key> <target_status>", file=sys.stderr)
            sys.exit(1)
        issue_key = sys.argv[2]
        target_status = sys.argv[3]
        transition_issue(jira_config, issue_key, target_status)
        
    elif action == "create":
        if len(sys.argv) < 4:
            print("Usage: jira_bridge.py create <summary> <description>", file=sys.stderr)
            sys.exit(1)
        summary = sys.argv[2]
        description = sys.argv[3]
        create_issue(jira_config, summary, description)
        
    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
