"""DG-514 Gate D. ``drunken-guild`` release smoke test.

What an operator did by hand before shipping 2.0.2 — "build a release-candidate wheel from
``origin/develop``, install it into a clean venv with a temp ``HOME``, and run what a user would
run" — turned into something that can be re-run on demand and in CI. Only the standard library and
``uv`` (already a required dependency of this project) are used; nothing new is installed to run
this script itself.

Steps, in order, each one a real subprocess against a real, disposable install — nothing here
mocks or stubs the installer:

1. ``uv build --wheel`` the current checkout into a temp directory.
2. ``uv venv`` a fresh virtual environment, then ``uv pip install`` the wheel into it.
3. Point ``HOME``/``USERPROFILE``/``APPDATA`` at a temp "home" distinct from both the venv and the
   real operator home, for every subprocess from here on.
4. ``drunken-install all`` then ``drunken-install extras --apply`` — the two commands a fresh
   install needs — and count what landed.
5. ``drunken-install status`` — must say "up to date" and print no ``retired`` line for an extra
   (DG-514 blocker A).
6. ``drunken-install skills --prune`` — the plan must remove nothing.
7. ``drunken-install hook --apply`` twice — the first must record the temp venv's OWN
   ``drunken-install`` executable (DG-514 blocker B), the second must say "already present".
8. ``drunken-install context`` — valid JSON, at most 2,500 characters, naming ``/prd`` and
   ``worker``.
9. ``drunken-doctor --json`` in the same temp ``HOME`` — the ``routes.session_hook`` check must be
   ``ok``.
10. Confirm the real ``~/.claude/settings.json`` and ``~/.drunken/projects.json`` — captured
    BEFORE any ``HOME`` override took effect — are byte-for-byte and mtime-for-mtime untouched.

Prints a final PASS/FAIL table and exits 1 if anything failed. Run directly:

    uv run python scripts/release_smoke.py

or through ``pytest -m integration`` via ``tests/test_release_smoke.py`` (deselected by default,
the same way the repository's ``e2e`` and ``routing`` marks are).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The two real files this run must never change — captured against the REAL home, before any
#: HOME/USERPROFILE/APPDATA override below takes effect for the subprocesses this script runs.
_REAL_HOME = Path(
    os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home()
)
_REAL_SETTINGS = _REAL_HOME / ".claude" / "settings.json"
_REAL_REGISTRY = _REAL_HOME / ".drunken" / "projects.json"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SmokeReport:
    results: list[CheckResult] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        self.results.append(CheckResult(name, passed, detail))
        return passed

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    def render(self) -> str:
        width = max((len(r.name) for r in self.results), default=0)
        lines = [
            "",
            "=" * (width + 14),
            "RELEASE SMOKE TEST — PASS/FAIL",
            "=" * (width + 14),
        ]
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lines.append(f"[{mark}] {r.name:<{width}}  {r.detail}")
        lines.append("-" * (width + 14))
        lines.append("OVERALL: " + ("PASS" if self.ok else "FAIL"))
        return "\n".join(lines)


def _run(
    argv: list[str], *, env: Optional[dict[str, str]] = None, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argv built from known paths, shell=False
        argv,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        shell=False,
        check=False,
    )


def _snapshot(path: Path) -> Optional[tuple[int, float, bytes]]:
    """(size, mtime, content) of *path*, or ``None`` if it does not exist. Read-only."""
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_size, stat.st_mtime, path.read_bytes()


def build_wheel(report: SmokeReport, dest: Path) -> Optional[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    # `uv build` must run from the checkout (reads its own pyproject.toml via cwd).
    result = subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "build", "--wheel", "--out-dir", str(dest)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300.0,
        shell=False,
        check=False,
    )
    wheels = sorted(dest.glob("*.whl"))
    ok = result.returncode == 0 and bool(wheels)
    report.record(
        "build.wheel",
        ok,
        str(wheels[-1]) if wheels else (result.stdout + result.stderr)[-400:],
    )
    return wheels[-1] if ok else None


def _scripts_dir(venv_dir: Path) -> Path:
    return venv_dir / "Scripts" if os.name == "nt" else venv_dir / "bin"


def _exe(venv_dir: Path, name: str) -> Path:
    scripts = _scripts_dir(venv_dir)
    return scripts / (f"{name}.exe" if os.name == "nt" else name)


def create_and_install(report: SmokeReport, venv_dir: Path, wheel: Path) -> bool:
    venv_result = subprocess.run(  # nosec B603
        ["uv", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=120.0,
        shell=False,
        check=False,
    )
    python = _exe(venv_dir, "python")
    if venv_result.returncode != 0 or not python.is_file():
        report.record(
            "venv.create", False, (venv_result.stdout + venv_result.stderr)[-400:]
        )
        return False
    report.record("venv.create", True, str(venv_dir))

    install_result = subprocess.run(  # nosec B603
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        capture_output=True,
        text=True,
        timeout=180.0,
        shell=False,
        check=False,
    )
    ok = install_result.returncode == 0
    report.record(
        "venv.install_wheel",
        ok,
        "installed" if ok else (install_result.stdout + install_result.stderr)[-400:],
    )
    return ok


def _fake_home_env(fake_home: Path) -> dict[str, str]:
    """A full environment, inheriting PATH etc., with HOME/USERPROFILE/APPDATA redirected into
    *fake_home* — so every subprocess below can only ever read or write there, never the real
    operator home."""
    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)
    env["APPDATA"] = str(fake_home / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(fake_home / "AppData" / "Local")
    for name in ("LOGNAME", "USER", "LNAME"):
        env.pop(name, None)
    return env


def run_smoke(report: SmokeReport, venv_dir: Path, fake_home: Path) -> None:
    env = _fake_home_env(fake_home)
    drunken_install = _exe(venv_dir, "drunken-install")
    drunken_doctor = _exe(venv_dir, "drunken-doctor")

    before_settings = _snapshot(_REAL_SETTINGS)
    before_registry = _snapshot(_REAL_REGISTRY)

    all_result = _run([str(drunken_install), "all"], env=env)
    all_ok = all_result.returncode == 0
    report.record("install.all", all_ok, (all_result.stdout + all_result.stderr)[-300:])

    skills_dir = fake_home / ".claude" / "skills"
    agents_dir = fake_home / ".claude" / "agents"
    core_skills = (
        sum(1 for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else 0
    )
    core_agents = (
        sum(1 for p in agents_dir.glob("*.md") if p.name != "INDEX.md")
        if agents_dir.is_dir()
        else 0
    )
    report.record(
        "install.all.counts",
        core_skills >= 15 and core_agents >= 3,
        f"{core_skills} core skill(s), {core_agents} core agent(s)",
    )

    extras_result = _run([str(drunken_install), "extras", "--apply"], env=env)
    extras_ok = extras_result.returncode == 0
    report.record(
        "install.extras_apply",
        extras_ok,
        (extras_result.stdout + extras_result.stderr)[-300:],
    )

    all_skills = (
        sum(1 for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else 0
    )
    all_agents = (
        sum(1 for p in agents_dir.glob("*.md") if p.name != "INDEX.md")
        if agents_dir.is_dir()
        else 0
    )
    report.record(
        "install.extras.counts",
        all_skills >= 31 and all_agents >= 18,
        f"{all_skills} skill(s) total, {all_agents} agent(s) total "
        f"(expect >=15+16=31 skills, >=3+15=18 agents)",
    )

    status_result = _run([str(drunken_install), "status"], env=env)
    status_out = status_result.stdout
    status_ok = (
        status_result.returncode == 0
        and "up to date" in status_out
        and "retired" not in status_out
    )
    report.record(
        "status.no_retired_line",
        status_ok,
        "clean" if status_ok else status_out[-400:],
    )

    prune_result = _run([str(drunken_install), "skills", "--prune"], env=env)
    prune_out = prune_result.stdout
    # `_print_orphans` only prints a "retired" section header at all when there is something
    # retired to report; absence of that header is exactly "removes nothing" for this run.
    prune_ok = prune_result.returncode == 0 and "retired," not in prune_out
    report.record(
        "prune.plan_removes_nothing",
        prune_ok,
        "clean" if prune_ok else prune_out[-400:],
    )

    hook_first = _run([str(drunken_install), "hook", "--apply"], env=env)
    hook_first_out = hook_first.stdout
    venv_marker = str(_scripts_dir(venv_dir))
    first_ok = (
        hook_first.returncode == 0
        and venv_marker.casefold() in hook_first_out.casefold()
        and ": added" in hook_first_out
    )
    report.record(
        "hook.apply_records_this_venv",
        first_ok,
        hook_first_out.strip()[-300:] if not first_ok else venv_marker,
    )

    hook_second = _run([str(drunken_install), "hook", "--apply"], env=env)
    second_ok = hook_second.returncode == 0 and "already present" in hook_second.stdout
    report.record(
        "hook.second_apply_is_noop",
        second_ok,
        "already present" if second_ok else hook_second.stdout.strip()[-300:],
    )

    context_result = _run([str(drunken_install), "context"], env=env)
    context_text = context_result.stdout.strip()
    context_ok = False
    context_detail = ""
    if context_result.returncode == 0:
        try:
            payload = json.loads(context_text)
        except ValueError as exc:
            context_detail = f"not valid JSON: {exc}"
        else:
            additional = (
                payload.get("hookSpecificOutput", {}).get("additionalContext", "")
                if isinstance(payload, dict)
                else ""
            )
            context_ok = (
                len(context_text) <= 2500
                and "/prd" in additional
                and "worker" in additional
            )
            context_detail = f"{len(context_text)} chars"
    else:
        context_detail = (context_result.stdout + context_result.stderr)[-300:]
    report.record("context.valid_and_bounded", context_ok, context_detail)

    registry_dir = fake_home / ".drunken"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_path = registry_dir / "projects.json"
    if not registry_path.is_file():
        registry_path.write_text('{"version": 2, "projects": {}}', encoding="utf-8")

    doctor_result = _run([str(drunken_doctor), "--json"], env=env)
    session_hook_ok = False
    doctor_detail = ""
    if doctor_result.returncode in (
        0,
        1,
    ):  # 1 just means "some other check failed/warned"
        try:
            doctor_payload: Any = json.loads(doctor_result.stdout)
        except ValueError as exc:
            doctor_detail = f"doctor did not print valid JSON: {exc}"
        else:
            checks = doctor_payload.get("checks", [])
            match = next(
                (c for c in checks if c.get("name") == "routes.session_hook"), None
            )
            if match is None:
                doctor_detail = (
                    "routes.session_hook check not present in doctor's report"
                )
            else:
                session_hook_ok = match.get("status") == "ok"
                doctor_detail = (
                    f"status={match.get('status')!r}: {match.get('detail', '')}"
                )
    else:
        doctor_detail = (doctor_result.stdout + doctor_result.stderr)[-300:]
    report.record("doctor.routes_session_hook_ok", session_hook_ok, doctor_detail)

    after_settings = _snapshot(_REAL_SETTINGS)
    after_registry = _snapshot(_REAL_REGISTRY)
    real_home_untouched = (
        before_settings == after_settings and before_registry == after_registry
    )
    report.record(
        "real_home.never_touched",
        real_home_untouched,
        f"{_REAL_SETTINGS} and {_REAL_REGISTRY} unchanged"
        if real_home_untouched
        else "the real ~/.claude/settings.json or ~/.drunken/projects.json changed during this run",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="drunken-release-smoke-") as tmp:
        tmp_path = Path(tmp)
        report = SmokeReport()

        wheel = build_wheel(report, tmp_path / "dist")
        if wheel is None:
            print(report.render())
            return 1

        venv_dir = tmp_path / "venv"
        if not create_and_install(report, venv_dir, wheel):
            print(report.render())
            return 1

        fake_home = tmp_path / "fakehome"
        fake_home.mkdir(parents=True, exist_ok=True)
        run_smoke(report, venv_dir, fake_home)

    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
