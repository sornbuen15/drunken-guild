"""DG-363. A stale ``build/lib/`` must not ship a retired module unnoticed.

The installed drunken-guild 1.3.1 carried `discord_mcp/` and `service/` --
ten files of machinery retired in DG-355 -- because setuptools reused a
`build/lib/` written before the retirement. `pyproject.toml` and the wheel's
own `top_level.txt` agreed on the current packages; its `RECORD` did not.

These tests build real wheels (via `zipfile`, matching the layout setuptools
produces -- `*.dist-info/{RECORD,top_level.txt}` plus the files themselves)
rather than asserting against a description of one, so a change to the
comparison logic has to keep agreeing with what a wheel actually looks like.

`TestARealBuildOfThisProject` goes further and calls real `uv build`, against
a copy of this project's own tree -- a first version of this check ran
`uv build` (no flags) and passed clean on a wheel that, with `--wheel`
dropped, builds from a *fresh sdist* rather than the stale tree, so it never
saw the stale `build/lib/` at all. That is reproduced here deliberately
(`test_the_sdist_round_trip_does_not_see_the_stale_module`) so a change back
to that invocation fails loudly rather than quietly.
"""

from __future__ import annotations

import io
import shutil
import subprocess  # nosec B404 - uv and git, invoked with fixed argument lists
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import check_wheel_contents as checker


def _write_wheel(
    path: Path,
    *,
    top_level: list[str],
    record_paths: list[str],
    omit_top_level_txt: bool = False,
) -> Path:
    """A minimal wheel: declared packages in top_level.txt, some set of files
    in RECORD. The two are not derived from each other here on purpose --
    that disagreement is exactly what a stale build/lib/ produces."""
    info_dir = "pkg-0.0.1.dist-info"
    record_lines = list(record_paths)
    if not omit_top_level_txt:
        record_lines.append(f"{info_dir}/top_level.txt,,")
    record_lines.append(f"{info_dir}/RECORD,,")

    with zipfile.ZipFile(path, "w") as archive:
        for record_path in record_paths:
            archive.writestr(record_path, "")
        if not omit_top_level_txt:
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

    def test_a_data_directory_is_not_flagged(self, tmp_path: Path) -> None:
        """`*.data/` is the wheel spec's other reserved top-level directory
        (scripts, headers, data files installed outside the package tree) --
        just as legitimate as `.dist-info` and never named in top_level.txt.
        Flagging it would fail every wheel that installs a console script
        this way."""
        wheel = _write_wheel(
            tmp_path / "data.whl",
            top_level=["core"],
            record_paths=["core/__init__.py", "pkg-0.0.1.data/scripts/drunken-doctor"],
        )

        assert checker.undeclared_top_level_modules(wheel) == []

    def test_a_missing_top_level_txt_is_a_named_error_not_a_traceback(
        self, tmp_path: Path
    ) -> None:
        wheel = _write_wheel(
            tmp_path / "no_top_level.whl",
            top_level=[],
            record_paths=["core/__init__.py"],
            omit_top_level_txt=True,
        )

        with pytest.raises(checker.WheelInspectionError, match="top_level.txt"):
            checker.undeclared_top_level_modules(wheel)

    def test_a_bad_zip_is_a_named_error_not_a_traceback(self, tmp_path: Path) -> None:
        not_a_wheel = tmp_path / "garbage.whl"
        not_a_wheel.write_bytes(b"this is not a zip file")

        with pytest.raises(checker.WheelInspectionError):
            checker.undeclared_top_level_modules(not_a_wheel)


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

    def test_an_unreadable_wheel_is_a_named_error_not_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        not_a_wheel = tmp_path / "garbage.whl"
        not_a_wheel.write_bytes(b"this is not a zip file")

        status = checker.main([str(not_a_wheel)])

        assert status == 2, "an unreadable wheel is a tooling problem, not a policy one"
        assert "garbage.whl" in capsys.readouterr().err


