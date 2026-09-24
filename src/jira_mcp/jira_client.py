import asyncio
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.context import ProjectContext
from core.errors import DrunkenError
from core.http import open_url

from . import assign, backlog


class JiraHTTPError(RuntimeError):
    """A Jira response that failed, with its HTTP status kept.

    Subclasses ``RuntimeError`` deliberately: every existing caller catches that
    and must keep working unchanged. What it adds is ``status``, because some
    400s are answers rather than failures — ``Tried to move to backlog on board
    without backlog`` is Jira telling us a capability is absent, and the only
    other way to recognise it was to match on the text of a flattened message.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class BoardProfile:
    """What this project's board is, and what it can actually do.

    ``type`` is recorded but never used to decide capability. Surveyed live on
    2026-08-16: board 68 is ``kanban`` and has no backlog, while three ``simple``
    boards have one, and a team-managed project can switch sprints on without
    its type changing at all. So capability is probed and type is only reported.

    Three states matter and must not collapse into each other:

    * ``known=False`` — the lookup failed. We know nothing, and saying "no
      board" would be inventing a fact.
    * ``known=True, id=None`` — confirmed: this project has no board. A
      business-type Jira project (ALPHA, BETA) cannot have one.
    * ``backlog=None`` — there is a board, but the backlog probe could not
      answer. Not the same as ``False``; see :meth:`JiraClient._probe_backlog`.
    """

    id: Optional[int] = None
    #: What the board is attached to, from the Agile API's ``location``.
    #:
    #: The board's own ``name`` is deliberately not carried. It is frozen at
    #: creation and there is no way to change it — a team-managed project offers
    #: no board-rename UI, and the Agile API creates and deletes boards rather
    #: than renaming them. Rename the project afterwards and the label is wrong
    #: forever: this board still answered ``DT board`` months after the project
    #: became ``Drunken-Guild``. Reporting an unchangeable field beside
    #: changeable ones is what sends a reader looking for a setting that does
    #: not exist, so it is not reported at all (DG-274).
    project_key: Optional[str] = None
    project_name: Optional[str] = None
    display_name: Optional[str] = None
    type: Optional[str] = None
    backlog: Optional[bool] = None
    known: bool = True


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
    except urllib.error.HTTPError as e:
        # Same message as the generic branch below, so nothing that reads it
        # changes -- but the status survives, which is what lets a caller tell
        # "this board has no backlog" (400) from "Jira is unreachable".
        body = ""
        try:
            body = " " + e.read().decode("utf-8")
        except Exception:
            pass
        raise JiraHTTPError(e.code, f"Jira API Request failed: {e}{body}") from None
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


#: A heading marker, one to three hashes *followed by a space*. The space is
#: required on purpose: `#DG-279` is a reference, and ticket bodies are full of
#: them.
_MD_HEADING = re.compile(r"^(#{1,3}) +(.*)$")

#: A bullet. Both markers, because both are already in use across this repo's
#: own ticket bodies and correcting authors is not what this is for.
_MD_BULLET = re.compile(r"^[-*] +(.*)$")

_MD_FENCE = "```"


def _adf_text(text: str) -> List[Dict[str, Any]]:
    """A text child, or nothing at all — ADF rejects an empty text node."""
    return [{"type": "text", "text": text}] if text else []


def _consume_fence(lines: List[str], index: int) -> tuple[Dict[str, Any], int]:
    """The code block opening at *index*, and the line after its close.

    An unterminated fence runs to the end rather than raising: this is a ticket
    body, and losing the rest of it to one missing pair of backticks is a worse
    outcome than a long code block.
    """
    language = lines[index].strip()[len(_MD_FENCE) :].strip()
    body: List[str] = []
    index += 1
    while index < len(lines) and not lines[index].strip().startswith(_MD_FENCE):
        body.append(lines[index])
        index += 1

    node: Dict[str, Any] = {
        "type": "codeBlock",
        "content": _adf_text("\n".join(body)),
    }
    if language:
        node["attrs"] = {"language": language}
    return node, index + 1


def to_adf(text: str) -> Dict[str, Any]:
    """Convert Markdown-ish plain text into an Atlassian Document Format doc.

    One paragraph per line; blank lines are separators rather than content,
    because an ADF paragraph carrying an empty text child is rejected by the
    API. A document with no paragraphs at all is not valid either, so wholly
    blank input becomes a single contentless paragraph.

    Headings, bullets and fenced code are recognised (DG-279). Before that
    every line became a paragraph, so a ticket filed by this project rendered
    as an undifferentiated wall — including the FINDING / SCOPE / ACCEPTANCE
    headings the `jira-tickets` skill requires, which arrived as ordinary
    sentences. :data:`_ADF_BLOCKS` had listed `heading`, `codeBlock` and
    `listItem` the whole time: the reader half of this pair understood shapes
    the writer half could not produce.

    Deliberately not a Markdown parser. Four block shapes, no inline marks, no
    nesting — enough that a ticket reads as a document, and little enough that
    it cannot mangle a body that was never meant as Markdown.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    content: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []

    def close_list() -> None:
        if items:
            content.append({"type": "bulletList", "content": list(items)})
            items.clear()

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()

        if stripped.startswith(_MD_FENCE):
            close_list()
            node, index = _consume_fence(lines, index)
            content.append(node)
            continue

        if heading := _MD_HEADING.match(stripped):
            close_list()
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": len(heading.group(1))},
                    "content": _adf_text(heading.group(2).strip()),
                }
            )
        elif bullet := _MD_BULLET.match(stripped):
            items.append(
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": _adf_text(bullet.group(1).strip()),
                        }
                    ],
                }
            )
        elif stripped:
            close_list()
            content.append({"type": "paragraph", "content": _adf_text(stripped)})
        else:
            close_list()

        index += 1

    close_list()
    if not content:
        content.append({"type": "paragraph"})
    return {"version": 1, "type": "doc", "content": content}


