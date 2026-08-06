"""Board card parsing and field manipulation utilities.

Card format (Markdown):
    # PROJECT-NNN: Title

    ## Status
    - **Status:** Todo
    - **Assignee:** @agent
    - **Start Time:** YYYY-MM-DD
    - **End Time:** YYYY-MM-DD
    - **Milestone:** M3          # optional
    - **Claimed By:** @agent     # added by board_claim_task
    - **Claimed At:** ISO8601    # added by board_claim_task
    - **Depends On:** TWA-30, TWA-31  # optional
    - **Blocks:** TWA-35              # optional

    ## Requirements / Objective / Description
    ...

    ## Action Items
    - [ ] unchecked item
    - [x] checked item
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CardData:
    """Parsed representation of a board card markdown file."""

    task_id: str
    filename: str
    title: str
    status: str
    assignee: str
    start_time: str
    end_time: str
    milestone: str | None
    claimed_by: str | None
    claimed_at: str | None
    depends_on: list[str]
    blocks: list[str]
    action_items: list[str]
    content: str  # original raw file content


def extract_section(content: str, heading: str) -> str:
    """Extract the body of a ``## Heading`` section.

    Returns an empty string when the section is absent.
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*\n([\s\S]*?)(?=\n##\s|\Z)"
    m = re.search(pattern, content, re.MULTILINE)
    return m.group(1) if m else ""


def _get_field(block: str, key: str) -> str | None:
    """Return the value of ``- **Key:** value`` from *block* (case-insensitive key)."""
    escaped = re.escape(key)
    # Horizontal whitespace only — a bare ``\s*`` crosses the newline and makes an
    # empty field swallow the following line (``- **Assignee:**`` picking up
    # ``- **Start Time:**`` as its value).
    m = re.search(
        rf"^[ \t]*-[ \t]+\*\*{escaped}:\*\*[ \t]*(.*)$",
        block,
        re.MULTILINE | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _get_list_field(block: str, key: str) -> list[str]:
    """Return a comma-separated list field as a Python list."""
    val = _get_field(block, key)
    if not val:
        return []
    return [v.strip() for v in val.split(",") if v.strip()]


def parse_card(content: str, filename: str) -> CardData:
    """Parse a board card markdown file into a :class:`CardData`.

    Tolerant of missing or malformed sections — never raises on bad input.
    """
    # --- Task ID from filename: TWA-37_slug.md -> TWA-37 ---
    id_match = re.match(r"^([A-Z]+-\d+)", filename)
    task_id = id_match.group(1) if id_match else filename.removesuffix(".md")

    # --- Title from first H1 ---
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else task_id

    # --- Status block ---
    status_block = extract_section(content, "Status")
    status_val = _get_field(status_block, "Status") or ""

    # Fall back for old-style plain-text status blocks (e.g. TWA-001)
    if not status_val:
        plain = re.search(
            r"^\s*(In Progress|Completed|Todo|Backlog|Blocked|Done)\s*$",
            status_block,
            re.MULTILINE | re.IGNORECASE,
        )
        status_val = plain.group(1) if plain else ""

    # --- Action items ---
    action_block = extract_section(content, "Action Items")
    action_items = re.findall(r"^\s*-\s+\[[ xX]\]\s+.+$", action_block, re.MULTILINE)

    return CardData(
        task_id=task_id,
        filename=filename,
        title=title,
        status=status_val,
        assignee=_get_field(status_block, "Assignee") or "",
        start_time=_get_field(status_block, "Start Time") or "",
        end_time=_get_field(status_block, "End Time") or "",
        milestone=_get_field(status_block, "Milestone"),
        claimed_by=_get_field(status_block, "Claimed By"),
        claimed_at=_get_field(status_block, "Claimed At"),
        depends_on=_get_list_field(status_block, "Depends On"),
        blocks=_get_list_field(status_block, "Blocks"),
        action_items=action_items,
        content=content,
    )


def set_card_field(content: str, key: str, value: str) -> str:
    """Set or add a ``- **Key:** value`` line in the ``## Status`` block.

    If the field already exists (case-insensitive match), it is updated in-place.
    Otherwise the line is prepended inside the ``## Status`` block.
    If no Status block exists, one is created after the H1 title.
    """
    escaped = re.escape(key)
    existing = re.compile(
        rf"^\s*-\s+\*\*{escaped}:\*\*\s*.*$",
        re.MULTILINE | re.IGNORECASE,
    )
    if existing.search(content):
        return existing.sub(f"- **{key}:** {value}", content, count=1)

    # Prepend into existing ## Status block
    status_header = re.compile(r"^(##\s+Status\s*\n)", re.MULTILINE)
    m = status_header.search(content)
    if m:
        pos = m.end()
        return content[:pos] + f"- **{key}:** {value}\n" + content[pos:]

    # No Status block — create one after the H1
    title_line = re.search(r"^#\s+.+\n", content, re.MULTILINE)
    if title_line:
        pos = title_line.end()
        section = f"\n## Status\n- **{key}:** {value}\n"
        return content[:pos] + section + content[pos:]

    # Last resort: append at end
    return content.rstrip("\n") + f"\n\n## Status\n- **{key}:** {value}\n"


def remove_card_field(content: str, key: str) -> str:
    """Remove a ``- **Key:** value`` line from a card (first occurrence)."""
    escaped = re.escape(key)
    pattern = re.compile(
        rf"^\s*-\s+\*\*{escaped}:\*\*\s*.*\n?",
        re.MULTILINE | re.IGNORECASE,
    )
    return pattern.sub("", content, count=1)
