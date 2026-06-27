import json
import os
import requests
import sys


def delete_issues(issue_keys):
    global_conf = os.path.expanduser("~/.gemini/config/jira_config.json")
    if not os.path.exists(global_conf):
        print("Config not found")
        sys.exit(1)

    with open(global_conf, "r") as f:
        config = json.load(f)

    url = config.get("jira_url")
    email = config.get("jira_email")
    token = config.get("jira_token")

    if not url or not email or not token:
        print("Missing credentials")
        sys.exit(1)

    auth = (email, token)
    headers = {"Accept": "application/json"}

    for key in issue_keys:
        res = requests.delete(
            f"{url}/rest/api/3/issue/{key}", auth=auth, headers=headers, timeout=10
        )
        if res.status_code in [200, 204]:
            print(f"Deleted {key}")
        else:
            print(f"Failed to delete {key}: {res.status_code} {res.text}")


if __name__ == "__main__":
    delete_issues(sys.argv[1:])
