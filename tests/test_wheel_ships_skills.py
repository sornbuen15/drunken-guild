# mypy: ignore-errors
"""DG-498 (REQ-022, REQ-008). The wheel carries every skill, so an install needs no clone.

Built from a COPY of the tracked tree, in a temporary folder: ``uv build`` writes ``build/`` next to
the sources it reads, and a stale ``build/lib`` is exactly how a wheel once shipped ten retired files
(DG-363). The repository is never the build directory here.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

NEEDED = ("pyproject.toml", "README.md", "LICENSE", "CHANGELOG.md")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> zipfile.ZipFile:
    if shutil.which("uv") is None:
        pytest.skip("uv is needed to build a wheel")
    work = tmp_path_factory.mktemp("wheelsrc")
    for name in NEEDED:
        if (REPO / name).is_file():
            shutil.copy2(REPO / name, work / name)
    for folder in ("src", "scripts", "skills", "agents"):
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
    assert done.returncode == 0, f"the wheel failed to build: {done.stderr[-600:]}"
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


def test_every_agent_adapter_and_the_manifest_are_inside_the_wheel(wheel) -> None:
    names = set(wheel.namelist())
    wanted = {
        "drunken_agents/" + p.name
        for p in (REPO / "agents").iterdir()
        if p.is_file() and (p.suffix == ".md" or p.name == "_sources.json")
    }

    assert "drunken_agents/_sources.json" in wanted and wanted
    assert not sorted(wanted - names), f"the wheel is missing {sorted(wanted - names)}"


def test_the_changelog_travels_with_the_install(wheel) -> None:
    data = [
        n for n in wheel.namelist() if n.endswith("share/drunken-guild/CHANGELOG.md")
    ]

    assert data, "drunken-install status needs the changelog to quote"


@pytest.fixture(scope="module")
def installed_command(wheel, tmp_path_factory):
    """The built wheel installed into a clean venv: what a person who ran ``uv tool install`` has."""
    venv = tmp_path_factory.mktemp("venv")
    wheel_path = Path(wheel.filename)
    made = subprocess.run(
        ["uv", "venv", str(venv)], capture_output=True, text=True, check=False
    )
    assert made.returncode == 0, made.stderr[-400:]
    bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
    python = bindir / ("python.exe" if sys.platform == "win32" else "python")
    put = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert put.returncode == 0, put.stderr[-600:]
    exe = bindir / (
        "drunken-install.exe" if sys.platform == "win32" else "drunken-install"
    )
    assert exe.exists(), f"the wheel installed no drunken-install command in {bindir}"
    return exe


def test_the_installed_command_finds_its_own_skills_and_agents(
    installed_command, tmp_path
) -> None:
    """Found by running it: ``importlib.resources.files`` returned a non-directory for the
    namespace package, and the command refused with 'not a source checkout'."""
    skills = tmp_path / "claude" / "skills"

    done = subprocess.run(
        [
            str(installed_command),
            "all",
            "--target",
            str(skills),
            "--agents-target",
            str(skills.parent / "agents"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )

    assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
    assert (skills / "prd" / "SKILL.md").read_bytes() == (
        REPO / "skills" / "flow" / "prd" / "SKILL.md"
    ).read_bytes()
    assert (skills / "INDEX.md").exists()
    assert (skills.parent / "agents" / "worker.md").exists()


def test_the_installed_prune_list_comes_from_the_wheel(
    installed_command, tmp_path
) -> None:
    skills = tmp_path / "claude" / "skills"
    retired = (REPO / "scripts" / "install" / "retired_skills.txt").read_text(
        encoding="utf-8"
    )
    name = next(
        line.strip()
        for line in retired.splitlines()
        if line.strip() and not line.startswith("#")
    )
    (skills / name).mkdir(parents=True)
    (skills / name / "SKILL.md").write_bytes(b"x" + bytes([10]))

    done = subprocess.run(
        [str(installed_command), "skills", "--target", str(skills), "--prune"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )

    assert done.returncode == 0, done.stderr[-400:]
    assert name in done.stdout, (
        "the retired-names list was not found in the installed package"
    )
    assert (skills / name).exists(), "--prune alone removes nothing"


def test_the_installed_status_quotes_the_changelog(installed_command, tmp_path) -> None:
    done = subprocess.run(
        [
            str(installed_command),
            "status",
            "--target",
            str(tmp_path / "s"),
            "--agents-target",
            str(tmp_path / "a"),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )

    assert done.returncode == 0, done.stderr[-400:]
    assert "changelog" in done.stdout and "not found" not in done.stdout