#: Block-level ADF nodes, each of which starts a new line in the flattened text.
_ADF_BLOCKS: frozenset[str] = frozenset(
    {
        "paragraph",
        "heading",
        "codeBlock",
        "blockquote",
        "listItem",
        "rule",
        "tableRow",
        "mediaSingle",
        "mediaGroup",
        "panel",
    }
)


def _adf_leaf(node: Dict[str, Any]) -> Optional[str]:
    """The text a leaf node contributes, or ``None`` if it is not a leaf.

    Split out from :func:`from_adf` so the tree walk stays one readable branch.
    ``None`` and ``""`` mean different things here: the first says "descend into
    this", the second says "a leaf that renders as nothing".
    """
    kind = node.get("type")
    if kind == "text":
        return str(node.get("text", ""))
    if kind == "hardBreak":
        return "\n"
    if kind == "rule":
        return "\n---\n"
    if kind in ("emoji", "mention"):
        attrs = node.get("attrs") or {}
        return str(attrs.get("text") or attrs.get("shortName") or "")
    return None


def _adf_fence(node: Dict[str, Any]) -> str:
    """A code block rendered whole, marker and all.

    Rendered rather than walked so its body survives verbatim: a `# comment` or
    a `- flag` inside a fence is shell, not Markdown, and :func:`to_adf` has to
    be able to read back what it wrote (DG-279).
    """
    language = str((node.get("attrs") or {}).get("language") or "")
    body: List[str] = []
    for child in node.get("content") or []:
        _adf_walk(child, body)
    return f"{_MD_FENCE}{language}\n{''.join(body)}\n{_MD_FENCE}\n"


def _adf_walk(node: Any, out: List[str]) -> None:
    """Append *node*'s text to *out*, descending into anything not a leaf."""
    if not isinstance(node, dict):
        return

    leaf = _adf_leaf(node)
    if leaf is not None:
        out.append(leaf)
        return

    kind = node.get("type")

    # Rendered whole rather than walked, so its body survives verbatim: a
    # `# comment` or a `- flag` inside a fence is shell, not Markdown, and
    # `to_adf` has to be able to read back what it wrote (DG-279).
    if kind == "codeBlock":
        if out and not out[-1].endswith("\n"):
            out.append("\n")
        out.append(_adf_fence(node))
        return

    is_block = kind in _ADF_BLOCKS
    # A block starts a new line, unless one is already open or a bullet marker
    # is waiting for its text -- "- \none" is not a list item.
    if is_block and out and not out[-1].endswith(("\n", "- ")):
        out.append("\n")
    if kind == "listItem":
        out.append("- ")
    if kind == "heading":
        # Written back with its marker so a round trip is lossless. The reader
        # rendered a heading as a bare line, which meant a ticket written with
        # structure was read without it -- the same wall by a longer route.
        level = int((node.get("attrs") or {}).get("level", 1))
        out.append("#" * level + " ")

    for child in node.get("content") or []:
        _adf_walk(child, out)

    if is_block and out and not out[-1].endswith("\n"):
        out.append("\n")


