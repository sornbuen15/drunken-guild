import asyncio
import base64
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from core.context import ProjectContext
from core.errors import DrunkenError
from core.http import open_url


def _make_request_sync(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if not email or not token:
        raise ValueError("Error: Missing credentials (email or token).")

    req = urllib.request.Request(url, method=method)
    auth_str = f"{email}:{token}"
    encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

    req.add_header("Authorization", f"Basic {encoded_auth}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        req.data = json.dumps(payload).encode("utf-8") if payload else None
        with open_url(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            return dict(json.loads(res_body)) if res_body else {}
    except DrunkenError:
        # Already structured and carries a remediation. Flattening it into a
        # generic RuntimeError here would throw away the one part the agent
        # can act on.
        raise
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, "read"):
            try:
                error_msg += " " + e.read().decode("utf-8")
            except Exception:
                pass
        raise RuntimeError(f"Jira API Request failed: {error_msg}") from None


async def make_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _make_request_sync, url, method, payload, email, token
    )


def to_adf(text: str) -> Dict[str, Any]:
    """Convert plain text into an Atlassian Document Format doc node.

    One paragraph per line; blank lines are separators rather than content,
    because an ADF paragraph carrying an empty text child is rejected by the
    API. A document with no paragraphs at all is not valid either, so wholly
    blank input becomes a single contentless paragraph.
    """
    paragraphs: List[Dict[str, Any]] = [
        {"type": "paragraph", "content": [{"type": "text", "text": stripped}]}
        for line in text.replace("\r\n", "\n").split("\n")
        if (stripped := line.strip())
    ]
    if not paragraphs:
        paragraphs.append({"type": "paragraph"})
    return {"version": 1, "type": "doc", "content": paragraphs}


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


class JiraClient:
    def __init__(self, ctx: ProjectContext) -> None:
        jira = ctx.require_jira()
        self.base_url = jira.url.rstrip("/")
        self.email = jira.email
        self.token = jira.token.reveal()
        self.project_key = jira.project_key

    async def search_issues(self, jql: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}&fields=summary,description,status,priority,assignee"
        res = await make_request(url, email=self.email, token=self.token)
        return minify_issues(res.get("issues", []))

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        return await make_request(url, email=self.email, token=self.token)

    async def get_transitions(self, issue_key: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        return await make_request(url, email=self.email, token=self.token)

    async def transition_issue(
        self, issue_key: str, target_status: str
    ) -> Dict[str, Any]:
        transitions_res = await self.get_transitions(issue_key)
        transitions = transitions_res.get("transitions", [])

        transition_id = None
        available_statuses = []
        for t in transitions:
            status_name = t.get("to", {}).get("name")
            if status_name:
                available_statuses.append(status_name)
                if status_name.lower() == target_status.lower():
                    transition_id = t.get("id")
                    break

        if not transition_id:
            raise ValueError(
                f"Transition to '{target_status}' not found for issue {issue_key}. "
                f"Available target statuses: {', '.join(available_statuses)}"
            )

        payload = {"transition": {"id": transition_id}}
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        await make_request(
            url, method="POST", payload=payload, email=self.email, token=self.token
        )
        return {
            "ok": True,
            "message": f"Successfully transitioned {issue_key} to '{target_status}'",
        }

    async def create_issue(
        self, summary: str, description: Any, issue_type: str = "Task"
    ) -> Dict[str, Any]:
        if isinstance(description, str):
            description = to_adf(description)

        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }
        }
        url = f"{self.base_url}/rest/api/3/issue"
        res = await make_request(
            url, method="POST", payload=payload, email=self.email, token=self.token
        )
        return {"ok": True, "key": res.get("key"), "self": res.get("self")}

    async def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        payload = {"body": to_adf(comment)}
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        res = await make_request(
            url, method="POST", payload=payload, email=self.email, token=self.token
        )
        return {"ok": True, "id": res.get("id")}
