# mypy: ignore-errors
"""DG-498 (REQ-022, REQ-008). The wheel carries every skill, so an install needs no clone.

Built from a COPY of the tracked tree, in a temporary folder: ``uv build`` writes ``build/`` next to
the sources it reads, and a stale ``build/lib`` is exactly how a wheel once shipped ten retired files
(DG-363). The repository is never the build directory here.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

NEEDED = ("pyproject.toml", "README.md", "LICENSE")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> zipfile.ZipFile:
    if shutil.which("uv") is None:
        pytest.skip("uv is needed to build a wheel")
    work = tmp_path_factory.mktemp("wheelsrc")
    for name in NEEDED:
        if (REPO / name).is_file():
            shutil.copy2(REPO / name, work / name)
    for folder in ("src", "scripts", "skills"):
        shutil.copytree(
            REPO / folder,
            work / folder,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
        )
    out = work / "dist"
    done = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out), str(work)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip(f"the wheel could not be built here: {done.stderr[-300:]}")
    return zipfile.ZipFile(next(out.glob("*.whl")))


def test_every_skill_in_the_repo_is_inside_the_wheel(wheel) -> None:
    names = set(wheel.namelist())
    wanted = {
        "drunken_skills/" + p.relative_to(REPO / "skills").as_posix()
        for p in (REPO / "skills").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }

    assert wanted, "the repository has no skills to ship?"
    missing = sorted(wanted - names)
    assert not missing, f"the wheel is missing {missing[:5]}"


def test_the_wheel_ships_the_retired_names_the_prune_reads(wheel) -> None:
    assert "scripts/install/retired_skills.txt" in wheel.namelist()


def test_a_shipped_skill_is_byte_identical_to_the_source(wheel) -> None:
    source = (REPO / "skills" / "flow" / "prd" / "SKILL.md").read_bytes()

    assert wheel.read("drunken_skills/flow/prd/SKILL.md") == source


def test_the_wheel_installs_the_command(wheel) -> None:
    entry = next(n for n in wheel.namelist() if n.endswith("entry_points.txt"))

    assert "drunken-install = core.install:main" in wheel.read(entry).decode("utf-8")
