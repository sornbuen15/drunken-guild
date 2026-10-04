# mypy: ignore-errors
"""DG-359. `install_skills.sh` (and `install_skills.ps1`, which had no
equivalent reporting at all) copy skills in and never prune. An install run
after the 2.0.0 re-scope left 34 retired skill directories installed beside
the 11 this repository ships, and nothing removed them.

"An agent does not delete" (CLAUDE.md) applies here too, least of all in the
operator's home: pruning is opt-in and dry-run by default.

  (no flag)              -- unchanged: report extras, remove nothing
  --prune / -Prune        -- list what would be removed, remove nothing
  --prune --prune-apply   -- remove exactly what --prune listed
  -Prune -PruneApply

`--prune-apply` / `-PruneApply` alone, without the list-first flag, is
refused rather than treated as "prune and apply at once" — nothing here
decides to delete without first being told what it would delete.

Every test here runs the real installer against a sandboxed `$HOME` /
`HOME` under `tmp_path`; none of it ever reads or writes the operator's own
`~/.claude`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Git for Windows' own bash, found explicitly. `shutil.which("bash")` on this
#: Windows workstation can resolve to the WSL launcher at
#: `C:\Windows\System32\bash.exe` instead, which fails outright ("execvpe
#: .../bash) failed") the moment `$HOME` is redirected into a plain Windows
#: temp path it cannot translate. On Linux, where CI actually runs this
#: script, `bash` on PATH is simply bash, and the explicit path below does
#: not exist — that branch falls back to `shutil.which`.
_GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
BASH = str(_GIT_BASH) if _GIT_BASH.is_file() else shutil.which("bash")

POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

SH_SCRIPT = REPO_ROOT / "scripts" / "install" / "install_skills.sh"
PS1_SCRIPT = REPO_ROOT / "scripts" / "install" / "install_skills.ps1"


def _sandbox(tmp_path: Path, leftover: bool = True) -> tuple[Path, Path]:
    """A repo copy and a `home` directory, both under *tmp_path*.

    Never the operator's own checkout or `~/.claude` — this is the only
    `HOME` / `$HOME` any installer run in this file is ever pointed at.
    """
    sandbox = tmp_path / "repo"
    (sandbox / "scripts").mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "skills", sandbox / "skills")
    shutil.copytree(REPO_ROOT / "scripts" / "install", sandbox / "scripts" / "install")
    home = tmp_path / "home"
    home.mkdir()
    if leftover:
        leftover_dir = home / ".claude" / "skills" / "leftover-skill"
        leftover_dir.mkdir(parents=True)
        (leftover_dir / "SKILL.md").write_text("a retired skill\n", encoding="utf-8")
    return sandbox, home


def _leftover_path(home: Path) -> Path:
    return home / ".claude" / "skills" / "leftover-skill"


def _run_sh(sandbox: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    script = sandbox / "scripts" / "install" / "install_skills.sh"
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run(
        [BASH, str(script), *args], capture_output=True, text=True, env=env
    )


def _run_ps1(
    sandbox: Path, home: Path, extra_args: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run `install_skills.ps1` with `$HOME` redirected, guarded by a canary.

    Same shape as `test_install_index_determinism.py`'s helper: the canary
    confirms `$HOME` was actually redirected *inside* the child process
    before the installer runs at all, so a redirection that silently failed
    cannot result in this test trusting a run against the operator's real
    `~/.claude`.
    """
    assert POWERSHELL is not None
    script = sandbox / "scripts" / "install" / "install_skills.ps1"
    command = (
        f"Set-Variable -Name HOME -Value '{home}' -Force -Scope Global; "
        f"$canary = $HOME; "
        f'Write-Host "CANARY:$canary"; '
        f"if ($canary -ne '{home}') {{ "
        f"Write-Host 'CANARY MISMATCH -- aborting, running nothing'; exit 97 "
        f"}}; "
        f"& '{script}' {extra_args}"
    ).strip()
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
    )
    assert f"CANARY:{home}" in result.stdout, (
        "the canary never confirmed $HOME inside the child process — this "
        "test cannot trust what the run did\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert result.returncode != 97, (
        "HOME redirection did not take effect; aborted before the installer "
        f"ran\n{result.stdout}\n{result.stderr}"
    )
    return result


@pytest.mark.skipif(BASH is None, reason="no bash on this machine")
class TestTheShInstallerPrunesOnlyOnRequest:
    def test_the_default_run_reports_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _leftover_path(home).is_dir(), (
            "a plain run with no flag removed an installed directory — "
            "pruning must be opt-in"
        )
        assert "leftover-skill" in result.stdout
        assert "Installed but not produced here" in result.stdout

    def test_prune_alone_lists_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home, "--prune")

        assert result.returncode == 0, result.stdout + result.stderr
        assert _leftover_path(home).is_dir(), (
            "--prune without --prune-apply must be dry-run: it removed the "
            "directory it only claimed it would remove"
        )
        assert "leftover-skill" in result.stdout
        assert "Would remove" in result.stdout

    def test_prune_and_prune_apply_together_remove_it(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _leftover_path(home).exists(), (
            "--prune --prune-apply named the directory and should have "
            "removed exactly it"
        )

    def test_prune_apply_alone_is_refused(self, tmp_path):
        """No flag may delete by itself — the list-first flag is mandatory."""
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home, "--prune-apply")

        assert result.returncode != 0
        assert _leftover_path(home).is_dir(), (
            "--prune-apply alone deleted something before being refused"
        )

    def test_index_only_and_prune_together_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path, leftover=False)
        result = _run_sh(sandbox, home, "--index-only", "--prune")

        assert result.returncode != 0
        assert not (home / ".claude").exists(), (
            "--index-only must never create the install target, prune or not"
        )

    def test_a_clean_install_with_nothing_extra_still_exits_zero(self, tmp_path):
        """Regression guard for the `xargs -n1 basename` portability bug this
        ticket also had to clear to make the above tests runnable at all:
        some xargs implementations invoke the command once, with no operand,
        on zero input rather than running it zero times, and under
        `set -o pipefail` that failed every ordinary, nothing-to-report run."""
        sandbox, home = _sandbox(tmp_path, leftover=False)
        result = _run_sh(sandbox, home)

        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
class TestThePs1InstallerPrunesConsistentlyWithTheShOne:
    """install_skills.ps1 had no orphan reporting at all before DG-359 — not
    even the read-only report install_skills.sh already had. Same flags, same
    gating, ported across."""

    def test_the_default_run_reports_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _leftover_path(home).is_dir()
        assert "leftover-skill" in result.stdout
        assert "Installed but not produced here" in result.stdout

    def test_prune_alone_lists_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home, "-Prune")

        assert result.returncode == 0, result.stdout + result.stderr
        assert _leftover_path(home).is_dir()
        assert "Would remove" in result.stdout

    def test_prune_and_prune_apply_together_remove_it(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _leftover_path(home).exists()

    def test_prune_apply_alone_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home, "-PruneApply")

        assert result.returncode != 0
        assert _leftover_path(home).is_dir()

    def test_index_only_and_prune_together_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path, leftover=False)
        result = _run_ps1(sandbox, home, "-IndexOnly -Prune")

        assert result.returncode != 0
        assert not (home / ".claude").exists()
