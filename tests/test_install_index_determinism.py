# mypy: ignore-errors
"""DG-280. A generated file that is also committed must not depend on who ran
the generator.

`install_skills.sh` and `install_agents.sh` truncated each description with
`cut -c1-N`. `cut -c` counts *bytes* under `LC_ALL=C` and *characters* under a
UTF-8 locale, and every description in this repository is full of em-dashes at
three bytes each. So the same skills produced two different `INDEX.md` files
depending on the shell.

Observed 2026-08-23: an install from an interactive UTF-8 shell rewrote 13
lines of `skills/INDEX.md`; regenerating from a shell with no locale set
reverted all 13 exactly. Both outputs are "what the generator produces", so the
file flip-flops and neither side is wrong — which is the worst shape a
generated artefact can have.

Byte truncation can also cut a multibyte character in half. The committed file
happened to stay valid UTF-8, by where the boundary fell rather than by
construction.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: DG-378 is a Windows defect, and CI runs on Linux only. The behavioural test
#: below therefore skips in CI and runs on the workstation the bug was found
#: on, which is the point of DG-371.
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
TRUNCATE = REPO_ROOT / "scripts" / "install" / "_truncate.py"
INSTALLERS = (
    REPO_ROOT / "scripts" / "install" / "install_skills.sh",
    REPO_ROOT / "scripts" / "install" / "install_agents.sh",
)

#: A description shaped like the real ones: em-dashes early, so a byte count
#: and a character count diverge well before the limit.
SAMPLE = (
    "Enforces Clean Architecture — layer separation — dependency rules — and boundaries"
)


def _truncate(text: str, width: int, locale: str) -> bytes:
    return subprocess.run(
        [sys.executable, str(TRUNCATE), str(width)],
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
        env={"LC_ALL": locale, "LANG": locale, "PATH": "/usr/bin:/bin"},
    ).stdout


class TestTruncationDoesNotDependOnTheShell:
    def test_the_two_locales_agree(self) -> None:
        """The whole bug. These differed by one or two characters per line,
        which is enough to dirty the repository on every install."""
        assert _truncate(SAMPLE, 40, "C") == _truncate(SAMPLE, 40, "en_US.UTF-8"), (
            "byte counting under LC_ALL=C is what made INDEX.md depend on who "
            "ran the installer"
        )

    def test_it_counts_characters_not_bytes(self) -> None:
        text = "—" * 20
        assert _truncate(text, 5, "C").decode("utf-8") == "—" * 5, (
            "five em-dashes are 15 bytes; a byte count would return one and a "
            "third of them"
        )

    def test_it_never_splits_a_multibyte_character(self) -> None:
        """The latent half of the bug: the committed file is valid UTF-8 today
        by luck of where the cut landed."""
        text = "—" * 20
        for width in range(1, 12):
            _truncate(text, width, "C").decode("utf-8")

    def test_shorter_than_the_limit_is_returned_whole(self) -> None:
        assert _truncate("short", 160, "C").decode("utf-8") == "short"


class TestTheInstallersNoLongerCountBytes:
    @pytest.mark.parametrize("script", INSTALLERS, ids=lambda p: p.name)
    def test_cut_c_is_gone(self, script: Path) -> None:
        """A guard, not a style rule. `cut -c` is the construct that carried
        the defect, and it reads as obviously correct — which is why it
        survived review twice."""
        assert "cut -c" not in script.read_text(encoding="utf-8"), (
            f"{script.name} still truncates with `cut -c`, which counts bytes "
            "under LC_ALL=C"
        )


class TestTheWidthDoesNotDependOnTheOperatingSystem:
    def test_the_powershell_variant_truncates_at_the_same_width(self) -> None:
        """Same class as the locale bug, found alongside it: the bash installer
        truncated a skill description at 160 and the PowerShell one at 80, so
        the committed file also depended on which OS regenerated it."""
        bash = (REPO_ROOT / "scripts" / "install" / "install_skills.sh").read_text(
            encoding="utf-8"
        )
        powershell = (
            REPO_ROOT / "scripts" / "install" / "install_skills.ps1"
        ).read_text(encoding="utf-8")
        assert "160" in bash, "the bash installer should still state its width"
        assert "Substring(0, [Math]::Min(160" in powershell, (
            "the PowerShell installer truncates skill descriptions at a "
            "different width from the bash one, so INDEX.md differs by platform"
        )


class TestTheGeneratorEmitsWhatACommitAccepts:
    """The second half of DG-280, found when `pre-commit` rewrote the freshly
    generated file and aborted the commit.

    A generator whose output the commit hook edits can never produce the file
    that is in git: regenerate, and the repository is dirty again by exactly
    the whitespace the hook removed. Same disease as the locale dependency,
    different symptom.
    """

    @pytest.mark.parametrize(
        "index",
        [REPO_ROOT / "skills" / "INDEX.md", REPO_ROOT / "agents" / "INDEX.md"],
        ids=lambda p: f"{p.parent.name}/{p.name}",
    )
    def test_the_committed_index_has_no_trailing_whitespace(self, index: Path) -> None:
        offenders = [
            number
            for number, line in enumerate(
                index.read_text(encoding="utf-8").splitlines(), 1
            )
            if line != line.rstrip()
        ]
        assert not offenders, (
            f"{index.name} lines {offenders} end in whitespace, which "
            "pre-commit strips — so the generator's output and the committed "
            "file can never match"
        )

    @pytest.mark.parametrize(
        "index",
        [REPO_ROOT / "skills" / "INDEX.md", REPO_ROOT / "agents" / "INDEX.md"],
        ids=lambda p: f"{p.parent.name}/{p.name}",
    )
    def test_the_committed_index_ends_in_exactly_one_newline(self, index: Path) -> None:
        raw = index.read_bytes()
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), (
            f"{index.name} must end in exactly one newline; end-of-file-fixer "
            "enforces that on commit, so the generator has to produce it"
        )

    def test_truncation_drops_the_space_the_awk_fold_leaves(self) -> None:
        """`printf \"%s \"` joins folded YAML lines, so a description ends in a
        space and a mid-sentence cut lands on one."""
        assert _truncate("word ", 5, "C").decode("utf-8") == "word"


class TestThePowerShellInstallerReadsTheShapeSkillsActuallyUse:
    """DG-378. `install_skills.ps1` read the trigger from a `Trigger/Keywords:**`
    line and the description from a `**Description:**` body line. Neither shape
    survived the move to YAML frontmatter: the first appears in *none* of the
    eleven `SKILL.md` files, so every row the Windows installer wrote lost its
    slash command, and `jira-tickets` — the one skill carrying no legacy body
    line either — lost its description as well.

    `install_skills.sh` was fixed for both and the `.ps1` was not, so the two
    installers published different indexes from the same tree. That is the same
    disease as the locale bug above: a generated *and* committed file whose
    content depends on which machine regenerated it.
    """

    def test_the_shape_it_used_to_look_for_is_really_gone(self) -> None:
        """The premise, asserted rather than assumed. If a skill ever
        reintroduces the line, the fallback stops being the only live path and
        this test is where that shows up."""
        carriers = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in sorted((REPO_ROOT / "skills").rglob("SKILL.md"))
            if "Trigger/Keywords:" in path.read_text(encoding="utf-8")
        ]
        assert not carriers, (
            f"{carriers} carry a `Trigger/Keywords:` line again — the "
            "installers' primary extractor is live, not dead code"
        )

    def test_it_reads_the_frontmatter_description(self) -> None:
        powershell = (
            REPO_ROOT / "scripts" / "install" / "install_skills.ps1"
        ).read_text(encoding="utf-8")
        assert "^description:" in powershell, (
            "install_skills.ps1 does not read the YAML frontmatter "
            "`description:`, which is the only place ten of the eleven skills "
            "state one"
        )

    def test_it_falls_back_to_the_trigger_on_phrase(self) -> None:
        powershell = (
            REPO_ROOT / "scripts" / "install" / "install_skills.ps1"
        ).read_text(encoding="utf-8")
        assert "Trigger on" in powershell, (
            "install_skills.ps1 has no `Trigger on` fallback, so no row it "
            "writes can name a slash command"
        )

    @pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
    def test_the_powershell_installer_reproduces_the_committed_index(
        self, tmp_path: Path
    ) -> None:
        """The acceptance line of DG-378, and the only one that reads the
        script by running it rather than by grepping it.

        Both of the installer's write targets are redirected into the sandbox.
        It installs into `$HOME/.claude/skills` and then mirrors the index back
        over `skills/INDEX.md`, so a test that ran it in place would write to
        the operator's profile and leave a tracked file rewritten whether it
        passed or failed.
        """
        sandbox = tmp_path / "repo"
        (sandbox / "scripts").mkdir(parents=True)
        shutil.copytree(REPO_ROOT / "skills", sandbox / "skills")
        shutil.copytree(
            REPO_ROOT / "scripts" / "install", sandbox / "scripts" / "install"
        )
        home = tmp_path / "home"
        home.mkdir()

        script = sandbox / "scripts" / "install" / "install_skills.ps1"
        assert POWERSHELL is not None
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"Set-Variable -Name HOME -Value '{home}' -Force -Scope Global; "
                f"& '{script}'",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"the installer exited {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )

        produced = (home / ".claude" / "skills" / "INDEX.md").read_bytes()

        assert not produced.startswith(b"\xef\xbb\xbf"), (
            "the index starts with a UTF-8 BOM, which is what "
            "`Set-Content -Encoding UTF8` adds on Windows PowerShell 5.1 and "
            "the bash installer never writes"
        )
        assert b"\r\n" not in produced, (
            "the index has CRLF line endings; the bash installer writes LF, "
            "and this file is committed"
        )

        # Against the blob rather than the checked-out file: core.autocrlf is on
        # for this clone, so skills/INDEX.md is CRLF on disk here and LF in git.
        # What has to match is what git stores -- that is the copy the macOS
        # installer wrote.
        committed = subprocess.run(
            ["git", "show", "HEAD:skills/INDEX.md"],
            capture_output=True,
            check=True,
            cwd=REPO_ROOT,
        ).stdout
        assert produced == committed, (
            "the PowerShell installer and the bash one disagree about the "
            "bytes of a file that is in git. The Windows copy is at\n"
            f"  {home / '.claude' / 'skills' / 'INDEX.md'}"
        )


class TestTheAgentInstallerWritesTheSameBytes:
    """DG-380 — DG-378's cure, applied to the other committed index.

    A Windows run and a macOS run of the same tree wrote different
    `agents/INDEX.md`: a BOM and CRLF, a trailing blank line the commit hook
    strips, `-` where the shell writes an em-dash, and its own filename in the
    "Generated by" header. Each install reverted the other's.
    """

    def test_the_header_names_one_generator(self) -> None:
        """Whichever script ran, the header must read the same."""
        sh = (REPO_ROOT / "scripts" / "install" / "install_agents.sh").read_text(
            encoding="utf-8"
        )
        ps = (REPO_ROOT / "scripts" / "install" / "install_agents.ps1").read_text(
            encoding="utf-8"
        )
        assert "Generated by `scripts/install/install_agents.sh`" not in sh
        assert "install_agents.ps1``. Do not edit" not in ps

    @pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
    def test_the_powershell_installer_reproduces_the_committed_index(
        self, tmp_path: Path
    ) -> None:
        """Run in a sandbox: it installs into $HOME/.claude/agents and mirrors
        the index back over agents/INDEX.md, so running it in place would write
        to the operator's profile and rewrite a tracked file."""
        sandbox = tmp_path / "repo"
        (sandbox / "scripts").mkdir(parents=True)
        shutil.copytree(REPO_ROOT / "agents", sandbox / "agents")
        shutil.copytree(
            REPO_ROOT / "scripts" / "install", sandbox / "scripts" / "install"
        )
        home = tmp_path / "home"
        home.mkdir()

        script = sandbox / "scripts" / "install" / "install_agents.ps1"
        assert POWERSHELL is not None
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"Set-Variable -Name HOME -Value '{home}' -Force -Scope Global; "
                f"& '{script}'",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"the installer exited {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )

        produced = (home / ".claude" / "agents" / "INDEX.md").read_bytes()
        assert not produced.startswith(b"\xef\xbb\xbf"), "the index starts with a BOM"
        assert b"\r\n" not in produced, "the index has CRLF line endings"

        committed = subprocess.run(
            ["git", "show", "HEAD:agents/INDEX.md"],
            capture_output=True,
            check=True,
            cwd=REPO_ROOT,
        ).stdout
        assert produced == committed, (
            "install_agents.ps1 and install_agents.sh disagree about the bytes "
            f"of agents/INDEX.md. The Windows copy is at\n  {home / '.claude' / 'agents' / 'INDEX.md'}"
        )
