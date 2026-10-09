# DG-485. The Windows workstation's system-level git config sets
# core.autocrlf=true while the repo's own config says false; without a
# .gitattributes pinning line endings, that system setting rewrites a
# worktree to CRLF on anything that touches it (a stash round trip, the
# Edit tool), producing whole-file diffs on an index that is already LF.
#
# This test reads the committed file's own text -- it must NOT depend on
# the machine's git config (core.autocrlf, core.eol) or on `git check-attr`,
# because the whole point is that those machine settings are exactly what
# .gitattributes must override. A plain content check fails the same way
# on every machine, which is what proves it is testing the fix and not the
# environment it runs in.

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GITATTRIBUTES = REPO_ROOT / ".gitattributes"


def test_gitattributes_file_exists() -> None:
    assert GITATTRIBUTES.is_file(), (
        "no root .gitattributes -- the system autocrlf=true setting can "
        "rewrite a worktree's line endings with nothing to stop it (DG-485)"
    )


def test_gitattributes_pins_the_default_rule_to_lf() -> None:
    text = GITATTRIBUTES.read_text(encoding="utf-8")
    default_rules = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("*") and not line.strip().startswith("*.")
    ]
    assert default_rules, (
        "no catch-all `*` rule in .gitattributes -- files not covered by a "
        "specific pattern fall back to the machine's own autocrlf setting"
    )
    assert any("eol=lf" in rule for rule in default_rules), (
        f"the catch-all rule(s) {default_rules!r} do not pin eol=lf -- a "
        "text file with no more specific rule is left to the machine's own "
        "autocrlf setting, which is the exact bug DG-485 reports"
    )


def test_gitattributes_keeps_shell_scripts_lf() -> None:
    """*.sh must stay LF: a CRLF shebang line fails with
    '/bin/sh^M: bad interpreter' under WSL, Git Bash and CI runners."""
    text = GITATTRIBUTES.read_text(encoding="utf-8")
    sh_rules = [
        line.strip() for line in text.splitlines() if line.strip().startswith("*.sh")
    ]
    assert sh_rules, "no *.sh rule in .gitattributes"
    assert all("eol=lf" in rule for rule in sh_rules), (
        f"*.sh rule(s) {sh_rules!r} do not pin eol=lf"
    )
