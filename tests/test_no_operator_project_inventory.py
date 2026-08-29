"""DG-317: this repository must not carry the operator's project inventory.

drunken-guild is public and MIT-licensed. What belongs in it is *how to use
drunken-guild* -- not which projects the operator happens to run with it, and
that includes the code, the tests and the docstrings. Nothing here is secret:
every channel id in git is a placeholder, there are no machine paths, and the
only personal email is the deliberate security contact in SECURITY.md. This is
about not publishing a project list, which is smaller than a leak and still not
the toolkit's to publish.

**This guard names no project.** Hardcoding the ids would put them back into a
tracked file, which is the thing being prevented. Instead it reads the
operator's own registry and asserts that no registered project id other than
this repository's own appears in tracked content. That also means it keeps
working when the operator's projects change, and it skips on CI and on a fresh
clone, where there is no registry to read and nothing to leak.

Use `alpha` and `beta` as placeholders, the convention DG-316 set in the guide.
Where a name would be doing real explanatory work, describe the *role* instead
-- "a consuming project's wrapper directory" says more to a stranger than a
directory name they do not have.
"""

import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

#: This repository's own key is expected everywhere and is not inventory.
OWN_KEY = "drunken-guild"

#: Below this, an id is too generic to match on without constant false
#: positives -- a project called "ci" or "api" would fire on ordinary prose.
#: Such an id is also not much of a disclosure.
MIN_ID_LENGTH = 3


def _registered_project_ids() -> list[str]:
    """Other projects on this machine, or an empty list when there is no registry."""
    try:
        from core.registry import ProjectRegistry

        ids = list(ProjectRegistry().get_projects())
    except Exception:
        return []
    return [i for i in ids if i != OWN_KEY and len(i) >= MIN_ID_LENGTH]


def _tracked_text_files() -> list[str]:
    """Every tracked file, listed by git.

    `git ls-files | xargs grep` rather than `git grep`: on the DG-317 sweep
    `git grep` returned a false negative, missing hits in a file it should have
    matched. Do not trust it alone to clear a privacy scan.
    """
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [f for f in out.stdout.split("\n") if f]


def _hits(project_id: str, files: list[str]) -> list[str]:
    # Not preceded or followed by a letter, so `ALPHA-40`, `JIRA_TOKEN_ALPHA` and
    # `project.alpha.jira` all count while `software` and `outward` do not --
    # both of those contain a project id as a substring and are innocent.
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(project_id)}(?![A-Za-z])", re.I)
    found = []
    for rel in files:
        path = os.path.join(REPO_ROOT, rel)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: nothing to read a name out of
        for n, line in enumerate(content.split("\n"), 1):
            if pattern.search(line):
                found.append(f"{rel}:{n}")
    return found


@pytest.mark.skipif(  # type: ignore[misc]
    not _registered_project_ids(),
    reason="no other project registered on this machine — nothing to leak",
)
def test_no_registered_project_id_appears_in_tracked_files() -> None:
    files = _tracked_text_files()
    offenders: dict[str, list[str]] = {}
    for project_id in _registered_project_ids():
        hits = _hits(project_id, files)
        if hits:
            offenders[project_id] = hits

    assert not offenders, (
        "A registered project id appears in tracked content. This repository is "
        "public; the operator's project list is not part of what it publishes. "
        "Use 'alpha'/'beta', or describe the role instead of naming it.\n"
        + "\n".join(
            f"  {pid}: {len(h)} occurrence(s), first at {h[0]}"
            for pid, h in offenders.items()
        )
    )


def test_the_guard_would_actually_catch_one(tmp_path: object) -> None:
    """The assertion above passes trivially if `_hits` never matches anything.

    A guard nobody has seen fire is a guard that may be checking the wrong
    thing -- so match a known-present string with the same machinery, and
    confirm the substring exclusions hold.
    """
    files = _tracked_text_files()
    assert _hits("drunken-guild", files), "the matcher found nothing at all"

    # `software` contains an id as a substring in the real inventory; the
    # boundary rule is what stops it firing, and it is the part most likely to
    # be loosened by accident later.
    assert not _hits("oftwar", files), "the boundary rule stopped rejecting substrings"
