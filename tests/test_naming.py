# mypy: ignore-errors
"""The product is drunken-guild. Nothing we own should still say otherwise.

This file used to guard two names. The first was ``agy`` — Antigravity's CLI,
which the Discord router dispatched work to, and a pid file, a log name and a
launchd label that were ours and still carried the old product name. Both halves
are retired now: the Antigravity plumbing in DG-349, the daemon that invoked it
in DG-355, so the direction those tests pinned no longer has a subject.

What is left is the sweep that has no expiry date. DG-274 renamed the package
and stopped: 61 files citing dead ticket keys, five templates that other
projects copy naming the old product. A sweep has a shelf life; this does not.
"""

import re
import subprocess
from pathlib import Path

import pytest  # noqa: F401 - kept for the parametrized guards added here later

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# DG-274 — the rest of the old identity
# ---------------------------------------------------------------------------

#: The board was renamed from `DT` to `DG` and the issues kept their numbers, so
#: every `DT-nnn` left in the tree is a key that finds nothing when searched. 61
#: files carried one, including the ticket-writing rules themselves.
OLD_TICKET_PREFIX = re.compile(r"\bDT-\d")

#: The product. `Drunken Team Inn`, `Drunken-Team`, `drunken-ai-team` and
#: `Drunken-Agy` are all names this project has stopped going by.
OLD_PRODUCT = re.compile(r"Drunken[- ]Team|drunken-ai-team|Drunken-Agy|drunken_agy\b")

#: Lines allowed to keep `drunken-team` in lower case, because each names a real
#: thing that still exists rather than describing this project:
#:
#:   * `~/Projects/drunken-team` — the fallback checkout, under standing
#:     instruction not to be touched. Naming it is the instruction.
#:   * `uv tool uninstall drunken-team` — the remedy a reader has to run.
#:   * `uv/tools/drunken-team` — the legacy tool root doctor looks for.
#:   * the accounts of DG-266 and DG-268, which cannot describe the bug without
#:     naming what the code used to say.
#:   * the registry's own project list. `drunken-team` is a live key in
#:     `~/.drunken/projects.json`, pointing at the fallback checkout this repo is
#:     under standing instruction to keep. Reporting what the registry holds has
#:     to report that key.
#:   * DG-306's fixture and finding, which needs a second live registry key
#:     distinct from `drunken-guild` to demonstrate the multi-project bug --
#:     `drunken-team` is the real one that actually exposed it.
LOWERCASE_ALLOWED = (
    "~/Projects/drunken-team",
    "uv tool uninstall drunken-team",
    "uv/tools/drunken-team",
    "drunken-team v2.1.0",
    "drunken_team 1.6.0",
    "drunken_agy 1.1.0",
    'tmp_path / "drunken-team"',
    "still owns those names",
    "from `drunken-team` to `drunken-guild`",
    "naming ``drunken-team``",
    "`drunken-team`, the fallback",
    "drunken-team/src",
    "`drunken-guild`, `drunken-team`, `beta`, `alpha`",
    '"drunken-team": {',
)

#: Records exist to name what was retired, so they are exempt wholesale.
RECORD_PREFIXES = ("_not_used/",)

#: The two files that cannot do their job without writing the old names down.
#: This one holds the patterns; `check_doc_drift.py` holds the list of retired
#: strings it greps documentation for. A guard that forbade its own subject
#: would be a guard nobody could write.
SELF_EXEMPT = frozenset({"tests/test_naming.py", "scripts/check_doc_drift.py"})


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return [
        f
        for f in out.stdout.split()
        if not f.startswith(RECORD_PREFIXES) and f not in SELF_EXEMPT
    ]


def _offenders(pattern: re.Pattern) -> list[str]:
    hits = []
    for relative in _tracked_files():
        path = REPO_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and not any(k in line for k in LOWERCASE_ALLOWED):
                hits.append(f"{relative}:{n}: {line.strip()[:100]}")
    return hits


class TestTheOldIdentityIsGone:
    """DG-274. The rename stopped at the package name and left the rest.

    A sweep has a shelf life; a test does not. Each of these was a real finding,
    not a hypothetical: 61 files citing dead ticket keys, five templates that
    other projects copy naming the old product, two install scripts telling a
    user to check they were in a repository that no longer exists.
    """

    def test_no_dead_ticket_keys(self) -> None:
        hits = _offenders(OLD_TICKET_PREFIX)
        assert not hits, (
            "The board is DG and these keys find nothing when searched:\n  "
            + "\n  ".join(hits)
        )

    def test_no_old_product_name(self) -> None:
        hits = _offenders(OLD_PRODUCT)
        assert not hits, "The product is drunken-guild:\n  " + "\n  ".join(hits)

    def test_lowercase_survivors_are_all_deliberate(self) -> None:
        """`drunken-team` in lower case is allowed only where it names something
        that really exists — the fallback checkout, the uninstall remedy, the
        legacy tool root, or the account of a bug that cannot be told without
        it. Anything else is a leftover."""
        hits = _offenders(re.compile(r"drunken[-_]team"))
        assert not hits, (
            "Add to LOWERCASE_ALLOWED with the reason, or use the new name:\n  "
            + "\n  ".join(hits)
        )