class TestARealBuildOfThisProject:
    """Builds real wheels with `uv build`, from copies of this project's own
    tree under `tmp_path` -- never from the real checkout, since `--wheel`
    writes `build/lib/` and `*.egg-info` into whatever directory it runs in.
    """

    @staticmethod
    def _tracked_copy(dest: Path) -> Path:
        """`git archive HEAD`, extracted -- the tracked tree, nothing more,
        and no `.git/` to carry along."""
        repo_root = Path(__file__).resolve().parent.parent
        result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
            ["git", "-C", str(repo_root), "archive", "HEAD"],
            capture_output=True,
            check=True,
            timeout=60,
        )
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
            tar.extractall(dest, filter="data")  # nosec B202 - this repo's own HEAD
        return dest

    @staticmethod
    def _plant_stale_module(copy_root: Path) -> None:
        """The DG-363 shape: a package retired from pyproject.toml, still
        physically present in a gitignored build/lib/ nobody cleaned."""
        stale = copy_root / "build" / "lib" / "discord_mcp"
        stale.mkdir(parents=True)
        (stale / "__init__.py").write_text("", encoding="utf-8")
        (stale / "bot.py").write_text("", encoding="utf-8")

    @staticmethod
    def _build_wheel(
        uv: str, source: Path, out_dir: Path, *, wheel_only: bool
    ) -> Path | None:
        argv = [uv, "build", "--out-dir", str(out_dir)]
        if wheel_only:
            argv.insert(2, "--wheel")
        result = subprocess.run(  # nosec B603 - fixed argv, no shell
            argv,
            cwd=source,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        wheels = list(out_dir.glob("*.whl")) if out_dir.exists() else []
        if result.returncode != 0 or not wheels:
            return None
        return wheels[0]

    @staticmethod
    def _uv_or_skip() -> str:
        uv = shutil.which("uv")
        if uv is None:
            pytest.skip("uv is not on PATH")
        assert uv is not None  # for mypy -- pytest.skip never returns
        return uv

    def test_the_current_tree_declares_everything_it_ships(
        self, tmp_path: Path
    ) -> None:
        """Sanity guard: this project's own pyproject.toml declarations agree
        with what a clean build actually ships today."""
        uv = self._uv_or_skip()
        source = self._tracked_copy(tmp_path / "clean")

        wheel = self._build_wheel(uv, source, tmp_path / "dist", wheel_only=True)
        if wheel is None:
            pytest.skip("uv build --wheel unavailable here")
            return

        assert checker.undeclared_top_level_modules(wheel) == []

    def test_a_stale_build_lib_in_the_real_tree_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The acceptance criterion itself, against the real pyproject.toml:
        a wheel built from a tree with a stale build/ is refused, and the
        message names the undeclared module. `--wheel` builds in place, so
        `install_lib` copies build/lib/ wholesale regardless of what is
        declared today -- this is the invocation that actually leaks it.
        """
        uv = self._uv_or_skip()
        source = self._tracked_copy(tmp_path / "stale")
        self._plant_stale_module(source)

        wheel = self._build_wheel(uv, source, tmp_path / "dist-stale", wheel_only=True)
        if wheel is None:
            pytest.skip("uv build --wheel unavailable here")
            return

        found = checker.undeclared_top_level_modules(wheel)
        assert found == ["discord_mcp"], (
            "a stale build/lib/ in the real tree must be caught and named, "
            f"not quietly shipped. Got {found}"
        )

    def test_the_sdist_round_trip_does_not_see_the_stale_module(
        self, tmp_path: Path
    ) -> None:
        """Documents why verify_clean_install.sh must pass `--wheel`: without
        it, `uv build` builds the wheel from a *freshly generated sdist*, and
        that sdist never contains the stale, gitignored build/lib/ -- so the
        wheel comes back clean despite the exact DG-363 condition being
        present in the tree it was "built from". A reviewer caught the first
        version of this wiring doing exactly this. If this test starts
        failing, uv changed its default build order and the comment in
        check_wheel_contents.py is stale, not this test.
        """
        uv = self._uv_or_skip()
        source = self._tracked_copy(tmp_path / "stale-sdist")
        self._plant_stale_module(source)

        wheel = self._build_wheel(uv, source, tmp_path / "dist-sdist", wheel_only=False)
        if wheel is None:
            pytest.skip("uv build unavailable here")
            return

        assert checker.undeclared_top_level_modules(wheel) == [], (
            "the sdist round trip is expected to miss the stale module -- "
            "that is exactly why `--wheel` is required, not optional"
        )
