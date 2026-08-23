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

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
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
