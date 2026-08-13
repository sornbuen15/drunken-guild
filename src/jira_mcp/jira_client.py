import asyncio
import base64
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from core.context import ProjectContext
from core.errors import DrunkenError
from core.http import open_url

from . import assign


def parse_response(body: str) -> Any:
    """Decode a Jira response body without assuming its shape.

    This used to be ``dict(json.loads(body))``, inline. Every endpoint called
    before ``/rest/api/3/user/assignable/search`` answered with an object, so
    the force-cast was invisible — and when the first array arrived it failed
    as *"dictionary update sequence element #0 has length 10; 2 is required"*,
    which describes the cast rather than the cause.

    An empty body reads as ``{}``: a successful ``PUT`` to the assignee
    endpoint returns 204 with nothing in it.
    """
    if not body:
        return {}
    return json.loads(body)


def _make_request_sync(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
    token: Optional[str] = None,
) -> Any:
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
            return parse_response(response.read().decode("utf-8"))
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
) -> Any:
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
        # Resolved lazily on first use and then cached for the life of the
        # process, same shape as the secrets resolver (checkpoint §3). The
        # agent never sees or passes a board id, which keeps it out of the
        # token budget and out of reach as an argument.
        self._board_warning: Optional[str] = None
        self._board_checked = False

    async def _fetch_boards(self) -> List[Dict[str, Any]]:
        """Agile boards for this project. Separate API from everything else
        here: /rest/api/3 is the platform, and it does not know what a board
        is — only /rest/agile/1.0 does."""
        url = (
            f"{self.base_url}/rest/agile/1.0/board"
            f"?projectKeyOrId={urllib.parse.quote(self.project_key)}&maxResults=1"
        )
        res = await make_request(url, email=self.email, token=self.token)
        values: List[Dict[str, Any]] = res.get("values", [])
        return values

    async def board_warning(self) -> Optional[str]:
        """One line of warning when work filed here will not appear anywhere.

        A business-type Jira project (Jira Work Management) has no agile
        board at all — not a setting that is switched off, but a thing that
        does not exist for that project type. Creating an issue in one still
        succeeds and still returns a key; it is simply invisible afterwards.
        Nothing errors, which is what makes it worth saying out loud.

        Looked up once per process and cached, including the healthy answer,
        so the common case costs one call for the life of the server and no
        tokens at all.
        """
        if self._board_checked:
            return self._board_warning

        self._board_checked = True
        try:
            boards = await self._fetch_boards()
        except Exception:
            # Advisory only. This exists to add a warning, so failing the
            # caller's actual work over it would make the cure worse than
            # the disease — stay quiet and let the real call speak.
            return None

        if not boards:
            self._board_warning = (
                f"{self.project_key} has no agile board (a business-type Jira "
                "project cannot have one), so this issue will not appear on any "
                "board. It is still reachable by key and by JQL. To get a board, "
                "the work has to live in a software-type project."
            )
        return self._board_warning

    async def search_issues(self, jql: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}&fields=summary,description,status,priority,assignee"
        res = await make_request(url, email=self.email, token=self.token)
        return minify_issues(res.get("issues", []))

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        res: Dict[str, Any] = await make_request(
            url, email=self.email, token=self.token
        )
        return res

    async def get_transitions(self, issue_key: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        res: Dict[str, Any] = await make_request(
            url, email=self.email, token=self.token
        )
        return res

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

    async def assignable_users(self, query: str) -> List[Dict[str, Any]]:
        """Users who can be assigned issues on this project.

        Scoped to ``self.project_key`` deliberately. The unscoped endpoint
        returns everyone on the site, which would let an issue be assigned to
        somebody with no access to the project it belongs to -- assigned,
        accepted, and invisible to them.
        """
        url = (
            f"{self.base_url}/rest/api/3/user/assignable/search"
            f"?project={urllib.parse.quote(self.project_key)}"
            f"&query={urllib.parse.quote(query)}&maxResults=50"
        )
        res = await make_request(url, email=self.email, token=self.token)
        if isinstance(res, list):
            return res
        values = res.get("values", [])
        return values if isinstance(values, list) else []

    async def my_account_id(self) -> str:
        """The account this credential belongs to.

        ``/rest/api/3/myself`` rather than a search, for the reason in
        core.context's docstring: it is the endpoint that actually fails on a
        bad credential instead of returning an empty result.
        """
        res = await make_request(
            f"{self.base_url}/rest/api/3/myself", email=self.email, token=self.token
        )
        account_id = res.get("accountId")
        if not account_id:
            raise DrunkenError(
                "Jira did not return an accountId for this credential.",
                remediation=(
                    "Check the credential with `drunken-doctor` -- this is the "
                    "endpoint it uses to verify identity."
                ),
            )
        return str(account_id)

    async def assign_issue(
        self, issue_key: str, account_id: Optional[str]
    ) -> Dict[str, Any]:
        """Set or clear the assignee. ``None`` unassigns."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/assignee"
        await make_request(
            url,
            method="PUT",
            payload=assign.payload_for(account_id),
            email=self.email,
            token=self.token,
        )
        return {"ok": True, "issue": issue_key, "account_id": account_id}

    async def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        payload = {"body": to_adf(comment)}
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        res = await make_request(
            url, method="POST", payload=payload, email=self.email, token=self.token
        )
        return {"ok": True, "id": res.get("id")}
