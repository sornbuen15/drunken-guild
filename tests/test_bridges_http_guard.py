# mypy: ignore-errors
"""The two bridges must not open a URL the scheme guard never saw — DG-325.

`core/http.py` exists for one reason, stated in its own docstring: `urlopen`
honours every scheme its openers know about, so a URL arriving from
configuration is not merely a network destination. `file:///etc/passwd` is a
valid argument and the body comes back looking exactly like an API response.
CLAUDE.md turns that into a rule — every outbound HTTP call goes through
`core/http.py`, with one `# nosec` on the guard itself.

Both bridges were missed. They called `urllib.request.urlopen` directly, and
nothing caught it because CI runs `bandit -r src -ll` while `pyproject.toml`
ships `scripts` as a package: a whole tree of shipped code that has never been
scanned.

The test below is deliberately not "does it print a different error". Before the
fix these bridges *succeed* on a `file://` URL and hand back the file's contents
as a parsed API response. That is the hole, so that is what is asserted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import confluence_bridge  # noqa: E402
import jira_bridge  # noqa: E402


@pytest.fixture()
def local_file(tmp_path):
    """A local file whose contents must never come back from an API call."""
    path = tmp_path / "stolen.json"
    path.write_text(json.dumps({"secret": "read-off-the-local-disk"}), "utf-8")
    return path


class TestAFileUrlIsNeverOpened:
    def test_the_jira_bridge_refuses_it(self, local_file, capsys) -> None:
        """Before the fix this returned {"secret": …} — the file's own contents,
        parsed as JSON, indistinguishable at the call site from a Jira
        response."""
        with pytest.raises(SystemExit):
            jira_bridge.make_request(f"file://{local_file}", email="a@b.c", token="x")
        assert "read-off-the-local-disk" not in capsys.readouterr().out

    def test_the_confluence_bridge_refuses_it(self, local_file, capsys) -> None:
        with pytest.raises(SystemExit):
            confluence_bridge.make_request(
                f"file://{local_file}", email="a@b.c", token="x"
            )
        assert "read-off-the-local-disk" not in capsys.readouterr().out

    @pytest.mark.parametrize("scheme", ["file", "ftp"])
    def test_the_refusal_names_the_scheme(self, tmp_path, scheme, capsys) -> None:
        """ "Request failed" sends the reader looking for a network problem. The
        guard already words this well; the bridges only have to let it through.

        Asserting the guard's own wording, not just the scheme string: a urlopen
        failure also echoes the URL back, so `scheme in stderr` alone passed
        before the fix existed and measured nothing.
        """
        with pytest.raises(SystemExit):
            jira_bridge.make_request(
                f"{scheme}://{tmp_path}/x.json", email="a@b.c", token="x"
            )
        err = capsys.readouterr().err
        assert f"{scheme!r} is not allowed" in err, err


class TestOnlyOneUrlopenInTheCodebase:
    def test_no_module_opens_a_url_outside_the_guard(self) -> None:
        """The rule is not "the bridges are fixed", it is "there is one place
        that opens a URL". A second one added later is the same defect again."""
        offenders = []
        for path in [*(REPO / "src").rglob("*.py"), *(REPO / "scripts").rglob("*.py")]:
            if path == REPO / "src" / "core" / "http.py":
                continue
            if "urllib.request.urlopen" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(REPO)))
        assert not offenders, (
            "These open a URL without the scheme guard in core/http.py:\n  "
            + "\n  ".join(offenders)
        )


class TestTheScanCoversWhatIsShipped:
    def test_bandit_scans_every_packaged_tree(self) -> None:
        """`pyproject.toml` ships `scripts` alongside the `src/` packages, so a
        scan of `src` alone leaves shipped code unscanned. That is how three
        HIGH-confidence findings sat there unreported."""
        workflow = (REPO / ".github/workflows/test.yml").read_text(encoding="utf-8")
        bandit_lines = [
            line.strip() for line in workflow.splitlines() if "bandit -r" in line
        ]
        assert bandit_lines, "no bandit invocation found in the workflow"
        for line in bandit_lines:
            assert "scripts" in line, f"bandit does not scan scripts/: {line!r}"


class TestGitignoreCoversTheObviousMistakes:
    @pytest.mark.parametrize("pattern", ["*.bak", "secrets.json"])
    def test_a_pattern_is_present(self, pattern) -> None:
        """Neither is where a real credential lives — `~/.drunken/secrets.json`
        is outside any checkout. Both are where one gets copied to "just for a
        minute", which is the same story `.env` already has a rule for."""
        lines = [
            line.strip()
            for line in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        ]
        assert pattern in lines
