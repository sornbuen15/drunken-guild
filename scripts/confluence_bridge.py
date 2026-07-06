#!/usr/bin/env python3
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

SPACE_KEY = "D"
SPACE_ID = "2031618"
HOMEPAGE_ID = "2031725"


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
                            os.environ.setdefault(
                                key.strip(), val.strip().strip('"').strip("'")
                            )
            except Exception:
                pass
            break
        parent = os.path.dirname(curr_dir)
        if parent == curr_dir:
            break
        curr_dir = parent


def get_jira_token() -> Optional[str]:
    load_dotenv()
    token = os.environ.get("JIRA_TOKEN")

    global_jira = os.path.expanduser("~/.gemini/config/jira_config.json")
    if not token and os.path.exists(global_jira):
        try:
            with open(global_jira, "r") as f:
                g_data = json.load(f)
                token = g_data.get("jira_token") or g_data.get("token")
        except Exception:
            pass

    return token


def get_jira_email() -> Optional[str]:
    load_dotenv()
    email = os.environ.get("CONFLUENCE_EMAIL") or os.environ.get("JIRA_EMAIL")

    local_jira = os.path.join(os.getcwd(), ".agents", "jira.json")
    if not email and os.path.exists(local_jira):
        try:
            with open(local_jira, "r") as f:
                email = json.load(f).get("jira_email")
        except Exception:
            pass

    global_jira = os.path.expanduser("~/.gemini/config/jira_config.json")
    if not email and os.path.exists(global_jira):
        try:
            with open(global_jira, "r") as f:
                email = json.load(f).get("jira_email")
        except Exception:
            pass

    return email


