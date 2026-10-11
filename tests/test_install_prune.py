# mypy: ignore-errors
"""DG-359. `install_skills.sh` (and `install_skills.ps1`, which had no
equivalent reporting at all) copy skills in and never prune.

Review finding #1, confirmed by reproduction: the first cut of this feature
pruned ANY directory that was not one of this repository's own skills, and
`--prune --prune-apply` deleted a hand-written, never-shipped skill because
the only test it applied was "has SKILL.md and is not in ours + .external".
Pruning now removes ONLY names listed on
`scripts/install/retired_skills.txt` — the tracked list of skills this
repository actually shipped and withdrew. Anything else unshipped is
reported "unrecognised" and is never removed automatically.

Review finding #2, confirmed by reproduction on this machine: a symlink (real
Windows symlink via `os.symlink`, and a real Windows junction via
`New-Item -ItemType Junction`) sharing a name with a retired skill is never
followed or removed — both installers check for a link before every
`rm -rf` / `Remove-Item`, and both report "(link, not touched)" instead.

Review finding #3: an empty or unset `$HOME`/`$env:USERPROFILE` is refused
outright rather than silently resolving relative to the wrong directory.

"An agent does not delete" (CLAUDE.md) applies here too, least of all in the
operator's home: pruning is opt-in and dry-run by default.

  (no flag)              -- unchanged: report extras, remove nothing
  --prune / -Prune        -- list what --prune-apply would remove, remove nothing
  --prune --prune-apply   -- remove ONLY orphans on retired_skills.txt
  -Prune -PruneApply

`--prune-apply` / `-PruneApply` alone, without the list-first flag, is
refused rather than treated as "prune and apply at once".

Every test here runs the real installer against a sandboxed `$HOME` /
`HOME` under `tmp_path`; none of it ever reads or writes the operator's own
`~/.claude`. The `.ps1` tests depend on the script actually reading `$HOME`
(redirected via `Set-Variable -Scope Global` before the script runs, in the
same child process) — the canary in `_run_ps1` exists specifically to prove
that redirection took effect before trusting anything the run did.
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

#: A name genuinely on scripts/install/retired_skills.txt (not one of the 16
#: that also live under plugins/drunken-extras/skills/, so it is
#: unambiguously "retired" and never "moved").
A_RETIRED_NAME = "ai-output"

#: Never on the retired list: a stand-in for a hand-written skill that has
#: nothing to do with this repository. This is exactly what review finding
#: #1 reproduced getting deleted.
AN_UNRECOGNISED_NAME = "my-custom-skill"


def _sandbox(tmp_path: Path, seed: bool = True) -> tuple[Path, Path]:
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
    if seed:
        for name, content in (
            (A_RETIRED_NAME, "a retired skill\n"),
            (AN_UNRECOGNISED_NAME, "mine, never shipped here\n"),
        ):
            skill_dir = home / ".claude" / "skills" / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return sandbox, home


#: A name genuinely on retired_skills.txt that is ALSO shipped today under
#: plugins/drunken-extras/skills/ in this actual repository -- not a
#: stand-in, the real thing review finding #1's doctor-side test already
#: covers (`test_a_retired_name_that_is_also_a_drunken_extras_skill_is_never_prunable`
#: in tests/test_ai_layer_drift.py). Picked by checking both real files
#: below, so a future edit to either list fails this loudly rather than
#: silently testing nothing.
A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS = "acronym-namer"


def _seed_extras_skill(sandbox: Path, name: str) -> None:
    """Ship *name* under plugins/drunken-extras/skills/ inside *sandbox*,
    where $PROJECT_ROOT/EXTRAS_DIR actually resolves for an installer run
    against this sandbox."""
    extras_dir = sandbox / "plugins" / "drunken-extras" / "skills" / name
    extras_dir.mkdir(parents=True)
    (extras_dir / "SKILL.md").write_text(
        "shipped under drunken-extras\n", encoding="utf-8"
    )


def _skill_path(home: Path, name: str) -> Path:
    return home / ".claude" / "skills" / name


def _retired_path(home: Path) -> Path:
    return _skill_path(home, A_RETIRED_NAME)


def _unrecognised_path(home: Path) -> Path:
    return _skill_path(home, AN_UNRECOGNISED_NAME)


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
    `~/.claude`. The installer itself reads plain `$HOME` (see
    `install_skills.ps1`'s `$GlobalSkillsDir = Join-Path $HOME ...`), which
    is exactly the variable this canary sets — if the script ever stopped
    reading `$HOME` directly, this redirection would stop working and the
    canary would not catch that; only the installer's own `-Prune`/report
    output pointing at the sandboxed path (asserted below) catches it.
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
class TestTheShInstallerPrunesOnlyKnownRetiredSkills:
    def test_the_default_run_reports_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _retired_path(home).is_dir()
        assert _unrecognised_path(home).is_dir()
        assert "Installed but not produced here" in result.stdout

    def test_prune_alone_lists_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home, "--prune")

        assert result.returncode == 0, result.stdout + result.stderr
        assert _retired_path(home).is_dir(), (
            "--prune without --prune-apply must be dry-run"
        )
        assert _unrecognised_path(home).is_dir()
        assert A_RETIRED_NAME in result.stdout
        assert "Would remove" in result.stdout
        assert "Unrecognised, never pruned" in result.stdout
        assert AN_UNRECOGNISED_NAME in result.stdout

    def test_prune_apply_removes_only_the_retired_one(self, tmp_path):
        """The literal regression review finding #1 reproduced: before this
        fix, `--prune --prune-apply` deleted anything unshipped. A custom
        skill that was never on retired_skills.txt must survive."""
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _retired_path(home).exists(), (
            "a name on retired_skills.txt should have been removed"
        )
        assert _unrecognised_path(home).is_dir(), (
            "a name NOT on retired_skills.txt must never be removed by "
            "--prune-apply — this is exactly what was deleted before the fix"
        )

    def test_prune_apply_alone_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_sh(sandbox, home, "--prune-apply")

        assert result.returncode != 0
        assert _retired_path(home).is_dir()
        assert _unrecognised_path(home).is_dir()

    def test_index_only_and_prune_together_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path, seed=False)
        result = _run_sh(sandbox, home, "--index-only", "--prune")

        assert result.returncode != 0
        assert not (home / ".claude").exists()

    def test_a_clean_install_with_nothing_extra_still_exits_zero(self, tmp_path):
        """Regression guard for the `xargs -n1 basename` portability bug this
        ticket also had to clear: some xargs implementations invoke the
        command once, with no operand, on zero input rather than running it
        zero times, and under `set -o pipefail` that failed every ordinary,
        nothing-to-report run."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        result = _run_sh(sandbox, home)

        assert result.returncode == 0, result.stdout + result.stderr

    def test_retired_list_comments_and_blank_lines_are_ignored(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        retired_file = sandbox / "scripts" / "install" / "retired_skills.txt"
        retired_file.write_text(
            f"# a comment\n\n{A_RETIRED_NAME}\n\n", encoding="utf-8"
        )

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _retired_path(home).exists()

    def test_retired_list_crlf_line_endings_parse_the_same_as_lf(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        retired_file = sandbox / "scripts" / "install" / "retired_skills.txt"
        retired_file.write_bytes(f"# comment\r\n{A_RETIRED_NAME}\r\n".encode("utf-8"))

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _retired_path(home).exists(), (
            "a CRLF retired_skills.txt must parse the same as an LF one"
        )

    def test_mutation_removing_the_list_check_would_show_red(self, tmp_path):
        """Not a permanent mutation — a direct demonstration that this test
        file actually distinguishes the fixed behaviour from the broken one.
        Replaces the installed script with the pre-fix text that pruned any
        unshipped orphan (no retired-list check at all) and shows the exact
        assertion above would have failed against it."""
        sandbox, home = _sandbox(tmp_path)
        script = sandbox / "scripts" / "install" / "install_skills.sh"
        text = script.read_text(encoding="utf-8")

        # The mutation: treat every orphan as "retired" by making the
        # unrecognised bucket empty — i.e. undo the one check this ticket
        # added. If this substitution ever stops matching (the surrounding
        # code moved), the test fails loudly here rather than passing for
        # the wrong reason.
        marker = '_retired_orphans=$(comm -12 <(echo "$_orphans") <(printf \'%s\\n\' "$_retired" | sort -u))'
        assert marker in text, (
            "the retired-list check this test mutates is not where it expected"
        )
        mutated = text.replace(
            marker,
            '_retired_orphans="$_orphans"  # MUTATED: no retired-list check',
        )
        script.write_text(mutated, encoding="utf-8")

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _unrecognised_path(home).exists(), (
            "sanity check on the mutation itself: with the retired-list "
            "check removed, the unrecognised skill should be deleted too, "
            "proving the real check above is what protects it"
        )

    def test_a_symlink_sharing_a_retired_name_is_never_followed_or_removed(
        self, tmp_path
    ):
        """Review finding #2, confirmed by reproduction: a real symlink
        (`os.symlink`) pointed at a directory outside the skills tree,
        sharing a retired skill's name. `--prune-apply` must neither delete
        the symlink's target's contents nor remove the link itself."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        skills_dir.mkdir(parents=True)

        outside = tmp_path / "outside_target"
        outside.mkdir()
        (outside / "SKILL.md").write_text("precious\n", encoding="utf-8")
        (outside / "do-not-delete-me.txt").write_text("evidence\n", encoding="utf-8")

        link_path = skills_dir / A_RETIRED_NAME
        try:
            os.symlink(str(outside), str(link_path), target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"cannot create a real symlink on this machine: {exc}")

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "link, not touched" in result.stdout
        assert link_path.exists() or link_path.is_symlink(), (
            "the link itself must not be removed"
        )
        assert (outside / "SKILL.md").exists(), (
            "the link's target must never be recursed into or deleted"
        )
        assert (outside / "do-not-delete-me.txt").exists()

    def test_the_preview_names_the_file_count_and_flags_extra_content(self, tmp_path):
        """DG-450. The old output said only `"  $target"` for a retired
        directory about to be removed whole, whether it held the one
        SKILL.md this repository shipped or a user's own notes and
        subfolders alongside it -- no count, no warning, for either `--prune`
        (dry run) or `--prune --prune-apply`."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"

        clean_dir = skills_dir / A_RETIRED_NAME
        clean_dir.mkdir(parents=True)
        (clean_dir / "SKILL.md").write_text("just this\n", encoding="utf-8")

        preview = _run_sh(sandbox, home, "--prune")
        assert preview.returncode == 0, preview.stdout + preview.stderr
        assert (
            f"{A_RETIRED_NAME} (1 file)" in preview.stdout
            or (str(clean_dir) + " (1 file)") in preview.stdout
        )
        assert "holds more than SKILL.md" not in preview.stdout

        # Now the same retired name, holding something beyond SKILL.md.
        shutil.rmtree(clean_dir)
        dirty_dir = skills_dir / A_RETIRED_NAME
        dirty_dir.mkdir(parents=True)
        (dirty_dir / "SKILL.md").write_text("plus extra\n", encoding="utf-8")
        (dirty_dir / "my-notes.txt").write_text("mine\n", encoding="utf-8")

        apply_run = _run_sh(sandbox, home, "--prune", "--prune-apply")
        assert apply_run.returncode == 0, apply_run.stdout + apply_run.stderr
        assert "holds more than SKILL.md" in apply_run.stdout
        assert "(2 files" in apply_run.stdout
        assert not dirty_dir.exists(), "flagged or not, --prune-apply still removes it"

    def test_a_retired_name_shipped_under_drunken_extras_is_never_pruned(
        self, tmp_path
    ):
        """Review finding #1's extras exclusion (`comm -23` against
        `$_extras`), already in the script, had no test for the .sh
        installer at all -- only doctor's own copy of the rule
        (`test_a_retired_name_that_is_also_a_drunken_extras_skill_is_never_prunable`)
        was covered. Uses the real name this repository ships under both
        `retired_skills.txt` and `plugins/drunken-extras/skills/` today, so a
        drift between the two lists fails this for the right reason."""
        retired_file = REPO_ROOT / "scripts" / "install" / "retired_skills.txt"
        assert A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS in retired_file.read_text(
            encoding="utf-8"
        ), "fixture premise: this name must still be on retired_skills.txt"
        assert (
            REPO_ROOT
            / "plugins"
            / "drunken-extras"
            / "skills"
            / A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS
            / "SKILL.md"
        ).is_file(), "fixture premise: this name must still ship under drunken-extras"

        sandbox, home = _sandbox(tmp_path, seed=False)
        _seed_extras_skill(sandbox, A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS)
        skill_dir = _skill_path(home, A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("moved, not retired\n", encoding="utf-8")

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert skill_dir.is_dir(), (
            "a name shipped today under plugins/drunken-extras/skills/ must "
            "never be pruned, even though it is also on retired_skills.txt"
        )

    def test_a_differently_cased_name_is_not_matched_to_the_retired_list(
        self, tmp_path
    ):
        """DG-450 finding #2's case-sensitivity gap. `comm` compares byte for
        byte: an installed directory whose name differs only in case from the
        retired list entry is a different string, not a match, and must be
        reported `unrecognised` -- never silently treated as the retired
        name and pruned out from under an operator who happens to be on a
        case-preserving filesystem."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        differently_cased = A_RETIRED_NAME.upper()
        assert differently_cased != A_RETIRED_NAME
        cased_dir = skills_dir / differently_cased
        cased_dir.mkdir(parents=True)
        (cased_dir / "SKILL.md").write_text("cased differently\n", encoding="utf-8")

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert cased_dir.is_dir(), (
            "a name that differs only in case from a retired_skills.txt "
            "entry must never be pruned as if it were the same name"
        )
        assert differently_cased in result.stdout
        assert "Unrecognised" in result.stdout

    def test_a_retired_name_that_is_a_plain_file_is_reported_not_removed(
        self, tmp_path
    ):
        """DG-450 finding #2. `_installed` only ever recognises a directory
        holding SKILL.md or a link; a plain file sharing a retired name was
        previously invisible to every list this script prints. It must be
        named, and never touched, by `--prune`."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        file_path = skills_dir / A_RETIRED_NAME
        file_path.write_text("I am a plain file, not a skill\n", encoding="utf-8")

        result = _run_sh(sandbox, home, "--prune", "--prune-apply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert file_path.is_file() and not file_path.is_dir(), (
            "a plain file sharing a retired name must never be removed"
        )
        assert "not a skill directory, left alone" in result.stdout
        assert A_RETIRED_NAME in result.stdout


class TestRetiredListNamesNoCurrentlyShippedSkillDG359:
    def test_no_name_on_the_real_list_is_a_currently_shipped_skill(self):
        """Mirrors `tests/test_ai_layer_drift.py`'s doctor-side guard: a name
        on `scripts/install/retired_skills.txt` must never also be a skill
        directory under `skills/` — otherwise `--prune-apply` could delete
        something the guild ships today."""
        retired_file = REPO_ROOT / "scripts" / "install" / "retired_skills.txt"
        names = {
            line.strip("\r").strip()
            for line in retired_file.read_text(encoding="utf-8").splitlines()
            if line.strip("\r").strip() and not line.strip().startswith("#")
        }
        shipped = {p.parent.name for p in (REPO_ROOT / "skills").glob("*/*/SKILL.md")}

        overlap = names & shipped
        assert not overlap, (
            f"{sorted(overlap)} are on retired_skills.txt and are also "
            "skills this repository currently ships"
        )


@pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
class TestThePs1InstallerPrunesConsistentlyWithTheShOne:
    """install_skills.ps1 had no orphan reporting at all before DG-359 — not
    even the read-only report install_skills.sh already had. Same flags, same
    gating, ported across."""

    def test_the_default_run_reports_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home)

        assert result.returncode == 0, result.stdout + result.stderr
        assert _retired_path(home).is_dir()
        assert _unrecognised_path(home).is_dir()
        assert "Installed but not produced here" in result.stdout

    def test_prune_alone_lists_but_does_not_remove(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home, "-Prune")

        assert result.returncode == 0, result.stdout + result.stderr
        assert _retired_path(home).is_dir()
        assert _unrecognised_path(home).is_dir()
        assert "Would remove" in result.stdout
        assert "Unrecognised, never pruned" in result.stdout

    def test_prune_apply_removes_only_the_retired_one(self, tmp_path):
        """Same reproduced regression as the `.sh` test: a hand-written
        skill never on the retired list must survive `-PruneApply`."""
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not _retired_path(home).exists()
        assert _unrecognised_path(home).is_dir()

    def test_prune_apply_alone_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path)
        result = _run_ps1(sandbox, home, "-PruneApply")

        assert result.returncode != 0
        assert _retired_path(home).is_dir()
        assert _unrecognised_path(home).is_dir()

    def test_index_only_and_prune_together_is_refused(self, tmp_path):
        sandbox, home = _sandbox(tmp_path, seed=False)
        result = _run_ps1(sandbox, home, "-IndexOnly -Prune")

        assert result.returncode != 0
        assert not (home / ".claude").exists()

    def test_a_reparse_point_sharing_a_retired_name_is_never_followed_or_removed(
        self, tmp_path
    ):
        """Review finding #2, confirmed by reproduction: a real Windows
        junction (`New-Item -ItemType Junction`) pointed at a directory
        outside the skills tree, sharing a retired skill's name.
        `-PruneApply` must neither delete the junction's target's contents
        nor remove the junction itself. `Remove-Item -Recurse -Force` on a
        reparse point has a documented history of recursing into the
        TARGET's contents rather than removing the link, which is exactly
        what the `ReparsePoint` attribute check guards against."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        skills_dir.mkdir(parents=True)

        outside = tmp_path / "outside_target"
        outside.mkdir()
        (outside / "SKILL.md").write_text("precious\n", encoding="utf-8")
        (outside / "do-not-delete-me.txt").write_text("evidence\n", encoding="utf-8")

        link_path = skills_dir / A_RETIRED_NAME
        creation = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{link_path}' -Target '{outside}'; "
                "$item = Get-Item -LiteralPath "
                f"'{link_path}' -Force; "
                'Write-Host "REPARSE:$([bool]($item.Attributes -band '
                '[System.IO.FileAttributes]::ReparsePoint))"',
            ],
            capture_output=True,
            text=True,
        )
        # `-ItemType Junction` is an NTFS-specific concept. On Linux (CI's
        # PowerShell host is `pwsh`, not Windows PowerShell) it may exit 0
        # without actually producing a reparse point at all -- confirmed by
        # reproduction: it printed nothing, created no entry, and the test
        # below would then pass for the wrong reason (the install never saw
        # anything named `ai-output` to begin with). Verify a real reparse
        # point actually exists before trusting the rest of this test.
        if creation.returncode != 0 or "REPARSE:True" not in creation.stdout:
            pytest.skip(
                "cannot create a real reparse point (junction) on this "
                f"machine: rc={creation.returncode}\n"
                f"{creation.stdout}\n{creation.stderr}"
            )

        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "link, not touched" in result.stdout
        assert link_path.exists(), "the junction itself must not be removed"
        assert (outside / "SKILL.md").exists(), (
            "the junction's target must never be recursed into or deleted"
        )
        assert (outside / "do-not-delete-me.txt").exists()

    def test_a_nested_link_inside_a_retired_directory_makes_it_skipped(self, tmp_path):
        """DG-450 finding #3. The reparse-point check above only ever looks
        at the retired name itself; a link ONE LEVEL INSIDE a retired
        directory -- rather than being the retired name -- was never scanned
        for at all. `-PruneApply` must never recurse into or remove the
        whole directory when one is found; it must report why and leave it
        alone, on both the preview and the apply run.

        Tries a real symbolic link first (works unprivileged on pwsh/Linux,
        which is where this ticket's own review finding #3 said pwsh was
        never exercised), falling back to a junction (Windows-only, works
        unprivileged there) -- skipping honestly, never asserting against a
        link that was not actually created, if neither can be made."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        retired_dir = skills_dir / A_RETIRED_NAME
        retired_dir.mkdir(parents=True)
        (retired_dir / "SKILL.md").write_text("has a nested link\n", encoding="utf-8")

        outside = tmp_path / "outside_target"
        outside.mkdir()
        (outside / "precious.txt").write_text("do not touch\n", encoding="utf-8")
        nested_link = retired_dir / "nested-link"

        created = None
        last_creation = None
        for item_type in ("SymbolicLink", "Junction"):
            creation = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"New-Item -ItemType {item_type} -Path '{nested_link}' "
                    f"-Target '{outside}' -ErrorAction Stop | Out-Null; "
                    f"$item = Get-Item -LiteralPath '{nested_link}' -Force; "
                    'Write-Host "REPARSE:$([bool]($item.Attributes -band '
                    '[System.IO.FileAttributes]::ReparsePoint))"',
                ],
                capture_output=True,
                text=True,
            )
            last_creation = (item_type, creation)
            if creation.returncode == 0 and "REPARSE:True" in creation.stdout:
                created = item_type
                break

        if created is None:
            item_type, creation = last_creation
            pytest.skip(
                "cannot create a real nested link (symlink or junction) on "
                f"this machine: last tried {item_type}, "
                f"rc={creation.returncode}\n{creation.stdout}\n{creation.stderr}"
            )

        preview = _run_ps1(sandbox, home, "-Prune")
        assert preview.returncode == 0, preview.stdout + preview.stderr
        assert "nested link" in preview.stdout
        assert str(retired_dir) in preview.stdout

        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "nested link" in result.stdout
        assert retired_dir.is_dir(), (
            "a retired directory holding a nested link must never be removed as a whole"
        )
        assert nested_link.exists() or nested_link.is_symlink(), (
            "the nested link itself must survive -- it was never followed"
        )
        assert (outside / "precious.txt").exists(), (
            "the nested link's target must never be recursed into or deleted"
        )

    def test_the_preview_names_the_file_count_and_flags_extra_content(self, tmp_path):
        """DG-450. Same gap as the `.sh` test: the old output said only
        `"  $target"` for a retired directory about to be removed whole,
        with no count and no warning either for `-Prune` (dry run) or
        `-Prune -PruneApply`."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"

        clean_dir = skills_dir / A_RETIRED_NAME
        clean_dir.mkdir(parents=True)
        (clean_dir / "SKILL.md").write_text("just this\n", encoding="utf-8")

        preview = _run_ps1(sandbox, home, "-Prune")
        assert preview.returncode == 0, preview.stdout + preview.stderr
        assert "(1 file)" in preview.stdout
        assert "holds more than SKILL.md" not in preview.stdout

        shutil.rmtree(clean_dir)
        dirty_dir = skills_dir / A_RETIRED_NAME
        dirty_dir.mkdir(parents=True)
        (dirty_dir / "SKILL.md").write_text("plus extra\n", encoding="utf-8")
        (dirty_dir / "my-notes.txt").write_text("mine\n", encoding="utf-8")

        apply_run = _run_ps1(sandbox, home, "-Prune -PruneApply")
        assert apply_run.returncode == 0, apply_run.stdout + apply_run.stderr
        assert "holds more than SKILL.md" in apply_run.stdout
        assert "(2 files" in apply_run.stdout
        assert not dirty_dir.exists(), "flagged or not, -PruneApply still removes it"

    def test_a_retired_name_shipped_under_drunken_extras_is_never_pruned(
        self, tmp_path
    ):
        """Review finding #1's extras exclusion (`-notcontains $Extras`),
        already in the script, had no test for the .ps1 installer at all --
        only doctor's own copy of the rule was covered. Uses the real name
        this repository ships under both `retired_skills.txt` and
        `plugins/drunken-extras/skills/` today."""
        retired_file = REPO_ROOT / "scripts" / "install" / "retired_skills.txt"
        assert A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS in retired_file.read_text(
            encoding="utf-8"
        ), "fixture premise: this name must still be on retired_skills.txt"
        assert (
            REPO_ROOT
            / "plugins"
            / "drunken-extras"
            / "skills"
            / A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS
            / "SKILL.md"
        ).is_file(), "fixture premise: this name must still ship under drunken-extras"

        sandbox, home = _sandbox(tmp_path, seed=False)
        _seed_extras_skill(sandbox, A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS)
        skill_dir = _skill_path(home, A_RETIRED_NAME_SHIPPED_UNDER_EXTRAS)
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("moved, not retired\n", encoding="utf-8")

        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert skill_dir.is_dir(), (
            "a name shipped today under plugins/drunken-extras/skills/ must "
            "never be pruned, even though it is also on retired_skills.txt"
        )

    def test_a_differently_cased_name_is_matched_case_insensitively(self, tmp_path):
        """DG-450 finding #2's case-sensitivity gap, the `.ps1` side.
        `-contains` compares strings case-insensitively by default -- unlike
        `comm` in the `.sh` installer -- so a differently-cased installed
        name here IS treated as the retired one and is prunable. This pins
        that actual, current behaviour down so a change to case handling (in
        either direction) is seen rather than silently shipped."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        differently_cased = A_RETIRED_NAME.upper()
        assert differently_cased != A_RETIRED_NAME
        cased_dir = skills_dir / differently_cased
        cased_dir.mkdir(parents=True)
        (cased_dir / "SKILL.md").write_text("cased differently\n", encoding="utf-8")

        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert not cased_dir.exists(), (
            "-contains matches case-insensitively today, so a differently-"
            "cased retired name is pruned the same as an exact match"
        )

    def test_a_retired_name_that_is_a_plain_file_is_reported_not_removed(
        self, tmp_path
    ):
        """DG-450 finding #2. `$Installed` only ever recognises a directory
        holding SKILL.md; a plain file sharing a retired name was previously
        invisible to every list this script prints. It must be named, and
        never touched, by `-Prune`."""
        sandbox, home = _sandbox(tmp_path, seed=False)
        skills_dir = home / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        file_path = skills_dir / A_RETIRED_NAME
        file_path.write_text("I am a plain file, not a skill\n", encoding="utf-8")

        result = _run_ps1(sandbox, home, "-Prune -PruneApply")

        assert result.returncode == 0, result.stdout + result.stderr
        assert file_path.is_file() and not file_path.is_dir(), (
            "a plain file sharing a retired name must never be removed"
        )
        assert "not a skill directory, left alone" in result.stdout
        assert A_RETIRED_NAME in result.stdout

    def test_empty_home_and_userprofile_is_refused(self, tmp_path):
        """Review finding #3. Both `$HOME` and `$env:USERPROFILE` emptied in
        the same child process, guarded the same way the canary helper
        guards the redirected case: this does not call `_run_ps1`, because
        the point here is specifically that NO redirection happens and the
        script must refuse rather than fall back to some other path."""
        sandbox, _ = _sandbox(tmp_path, seed=False)
        script = sandbox / "scripts" / "install" / "install_skills.ps1"
        command = (
            "Set-Variable -Name HOME -Value '' -Force -Scope Global; "
            "$env:USERPROFILE = ''; "
            f"& '{script}'"
        )
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "empty or unset" in result.stdout + result.stderr


@pytest.mark.skipif(BASH is None, reason="no bash on this machine")
def test_empty_home_is_refused_sh(tmp_path):
    """Review finding #3 for install_skills.sh. Windows' process-creation
    layer cannot reliably pass a literal empty-string environment variable
    (confirmed separately: it corrupts adjacent values instead), so `HOME`
    is unset *inside* a running bash process via `unset HOME;` rather than
    via the Python subprocess `env=` dict — this is the only way to exercise
    a genuinely empty `$HOME` on this platform. On Linux, where this script
    actually runs, an unset `$HOME` behaves the same way either route."""
    sandbox, _ = _sandbox(tmp_path, seed=False)
    script = sandbox / "scripts" / "install" / "install_skills.sh"
    command = f'unset HOME; "{script}"'
    result = subprocess.run([BASH, "-c", command], capture_output=True, text=True)

    assert result.returncode != 0
    assert "empty or unset" in result.stdout + result.stderr
