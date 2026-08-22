"""Read the state of the work, instead of typing it into a file.

DG-257. ``SESSION_CHECKPOINT.md`` section 2 -- branch, test count, open PRs,
ticket states -- went stale within an hour of being written, and the file itself
records that the section "has been wrong twice, in both directions". While this
module was being written it was stale again: it named three PRs as awaiting
merge that had all merged, and a test count 49 behind.

Every session was opening by hand-verifying the same four things. The parts that
go stale are exactly the parts that are derivable, so they should be derived.
What stays hand-written is what cannot be: what was decided, and why.

**Read-only.** It reports. It does not write the checkpoint, and it does not
touch Jira beyond a search. Nothing here acquires a schedule -- same rule as
DG-252, a check that answers when asked.

**Every source can be absent, and says so.** ``gh`` may not be installed, Jira
may not answer, a checkout may have no tags. None of those are reported as an
empty result: "could not ask" and "the answer is nothing" are different facts,
and collapsing them is how a board came to read as empty for months (S4).
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - git and gh, invoked with fixed argument lists
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .context import ProjectContext
from .registry import ProjectRegistry

#: Long enough for a cold `gh` call or a Jira round trip, short enough that a
#: hung network does not hold a status report open indefinitely.
TIMEOUT_SECONDS = 60


@dataclass
class Section:
    """One answerable question, and whether it could be answered.

    ``available=False`` with a stated ``reason`` is the whole point of the
    class: a report that silently omits what it could not reach is worse than
    one that says so.
    """

    name: str
    available: bool = True
    reason: str = ""
    rows: List[str] = field(default_factory=list)
    data: Any = None


def _run(argv: List[str], cwd: Optional[Path] = None) -> Optional[str]:
    """Stdout of *argv*, or ``None`` if it could not be run or failed."""
    try:
        result = subprocess.run(  # nosec B603 - fixed argv, no shell
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_section(git_root: Path) -> Section:
    """Where the branches are, and whether local agrees with origin."""
    section = Section("git")
    head = _run(["git", "rev-parse", "--short", "HEAD"], git_root)
    if head is None:
        section.available = False
        section.reason = f"{git_root} did not answer as a git repository."
        return section

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], git_root) or "?"
    origin_main = _run(["git", "rev-parse", "--short", "origin/main"], git_root)
    origin_dev = _run(["git", "rev-parse", "--short", "origin/develop"], git_root)
    newest_tag = next(
        iter((_run(["git", "tag", "--sort=-v:refname"], git_root) or "").split()), None
    )

    # Counted, not guessed from the branch name. "My branch is called develop"
    # and "my branch is where origin/develop is" are different claims, and the
    # second is the one that decides whether something is really merged.
    ahead = behind = None
    counts = _run(
        ["git", "rev-list", "--left-right", "--count", "origin/develop...HEAD"],
        git_root,
    )
    if counts and len(counts.split()) == 2:
        behind, ahead = (int(part) for part in counts.split())

    if behind == 0 and ahead == 0:
        position = "level with `origin/develop`"
    elif behind is None:
        position = "position against `origin/develop` unknown"
    else:
        position = f"**{ahead} ahead, {behind} behind** `origin/develop`"

    section.data = {
        "branch": branch,
        "head": head,
        "origin_main": origin_main,
        "origin_develop": origin_dev,
        "newest_tag": newest_tag,
        "ahead": ahead,
        "behind": behind,
    }
    section.rows = [
        f"| `main` | `{origin_main or 'unknown'}`"
        f"{f' — newest tag {newest_tag}' if newest_tag else ''} |",
        f"| `origin/develop` | `{origin_dev or 'unknown'}` |",
        f"| local `{branch}` | `{head}` — {position} |",
    ]
    return section


def pr_section(git_root: Path) -> Section:
    """Open pull requests, via ``gh``."""
    section = Section("pull requests")
    raw = _run(
        ["gh", "pr", "list", "--state", "open", "--json", "number,title,headRefName"],
        git_root,
    )
    if raw is None:
        section.available = False
        section.reason = (
            "`gh` is not installed, not authenticated, or this checkout has no "
            "GitHub remote. Not the same as having no open PRs."
        )
        return section

    try:
        prs = json.loads(raw)
    except json.JSONDecodeError:
        section.available = False
        section.reason = "`gh` returned something that is not JSON."
        return section

    section.data = prs
    section.rows = (
        [f"| #{pr['number']} | {pr['title']} |" for pr in prs]
        if prs
        else ["| — | none open |"]
    )
    return section


def jira_section(project_id: str) -> Section:
    """Everything not Done, grouped by status, with who holds it."""
    section = Section("jira")
    try:
        # Lazily imported, and reused rather than reimplemented: a second Jira
        # client here would be a second surface that can disagree with the
        # first, which is the failure DG-250 spent a session curing.
        from jira_mcp.jira_client import JiraClient
        from jira_mcp.jql import scope_to_project

        client = JiraClient(ProjectContext.build(project_id))
        issues = asyncio_run(
            client.search_issues(
                scope_to_project(
                    "statusCategory != Done ORDER BY key ASC", client.project_key
                )
            )
        )
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        section.available = False
        section.reason = f"could not ask Jira: {exc}"
        return section

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        grouped.setdefault(str(issue.get("status")), []).append(issue)

    section.data = grouped
    for status, rows in sorted(grouped.items()):
        listed = ", ".join(
            f"{row['key']}"
            + ("" if row.get("assignee") == "Unassigned" else f" ({row['assignee']})")
            for row in rows
        )
        section.rows.append(f"| **{status}** | {listed} |")
    if not section.rows:
        section.rows = ["| — | nothing open |"]
    return section


def asyncio_run(coro: Any) -> Any:
    """``asyncio.run``, imported here so the module stays cheap to import."""
    import asyncio

    return asyncio.run(coro)


def test_section(git_root: Path) -> Section:
    """The suite's real result, only ever by running it.

    Opt-in. A test count is a fact if it was measured this minute and a rumour
    otherwise, and reprinting a remembered number is the habit this whole
    command exists to break.
    """
    section = Section("tests")
    raw = _run(["uv", "run", "pytest", "-q", "--no-cov"], git_root)
    if raw is None:
        section.available = False
        section.reason = "the suite did not run, or it failed. Run it directly."
        return section

    summary = next(
        (
            line
            for line in reversed(raw.splitlines())
            if "passed" in line or "failed" in line
        ),
        "",
    )
    section.data = summary
    section.rows = [f"| tests | {summary.strip('= ')} |"]
    return section


def render(sections: List[Section]) -> str:
    """The sections as markdown, shaped to be pasted into the checkpoint."""
    out = ["## Where things stand", "", "| | |", "|---|---|"]
    for section in sections:
        if section.available:
            out.extend(section.rows)
        else:
            out.append(f"| {section.name} | *not answered — {section.reason}* |")
    out.append("")
    out.append(
        "Derived by `drunken-status`. Nothing here was typed; anything it could "
        "not reach says so above rather than being left out."
    )
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drunken-status",
        description=(
            "Report the state of the work from git, GitHub and Jira, so the "
            "checkpoint does not have to carry a copy of it."
        ),
    )
    parser.add_argument(
        "--project",
        help="Registered project id. Defaults to the only one, if there is only one.",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Run the suite and report its real result. Off by default: it takes time.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    return parser


def _resolve_project(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    projects = list(ProjectRegistry().get_projects())
    return projects[0] if len(projects) == 1 else None


def main() -> int:
    args = build_parser().parse_args()

    project_id = _resolve_project(args.project)
    if project_id is None:
        print(
            "error: more than one project is registered, so --project is needed "
            "to say which one's board to read.",
            file=sys.stderr,
        )
        return 2

    try:
        git_root = ProjectContext.build(project_id).git_root_path()
    except Exception:
        git_root = Path.cwd()

    sections = [git_section(git_root), pr_section(git_root), jira_section(project_id)]
    if args.tests:
        sections.append(test_section(git_root))

    if args.json:
        print(
            json.dumps(
                {
                    section.name: {
                        "available": section.available,
                        "reason": section.reason,
                        "data": section.data,
                    }
                    for section in sections
                },
                indent=2,
            )
        )
        return 0

    print(render(sections))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
