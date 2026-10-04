"""DG-363. A stale ``build/lib/`` must not ship a retired module unnoticed.

The installed drunken-guild 1.3.1 carried `discord_mcp/` and `service/` --
ten files of machinery retired in DG-355 -- because setuptools reused a
`build/lib/` written before the retirement. `pyproject.toml` and the wheel's
own `top_level.txt` agreed on the current packages; its `RECORD` did not.

These tests build real wheels (via `zipfile`, matching the layout setuptools
produces -- `*.dist-info/{RECORD,top_level.txt}` plus the files themselves)
rather than asserting against a description of one, so a change to the
comparison logic has to keep agreeing with what a wheel actually looks like.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - uv, invoked with a fixed argument list
import zipfile
from pathlib import Path

import pytest

from scripts import check_wheel_contents as checker


def _write_wheel(path: Path, *, top_level: list[str], record_paths: list[str]) -> Path:
    """A minimal wheel: declared packages in top_level.txt, some set of files
    in RECORD. The two are not derived from each other here on purpose --
    that disagreement is exactly what a stale build/lib/ produces."""
    info_dir = "pkg-0.0.1.dist-info"
    record_lines = list(record_paths)
    record_lines.append(f"{info_dir}/top_level.txt,,")
    record_lines.append(f"{info_dir}/RECORD,,")

    with zipfile.ZipFile(path, "w") as archive:
        for record_path in record_paths:
            archive.writestr(record_path, "")
        archive.writestr(f"{info_dir}/top_level.txt", "\n".join(top_level) + "\n")
        archive.writestr(f"{info_dir}/RECORD", "\n".join(record_lines) + "\n")
    return path


class TestUndeclaredTopLevelModules:
    def test_a_clean_wheel_reports_nothing(self, tmp_path: Path) -> None:
        wheel = _write_wheel(
            tmp_path / "clean.whl",
            top_level=["core", "jira_mcp"],
            record_paths=["core/__init__.py", "jira_mcp/__init__.py"],
        )

        assert checker.undeclared_top_level_modules(wheel) == []

    def test_a_retired_package_left_in_build_lib_is_named(self, tmp_path: Path) -> None:
        """Seen failing first: this is the DG-363 shape -- top_level.txt
        agrees with what the project declares, RECORD carries a package
        retired from pyproject.toml but still physically present in a stale
        build/lib/."""
        wheel = _write_wheel(
            tmp_path / "stale.whl",
            top_level=["core", "jira_mcp"],
            record_paths=[
                "core/__init__.py",
                "jira_mcp/__init__.py",
                "discord_mcp/__init__.py",
                "discord_mcp/bot.py",
                "service/__init__.py",
            ],
        )

        found = checker.undeclared_top_level_modules(wheel)

        assert found == ["discord_mcp", "service"], (
            "every undeclared top-level name must be named once, not just "
            f"that something was wrong. Got {found}"
        )

    def test_a_root_level_module_is_named_without_its_suffix(
        self, tmp_path: Path
    ) -> None:
        """top_level.txt lists a bare module name (`six`, not `six.py`);
        RECORD lists the file. The comparison has to normalise one to the
        other or every undeclared single-file module reads as declared."""
        wheel = _write_wheel(
            tmp_path / "root_module.whl",
            top_level=["core"],
            record_paths=["core/__init__.py", "leftover.py"],
        )

        assert checker.undeclared_top_level_modules(wheel) == ["leftover"]

    def test_dist_info_s_own_files_are_never_flagged(self, tmp_path: Path) -> None:
        """RECORD lists its own dist-info contents (METADATA, LICENSE, ...).
        None of those are a package the project declares, and flagging them
        would make every wheel fail."""
        wheel = _write_wheel(
            tmp_path / "self.whl",
            top_level=["core"],
            record_paths=["core/__init__.py"],
        )

        assert checker.undeclared_top_level_modules(wheel) == []


class TestTheCommandLine:
    def test_a_stale_wheel_is_refused_and_the_message_names_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wheel = _write_wheel(
            tmp_path / "stale.whl",
            top_level=["core"],
            record_paths=["core/__init__.py", "discord_mcp/bot.py"],
        )

        status = checker.main([str(wheel)])

        assert status == 1, "an undeclared module must fail the check"
        err = capsys.readouterr().err
        assert "discord_mcp" in err, "the reader must not have to go looking"

    def test_a_clean_wheel_passes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wheel = _write_wheel(
            tmp_path / "clean.whl",
            top_level=["core"],
            record_paths=["core/__init__.py"],
        )

        assert checker.main([str(wheel)]) == 0


class TestARealBuildOfThisProject:
    """Builds an actual wheel with `uv build`, into a scratch output
    directory, and checks it -- a sanity guard that this project's own
    `pyproject.toml` declarations agree with what gets shipped today."""

    def test_the_current_tree_declares_everything_it_ships(
        self, tmp_path: Path
    ) -> None:
        uv = shutil.which("uv")
        if uv is None:
            pytest.skip("uv is not on PATH")
            return

        repo_root = Path(__file__).resolve().parent.parent
        out_dir = tmp_path / "dist"

        result = subprocess.run(  # nosec B603 - fixed argv, no shell
            [uv, "build", "--out-dir", str(out_dir)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        wheels = list(out_dir.glob("*.whl")) if out_dir.exists() else []
        if result.returncode != 0 or not wheels:
            pytest.skip(f"uv build unavailable here: {result.stderr[-500:]}")

        assert checker.undeclared_top_level_modules(wheels[0]) == []