def from_adf(node: Any) -> str:
    """Flatten an Atlassian Document Format document into plain text.

    The other half of :func:`to_adf`, and the reason DG-255 exists: ADF wraps
    one sentence in roughly four times its length, and ``minify_issues`` was
    returning it verbatim. A six-issue search spent 95% of its tokens on markup
    no reader wanted.

    Unknown node types are walked rather than dropped. ADF gains node types
    faster than we will notice, and losing a paragraph silently is worse than
    rendering it plainly -- an agent reading a truncated post-mortem cannot tell
    that it was truncated.

    Passing something that is already a string returns it unchanged, so callers
    do not have to know which shape Jira gave them.
    """
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    out: List[str] = []
    _adf_walk(node, out)

    # Collapse the runs of blank lines the block rule produces at nesting
    # boundaries, without touching the deliberate ones between paragraphs.
    text = "".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def minify_issues(
    issues: List[Dict[str, Any]], brief: bool = True
) -> List[Dict[str, Any]]:
    """Reduce Jira's search response to what a reader actually uses.

    ``brief`` is the default because the alternative was measured: a six-issue
    search cost 5,697 tokens and 95% of that was raw ADF description. The same
    search without descriptions cost 296. Anyone who wants the body asks for one
    issue by key, which is one cheap call rather than five expensive ones.

    What brief keeps, and why each earns its place:

    * ``key``, ``summary``, ``status`` — the question almost every search asks.
    * ``assignee`` — since DG-250 this is *whose* the work is; there is no other
      surface that says so.
    * ``parent`` and ``parent_summary`` — hierarchy for free. Without them an
      agent that needs the Epic makes a second call per issue, so omitting them
      to save characters costs tokens.

    What brief drops:

    * ``description`` — the 95%.
    * ``priority`` — it cannot be set on a team-managed project at all, so every
      DG issue reads ``Medium``. A field with one possible value is not
      information; use ``labels`` (DG-255 B3).

    ``brief=False`` keeps both, with the description flattened out of ADF —
    still three to four times smaller than what this function used to return.
    """
    minified = []
    for issue in issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        parent = fields.get("parent") or {}
        row: Dict[str, Any] = {
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": (fields.get("status") or {}).get("name"),
            "assignee": assignee.get("displayName")
            or assignee.get("emailAddress")
            or "Unassigned",
        }
        if parent:
            row["parent"] = parent.get("key")
            row["parent_summary"] = (parent.get("fields") or {}).get("summary")
        if not brief:
            row["priority"] = (fields.get("priority") or {}).get("name")
            row["description"] = from_adf(fields.get("description"))
        minified.append(row)
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
        self._profile: Optional[BoardProfile] = None
        #: Field name -> id, from Jira's own /field. Never hardcoded: Start
        #: date is customfield_10015 on this instance and something else on
        #: the next one. Same lazy-once shape as the board profile.
        self._fields: Optional[Dict[str, str]] = None

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

    async def _probe_backlog(self, board_id: int) -> Optional[bool]:
        """Whether *board_id* has a backlog, asked rather than inferred.

        ``GET /board/{id}/backlog`` answers 400 *"Backlogs are not supported on
        this board"* when it does not, which is a fact stated by the only
        authority on it. ``maxResults=0`` because the answer is the status code,
        not the issues.

        Returns ``None`` when the probe itself failed. That is not the same as
        ``False``: reporting "no backlog" because a request timed out would
        invent a limitation the board does not have, and every caller would then
        refuse work that would have succeeded.

        Column names are not a substitute for this. Board 68's first column is
        literally called *Backlog* and the board has no backlog.
        """
        url = f"{self.base_url}/rest/agile/1.0/board/{board_id}/backlog?maxResults=0"
        try:
            await make_request(url, email=self.email, token=self.token)
        except JiraHTTPError as exc:
            if exc.status == 400 and backlog.is_no_backlog_response(str(exc)):
                return False
            return None
        except Exception:
            # A timeout, a refused connection, a body that is not JSON: the
            # probe failed, which says nothing about the board. None, not
            # False — "could not ask" must not be reported as "no backlog",
            # or callers refuse work that would have succeeded (docstring).
            return None
        return True

    async def board_profile(self) -> BoardProfile:
        """This project's board and what it can do. One lookup per process.

        Cached including the healthy answer, so the common case costs two calls
        for the life of the server and nothing thereafter.
        """
        if self._profile is None:
            self._profile = await self._build_profile()
        return self._profile

    async def _build_profile(self) -> BoardProfile:
        try:
            boards = await self._fetch_boards()
        except Exception:
            # Ignorance, not a finding. Everything downstream distinguishes the
            # two, because "we could not ask" and "there is no board" lead to
            # different advice.
            return BoardProfile(known=False)

        if not boards:
            return BoardProfile(known=True)

        board = boards[0]
        board_id = board.get("id")

        has_backlog: Optional[bool] = None
        if board_id:
            try:
                has_backlog = await self._probe_backlog(board_id)
            except Exception:
                # The board is real and known even when the second question
                # could not be asked. Losing the whole profile over the
                # optional half of it would be the cure being worse than the
                # disease again.
                has_backlog = None

        # Only `location` is read. See BoardProfile for why `board["name"]` is
        # not carried at all.
        location = board.get("location") or {}

        return BoardProfile(
            id=board_id,
            project_key=location.get("projectKey"),
            project_name=location.get("projectName"),
            display_name=location.get("displayName"),
            type=board.get("type"),
            backlog=has_backlog,
            known=True,
        )

    async def issue_types(self) -> List[str]:
        """Issue type names this project accepts, or an empty list.

        Asked of the project rather than assumed: "Story" exists on some
        projects and not others, and a create that names a missing type fails
        with a message that does not say which ones are available.
        """
        try:
            res = await make_request(
                f"{self.base_url}/rest/api/3/project/"
                f"{urllib.parse.quote(self.project_key)}",
                email=self.email,
                token=self.token,
            )
            return [
                str(t.get("name"))
                for t in (res.get("issueTypes") or [])
                if t.get("name")
            ]
        except Exception:
            return []

    async def settable_fields(self) -> Dict[str, str]:
        """The optional fields ``create_issue`` can set, and their ids here.

        Reported so nobody has to guess, and so nobody hardcodes
        ``customfield_10015`` after finding it in a payload -- it is Start date
        on this instance only. Absent names are absent from the map rather than
        reported as null: "this instance does not have that field" is a
        different fact from "its id is unknown".
        """
        fields = await self.field_map()
        wanted = ("start date", "due date", "labels", "parent", "rank")
        return {name: fields[name] for name in wanted if name in fields}

    async def board_warning(self) -> Optional[str]:
        """One line of warning when work filed here will not appear anywhere.

        A business-type Jira project (Jira Work Management) has no agile
        board at all — not a setting that is switched off, but a thing that
        does not exist for that project type. Creating an issue in one still
        succeeds and still returns a key; it is simply invisible afterwards.
        Nothing errors, which is what makes it worth saying out loud.

        Advisory: a lookup that failed says nothing at all. This exists to add
        a warning, so letting it fail a create would make the cure worse than
        the disease.
        """
        profile = await self.board_profile()
        if not profile.known or profile.id is not None:
            return None
        return (
            f"{self.project_key} has no agile board (a business-type Jira "
            "project cannot have one), so this issue will not appear on any "
            "board. It is still reachable by key and by JQL. To get a board, "
            "the work has to live in a software-type project."
        )

    async def _move_issues(self, url: str, issue_keys: List[str]) -> Dict[str, Any]:
        """POST a move and read what Jira actually did.

        Both endpoints answer 204 with an empty body on a clean move, and 207
        with per-issue ``entries`` when only some of them went. A 207 is not a
        success, and reporting it as one would leave the caller believing a
        batch moved when half of it did not.
        """
        res = await make_request(
            url,
            method="POST",
            payload={"issues": issue_keys},
            email=self.email,
            token=self.token,
        )
        entries = res.get("entries") if isinstance(res, dict) else None
        if entries:
            return {"ok": False, "requested": issue_keys, "entries": entries}
        return {"ok": True, "moved": issue_keys}

    async def move_to_backlog(
        self, board_id: int, issue_keys: List[str]
    ) -> Dict[str, Any]:
        """Take issues off the board and put them in its backlog.

        Keys are the caller's responsibility to scope — see
        :func:`jira_mcp.backlog.scope_keys`, which the tool runs first. This
        endpoint will happily move another project's issues.
        """
        return await self._move_issues(
            f"{self.base_url}/rest/agile/1.0/backlog/{board_id}/issue", issue_keys
        )

    async def move_to_board(
        self, board_id: int, issue_keys: List[str]
    ) -> Dict[str, Any]:
        """Put backlog issues back onto the board. The way home from
        :meth:`move_to_backlog`."""
        return await self._move_issues(
            f"{self.base_url}/rest/agile/1.0/board/{board_id}/issue", issue_keys
        )

    async def search_issues(self, jql: str, brief: bool = True) -> List[Dict[str, Any]]:
        """Search, returning the brief shape unless asked for the full one.

        ``parent`` is requested in both shapes: it is a few characters on the
        wire and it removes a follow-up call per issue. ``description`` is only
        requested when it will be returned — asking Jira for ADF and then
        discarding it costs nothing in tokens but everything in latency on a
        large board.
        """
        fields = "summary,status,assignee,parent"
        if not brief:
            fields += ",description,priority"
        url = (
            f"{self.base_url}/rest/api/3/search/jql"
            f"?jql={urllib.parse.quote(jql)}&fields={fields}"
        )
        res = await make_request(url, email=self.email, token=self.token)
        return minify_issues(res.get("issues", []), brief=brief)

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

    async def field_map(self) -> Dict[str, str]:
        """Lowercased field name -> field id, as this Jira instance reports it.

        Resolved at runtime and cached, because custom field ids are per
        instance. Start date is ``customfield_10015`` here and there is no
        reason to expect it anywhere else; hardcoding it is how a payload
        silently writes nothing on somebody else's site.

        Never raises: an instance that will not list its fields still creates
        issues, just without the optional dates.
        """
        if self._fields is None:
            try:
                res = await make_request(
                    f"{self.base_url}/rest/api/3/field",
                    email=self.email,
                    token=self.token,
                )
                self._fields = {
                    str(f.get("name", "")).lower(): str(f.get("id"))
                    for f in (res if isinstance(res, list) else [])
                    if f.get("id")
                }
            except Exception:
                self._fields = {}
        return self._fields

    async def create_issue(
        self,
        summary: str,
        description: Any,
        issue_type: str = "Task",
        parent: Optional[str] = None,
        duedate: Optional[str] = None,
        start_date: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an issue, with the fields that make it visible once created.

        Everything past ``issue_type`` is optional and was absent until DG-255,
        which is why this project's Timeline was empty: an Epic with no children
        has nothing to draw. ``parent`` is what makes an issue a child.

        ``labels`` stands in for priority. Priority cannot be set on a
        team-managed project at all -- every DG issue reads ``Medium`` because
        that is the only value it can have -- so a label is the only way to mark
        one ticket as more urgent than another.

        Dates are ISO ``YYYY-MM-DD``. ``start_date`` goes through
        :meth:`field_map` rather than a hardcoded id.
        """
        if isinstance(description, str):
            description = to_adf(description)

        fields: Dict[str, Any] = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
        if parent:
            fields["parent"] = {"key": parent}
        if duedate:
            fields["duedate"] = duedate
        if labels:
            fields["labels"] = labels
        if start_date:
            start_id = (await self.field_map()).get("start date")
            if start_id:
                fields[start_id] = start_date

        url = f"{self.base_url}/rest/api/3/issue"
        res = await make_request(
            url,
            method="POST",
            payload={"fields": fields},
            email=self.email,
            token=self.token,
        )
        # The key, not the `self` URL. The URL is derivable from the key and
        # nobody ever followed it; it was pure cost on every create (DG-255 A4).
        return {"ok": True, "key": res.get("key")}

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

    async def edit_labels(
        self, issue_key: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply a ``labels.update_payload`` body. Jira answers 204, no body."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        await make_request(
            url, method="PUT", payload=payload, email=self.email, token=self.token
        )
        return {"ok": True, "issue": issue_key}

    async def edit_issue(
        self, issue_key: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply an ``edits.fields_payload`` body. Jira answers 204, no body."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        await make_request(
            url, method="PUT", payload=payload, email=self.email, token=self.token
        )
        return {"ok": True, "issue": issue_key}

    async def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        payload = {"body": to_adf(comment)}
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        res = await make_request(
            url, method="POST", payload=payload, email=self.email, token=self.token
        )
        return {"ok": True, "id": res.get("id")}
