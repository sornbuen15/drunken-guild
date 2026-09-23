# mypy: ignore-errors
"""DG-312. A comment that says "tracked separately" must name the ticket.

pyproject.toml pinned `mcp<2` and said the 2.x migration was "tracked
separately". A Jira search found no such ticket — only the long-closed 1.x
adoption (DG-65, DG-182). A claim of tracking with no key is a promise nobody
can check, and it reads to the next person as "someone has this".
"""

import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
CLAIM = re.compile(r"tracked (separately|elsewhere|in a separate)", re.I)


def test_every_tracking_claim_names_its_ticket() -> None:
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines()
    bad = [
        f"pyproject.toml:{n}"
        for n, line in enumerate(lines, 1)
        if CLAIM.search(line) and not re.search(r"\bDG-\d+\b", line)
    ]
    assert not bad, f"claims tracking without a ticket key: {bad}"