def make_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    email: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if not email:
        email = get_jira_email()
    if not email:
        print(
            "Error: CONFLUENCE_EMAIL environment variable is not set and could not be found in config JSON files.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not token:
        print("Error: JIRA_TOKEN environment variable not set.", file=sys.stderr)
        sys.exit(1)

    req = urllib.request.Request(url, method=method)
    auth_str = f"{email}:{token}"
    encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

    req.add_header("Authorization", f"Basic {encoded_auth}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        data = json.dumps(payload).encode("utf-8") if payload else None
        with urllib.request.urlopen(req, data=data, timeout=20) as response:
            res_body = response.read().decode("utf-8")
            return dict(json.loads(res_body)) if res_body else {}
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        print(e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def inline_formatting(text: str) -> str:
    # Escape HTML special chars
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold **text** or __text__
    text = re.sub(r"\*\*(.*?)\*\*|__(.*?)__", r"<strong>\1\2</strong>", text)
    # Italic *text* or _text_
    text = re.sub(r"\*(.*?)\*|_(.*?)_", r"<em>\1\2</em>", text)
    # Inline code `code`
    text = re.sub(r"`(.*?)`", r"<code>\1</code>", text)
    # Link [text](url)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)
    return text


def markdown_to_html(md_text: str) -> str:  # noqa: C901  # TODO(DT-46): Technical Debt - Refactor to reduce McCabe complexity
    html_lines = []
    lines = md_text.split("\n")

    in_code_block = False
    in_list = False
    in_ordered_list = False
    in_table = False

    for line in lines:
        stripped = line.strip()

        # Code block
        if stripped.startswith("```"):
            if in_code_block:
                html_lines.append("</pre>")
                in_code_block = False
            else:
                lang = stripped[3:].strip()
                html_lines.append(f'<pre class="code-{lang}">')
                in_code_block = True
            continue

        if in_code_block:
            escaped = (
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            html_lines.append(escaped)
            continue

        # Lists
        if stripped.startswith("- ") or stripped.startswith("* "):
            if in_ordered_list:
                html_lines.append("</ol>")
                in_ordered_list = False
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item = stripped[2:]
            item = inline_formatting(item)
            html_lines.append(f"<li>{item}</li>")
            continue

        if re.match(r"^\d+\.\s", stripped):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if not in_ordered_list:
                html_lines.append("<ol>")
                in_ordered_list = True
            item = re.sub(r"^\d+\.\s", "", stripped)
            item = inline_formatting(item)
            html_lines.append(f"<li>{item}</li>")
            continue

        # Close lists if line is empty or doesn't match list
        if not stripped or (
            not stripped.startswith("- ")
            and not stripped.startswith("* ")
            and not re.match(r"^\d+\.\s", stripped)
        ):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_ordered_list:
                html_lines.append("</ol>")
                in_ordered_list = False

        # Empty line
        if not stripped:
            continue

        # Headers
        if stripped.startswith("#"):
            level = 0
            for char in stripped:
                if char == "#":
                    level += 1
                else:
                    break
            header_text = stripped[level:].strip()
            header_text = inline_formatting(header_text)
            html_lines.append(f"<h{level}>{header_text}</h{level}>")
            continue

        # Table
        if stripped.startswith("|"):
            if not in_table:
                html_lines.append("<table>")
                in_table = True
            if re.match(r"^\|[\s:-|]+\|$", stripped):
                continue
            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            html_lines.append("<tr>")
            for cell in cells:
                cell_text = inline_formatting(cell)
                # If we are in the first row, we can use th
                if len(html_lines) <= 2 or html_lines[-2] == "<table>":
                    html_lines.append(f"<th>{cell_text}</th>")
                else:
                    html_lines.append(f"<td>{cell_text}</td>")
            html_lines.append("</tr>")
            continue

        if in_table and not stripped.startswith("|"):
            html_lines.append("</table>")
            in_table = False

        # Regular paragraph
        item = inline_formatting(stripped)
        html_lines.append(f"<p>{item}</p>")

    if in_code_block:
        html_lines.append("</pre>")
    if in_list:
        html_lines.append("</ul>")
    if in_ordered_list:
        html_lines.append("</ol>")
    if in_table:
        html_lines.append("</table>")

    return "\n".join(html_lines)


def get_page_by_title(title: str, token: str) -> Optional[Dict[str, Any]]:
    title_quoted = urllib.parse.quote(title)
    url = f"https://sornbuen15.atlassian.net/wiki/api/v2/spaces/{SPACE_ID}/pages?title={title_quoted}"
    res = make_request(url, token=token)
    results = res.get("results", [])
    return results[0] if results else None


def create_page(
    title: str, body_html: str, parent_id: Optional[str], token: str
) -> Dict[str, Any]:
    payload = {
        "spaceId": SPACE_ID,
        "status": "current",
        "title": title,
        "parentId": parent_id or HOMEPAGE_ID,
        "body": {"representation": "storage", "value": body_html},
    }
    url = "https://sornbuen15.atlassian.net/wiki/api/v2/pages"
    return make_request(url, method="POST", payload=payload, token=token)


def update_page(
    page_id: str, current_version: int, title: str, body_html: str, token: str
) -> Dict[str, Any]:
    payload = {
        "id": page_id,
        "status": "current",
        "title": title,
        "spaceId": SPACE_ID,
        "body": {"representation": "storage", "value": body_html},
        "version": {
            "number": current_version + 1,
            "message": "Auto-updated by Antigravity",
        },
    }
    url = f"https://sornbuen15.atlassian.net/wiki/api/v2/pages/{page_id}"
    return make_request(url, method="PUT", payload=payload, token=token)


def strip_frontmatter(md_content: str) -> str:
    if md_content.startswith("---"):
        parts = md_content.split("---")
        if len(parts) >= 3:
            return "---".join(parts[2:]).strip()
    return md_content


def push_document(title: str, file_path: str, parent_id: Optional[str] = None) -> None:
    token = get_jira_token()
    if not token:
        print("Error: Jira token not found.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(file_path):
        print(f"Error: Local file '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # Strip YAML frontmatter if present
    md_content = strip_frontmatter(md_content)

    print(f"Converting '{title}' ({file_path}) to XHTML storage format...")
    html_content = markdown_to_html(md_content)

    print(f"Checking if page '{title}' exists in space {SPACE_KEY}...")
    existing_page = get_page_by_title(title, token)

    if existing_page:
        page_id = str(existing_page.get("id"))
        current_version = existing_page.get("version", {}).get("number", 1)
        print(f"Page exists (ID: {page_id}, Version: {current_version}). Updating...")
        res = update_page(page_id, current_version, title, html_content, token)
        print(
            json.dumps(
                {
                    "ok": True,
                    "action": "update",
                    "id": res.get("id"),
                    "title": res.get("title"),
                }
            )
        )
    else:
        print("Page does not exist. Creating page...")
        res = create_page(title, html_content, parent_id, token)
        print(
            json.dumps(
                {
                    "ok": True,
                    "action": "create",
                    "id": res.get("id"),
                    "title": res.get("title"),
                }
            )
        )


def main() -> None:
    if len(sys.argv) < 4 or sys.argv[1] != "push":
        print(
            "Usage: confluence_bridge.py push <title> <file_path> [parent_id]",
            file=sys.stderr,
        )
        sys.exit(1)

    title = sys.argv[2]
    file_path = sys.argv[3]
    parent_id = sys.argv[4] if len(sys.argv) > 4 else None

    push_document(title, file_path, parent_id)


if __name__ == "__main__":
    main()
