import json
import os
import urllib.request

token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
req = urllib.request.Request(
    "https://api.github.com/repos/sornbuen15/drunken-team/pulls", method="POST"
)
req.add_header("Authorization", f"Bearer {token}")
req.add_header("Accept", "application/vnd.github.v3+json")
data = json.dumps(
    {
        "title": "feat: restructure agents",
        "head": "feat/restructure-agents",
        "base": "develop",
        "body": "Restructure agents and update checkpoint. Preparing to migrate Jira bridge to MCP.",
    }
).encode("utf-8")
try:
    with urllib.request.urlopen(req, data=data) as response:
        print("Success! PR Created:", json.loads(response.read())["html_url"])
except Exception as e:
    print("Error:", e.read().decode() if hasattr(e, "read") else str(e))
