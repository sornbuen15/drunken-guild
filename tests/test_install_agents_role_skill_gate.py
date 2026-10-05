# mypy: ignore-errors
"""DG-402, coordinator review HIGH finding 4.

Claude Code's own subagent docs (https://code.claude.com/docs/en/subagents)
say a `skills:` entry naming a skill that is not installed is skipped
silently: "If a listed skill is missing or disabled ... Claude Code skips it
and logs a warning to the debug log." A role adapter installed before its
role skill would therefore run with effectively no role prompt and no
visible error at all.

`install_agents.sh` / `.ps1` must refuse to install a role adapter whose
skill is not present under the *target* `~/.claude/skills/`, naming the
missing skill and the remediation command, rather than installing it anyway.

Every test here runs against a sandboxed `$HOME`, guarded by the same canary
pattern `test_install_index_determinism.py` uses: a child process is asked
to print `$HOME` from inside itself immediately after the redirection, and
the test refuses to trust anything the run did if that print does not match.
Nothing here is ever run against the operator's real `~/.claude`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
BASH = shutil.which("bash")


def _sandbox(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of `agents/`, `skills/` and `scripts/install/` under *tmp_path*,
    and a fresh, empty `$HOME` beside it -- never the real repository tree,
    never the operator's real `$HOME`."""
    sandbox = tmp_path / "repo"
    sandbox.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "agents", sandbox / "agents")
    shutil.copytree(REPO_ROOT / "skills", sandbox / "skills")
    shutil.copytree(REPO_ROOT / "scripts" / "install", sandbox / "scripts" / "install")
    home = tmp_path / "home"
    home.mkdir(parents=True)
    return sandbox, home


def _run_sh(
    script: Path,
    home: Path,
    extra_args: str = "",
    prepend_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a bash installer with `$HOME` redirected to *home* via the child
    process's own environment -- no string-built canary command here, since
    nested quoting through `bash -c '...'` is exactly the kind of fragile
    construction DG-321 warns about. The canary is the installer's own
    "Target: ..." line, which always echoes `$GLOBAL_AGENTS_DIR` (built from
    `$HOME`) back out -- confirmed by :func:`_assert_canary`.

    *prepend_path*, if given, goes in front of `$PATH` -- used to put a stub
    `python3` ahead of the real one, to prove the installer refuses rather
    than fails open when python3 itself misbehaves."""
    assert BASH is not None
    import os

    env = dict(os.environ)
    env["HOME"] = home.as_posix()
    if prepend_path is not None:
        env["PATH"] = f"{prepend_path.as_posix()}:{env.get('PATH', '')}"
    return subprocess.run(
        [BASH, str(script), *([extra_args] if extra_args else [])],
        capture_output=True,
        text=True,
        env=env,
    )


def _run_ps(
    script: Path, home: Path, extra_args: str = ""
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    command = (
        f"Set-Variable -Name HOME -Value '{home}' -Force -Scope Global; "
        f"$canary = $HOME; "
        f'Write-Host "CANARY:$canary"; '
        f"if ($canary -ne '{home}') {{ "
        f"Write-Host 'CANARY MISMATCH -- aborting, running nothing'; exit 97 "
        f"}}; "
        f"& '{script}' {extra_args}"
    ).strip()
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
    )


def _real_home_agents_dir() -> Path:
    import os

    return Path(os.path.expanduser("~")) / ".claude" / "agents"


def _real_home_manager_mtime() -> float | None:
    manager = _real_home_agents_dir() / "manager.md"
    return manager.stat().st_mtime if manager.is_file() else None


def _assert_sh_ran_against(
    result: subprocess.CompletedProcess[str], home: Path
) -> None:
    """The installer always prints a `Target:` line. Git Bash on Windows
    rewrites a Windows temp path in `$HOME` to its own `/tmp` mount, so the
    printed line cannot be string-matched against the Python-side path --
    the safety property that actually matters is checked instead: the
    operator's *real* `~/.claude/agents` was never named or touched. Whether
    the redirection reached the *sandboxed* home is then confirmed
    functionally, by each test's own assertions about files under *home*."""
    assert "Target:" in result.stdout, (
        f"the installer printed no Target line at all\n{result.stdout}\n{result.stderr}"
    )
    real = str(_real_home_agents_dir()).replace("\\", "/")
    assert real not in result.stdout.replace("\\", "/"), (
        "the installer's Target line names the operator's real ~/.claude/agents "
        f"-- HOME redirection did not take effect\n{result.stdout}"
    )


def _assert_ps_canary(result: subprocess.CompletedProcess[str], home: Path) -> None:
    assert f"CANARY:{home}" in result.stdout, (
        "the canary never confirmed $HOME inside the child process -- refusing "
        f"to trust anything the run did\n{result.stdout}\n{result.stderr}"
    )
    assert result.returncode != 97, (
        "HOME redirection did not take effect; aborted before the installer "
        f"ran\n{result.stdout}\n{result.stderr}"
    )


@pytest.fixture(autouse=True)
def _real_home_is_never_touched() -> None:
    """Extra defence beneath the string check above: the operator's real
    `~/.claude/agents/manager.md` must have the same mtime after every test
    in this module as before it. If HOME redirection ever silently failed
    and a test ran for real, this is what catches it even if the printed
    Target line happened to look sandboxed."""
    before = _real_home_manager_mtime()
    yield
    after = _real_home_manager_mtime()
    assert before == after, (
        "the operator's real ~/.claude/agents/manager.md changed during a "
        "sandboxed test -- HOME redirection failed silently"
    )


def _write_stub_python3(bin_dir: Path, body: str) -> None:
    """A fake `python3` on `PATH`, ahead of the real one -- stands in for a
    misbehaving interpreter (a broken shim, reproduced during review: it can
    exit 0 and print nothing at all for *any* script, `_role_skill.py`
    included)."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "python3"
    stub.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    stub.chmod(0o755)


def _seed_skill(home: Path, name: str) -> None:
    skill_dir = home / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: seeded for a sandboxed test.\n---\n",
        encoding="utf-8",
    )


class TestInstallRefusesWithoutTheRoleSkillInstalled:
    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_sh_refuses_and_installs_nothing(self, tmp_path: Path) -> None:
        sandbox, home = _sandbox(tmp_path)
        script = sandbox / "scripts" / "install" / "install_agents.sh"

        result = _run_sh(script, home)
        _assert_sh_ran_against(result, home)

        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"install_agents.sh exited 0 with no role skill installed at "
            f"all\n{combined}"
        )
        assert "Refusing" in combined and "manager" in combined, (
            f"no refusal naming the missing skill was printed\n{combined}"
        )
        installed = home / ".claude" / "agents" / "manager.md"
        assert not installed.exists(), (
            "manager.md was installed despite its role skill being absent"
        )

    @pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
    def test_ps1_refuses_and_installs_nothing(self, tmp_path: Path) -> None:
        sandbox, home = _sandbox(tmp_path)
        script = sandbox / "scripts" / "install" / "install_agents.ps1"

        result = _run_ps(script, home)
        _assert_ps_canary(result, home)

        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"install_agents.ps1 exited 0 with no role skill installed at "
            f"all\n{combined}"
        )
        assert "Refusing" in combined and "manager" in combined, (
            f"no refusal naming the missing skill was printed\n{combined}"
        )
        installed = home / ".claude" / "agents" / "manager.md"
        assert not installed.exists(), (
            "manager.md was installed despite its role skill being absent"
        )


class TestInstallSucceedsOnceTheRoleSkillsAreInstalled:
    """The companion positive case -- the migration order the Boss must
    follow: install_skills first, then install_agents."""

    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_sh_installs_once_skills_are_present(self, tmp_path: Path) -> None:
        sandbox, home = _sandbox(tmp_path)
        for name in ("manager", "worker", "reviewer"):
            _seed_skill(home, name)
        script = sandbox / "scripts" / "install" / "install_agents.sh"

        result = _run_sh(script, home)
        _assert_sh_ran_against(result, home)

        assert result.returncode == 0, (
            f"install_agents.sh refused even though all three role skills "
            f"are installed\n{result.stdout}\n{result.stderr}"
        )
        for name in ("manager", "worker", "reviewer"):
            assert (home / ".claude" / "agents" / f"{name}.md").is_file()

    @pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
    def test_ps1_installs_once_skills_are_present(self, tmp_path: Path) -> None:
        sandbox, home = _sandbox(tmp_path)
        for name in ("manager", "worker", "reviewer"):
            _seed_skill(home, name)
        script = sandbox / "scripts" / "install" / "install_agents.ps1"

        result = _run_ps(script, home)
        _assert_ps_canary(result, home)

        assert result.returncode == 0, (
            f"install_agents.ps1 refused even though all three role skills "
            f"are installed\n{result.stdout}\n{result.stderr}"
        )
        for name in ("manager", "worker", "reviewer"):
            assert (home / ".claude" / "agents" / f"{name}.md").is_file()


class TestBothInstallersProduceIdenticalAdapterBytes:
    """DG-380's precedent, applied to the new generated artefact: a Windows
    run and a macOS/Linux run of the same tree must write the same
    `agents/<role>.md` bytes once both role skills are installed."""

    @pytest.mark.skipif(
        BASH is None or POWERSHELL is None,
        reason="needs both a bash and a PowerShell host",
    )
    def test_sh_and_ps1_agree_byte_for_byte(self, tmp_path: Path) -> None:
        sh_sandbox, home_sh = _sandbox(tmp_path / "sh")
        ps_sandbox, home_ps = _sandbox(tmp_path / "ps")
        for home in (home_sh, home_ps):
            for name in ("manager", "worker", "reviewer"):
                _seed_skill(home, name)

        sh_result = _run_sh(
            sh_sandbox / "scripts" / "install" / "install_agents.sh", home_sh
        )
        _assert_sh_ran_against(sh_result, home_sh)
        assert sh_result.returncode == 0, sh_result.stdout + sh_result.stderr

        ps_result = _run_ps(
            ps_sandbox / "scripts" / "install" / "install_agents.ps1", home_ps
        )
        _assert_ps_canary(ps_result, home_ps)
        assert ps_result.returncode == 0, ps_result.stdout + ps_result.stderr

        for name in ("manager", "worker", "reviewer"):
            sh_bytes = (home_sh / ".claude" / "agents" / f"{name}.md").read_bytes()
            ps_bytes = (home_ps / ".claude" / "agents" / f"{name}.md").read_bytes()
            assert sh_bytes == ps_bytes, (
                f"install_agents.sh and .ps1 disagree about {name}.md's bytes"
            )


class TestTheRefusalIsNotAccidentallyRemovable:
    """Mutation proof, in the same spirit as DG-423's `cut -c is gone` guard:
    strip the refusal block from a sandboxed copy of each script and prove
    the old, dangerous behaviour -- a silent, successful install of a role
    adapter whose skill is missing -- resurfaces. If this test ever starts
    passing on the *unmutated* script, the mutation stopped mutating
    anything real."""

    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_removing_the_sh_guard_reintroduces_the_silent_install(
        self, tmp_path: Path
    ) -> None:
        sandbox, home = _sandbox(tmp_path)
        script = sandbox / "scripts" / "install" / "install_agents.sh"
        text = script.read_text(encoding="utf-8")
        assert "MISSING_ROLE_SKILL" in text, "the guard itself is already gone"
        mutated = text.replace(
            'if [ ! -f "$GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md" ]; then',
            "if false; then",
        )
        assert mutated != text, "the mutation did not change anything -- fix it"
        script.write_text(mutated, encoding="utf-8")

        result = _run_sh(script, home)
        _assert_sh_ran_against(result, home)
        assert result.returncode == 0, (
            "removing the guard should reproduce the old silent-install "
            f"behaviour (exit 0)\n{result.stdout}\n{result.stderr}"
        )
        assert (home / ".claude" / "agents" / "manager.md").is_file(), (
            "with the guard removed, manager.md should install despite its "
            "role skill being absent -- the exact defect the guard exists "
            "to prevent"
        )


class TestTheGateFailsClosedWhenPython3ItselfMisbehaves:
    """DG-402, coordinator review, CRITICAL. The previous `_role_skill()`
    ended in `2>/dev/null || true`, and the caller refused only when its
    result was non-empty -- so a `python3` that failed outright, or that
    exited 0 printing nothing at all (reproduced here with a stub: this is
    exactly what a broken shim can do, for *any* script, not only
    `_role_skill.py`), read as "no role dependency" and the adapter
    installed anyway. Fail *open* is the wrong failure mode for a safety
    gate; both stubs below must now be refused, loudly, naming python3.

    Seen red first against the pre-fix script (reverting the fix locally
    and re-running these two reproduces: exit 0, `manager.md` installed,
    no complaint at all)."""

    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_a_stub_python3_exiting_0_with_no_output_is_refused(
        self, tmp_path: Path
    ) -> None:
        sandbox, home = _sandbox(tmp_path)
        bin_dir = tmp_path / "stub-bin"
        _write_stub_python3(bin_dir, "exit 0")
        script = sandbox / "scripts" / "install" / "install_agents.sh"

        result = _run_sh(script, home, prepend_path=bin_dir)

        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"a python3 stub that exits 0 printing nothing must be refused, "
            f"not treated as success\n{combined}"
        )
        assert "python3" in combined.lower(), (
            f"the refusal must name python3 as the problem\n{combined}"
        )
        assert not (home / ".claude" / "agents" / "manager.md").exists(), (
            "manager.md must not install when python3 cannot be trusted to "
            f"answer the role-skill check\n{combined}"
        )

    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_a_stub_python3_exiting_non_zero_is_refused(self, tmp_path: Path) -> None:
        sandbox, home = _sandbox(tmp_path)
        bin_dir = tmp_path / "stub-bin"
        _write_stub_python3(bin_dir, "exit 7")
        script = sandbox / "scripts" / "install" / "install_agents.sh"

        result = _run_sh(script, home, prepend_path=bin_dir)

        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"a python3 stub that exits non-zero must be refused, not "
            f"treated as success\n{combined}"
        )
        assert "python3" in combined.lower(), (
            f"the refusal must name python3 as the problem\n{combined}"
        )
        assert not (home / ".claude" / "agents" / "manager.md").exists(), (
            "manager.md must not install when python3 exits non-zero on the "
            f"role-skill check\n{combined}"
        )

    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_mutation_reintroducing_the_swallow_reproduces_the_fail_open(
        self, tmp_path: Path
    ) -> None:
        """The actual before/after proof: restore the old `|| true` shape
        over the fixed script and show the stub from the first test above
        now installs anyway -- the exact bug this PR fixes."""
        sandbox, home = _sandbox(tmp_path)
        bin_dir = tmp_path / "stub-bin"
        _write_stub_python3(bin_dir, "exit 0")
        script = sandbox / "scripts" / "install" / "install_agents.sh"
        text = script.read_text(encoding="utf-8")

        assert '"$_PY3_PROBE" != "ok"' in text, (
            "the python3 sanity probe is already gone"
        )
        mutated = text.replace(
            '_PY3_PROBE="$(python3 -c \'print("ok")\' 2>/dev/null </dev/null || true)"\n'
            '  if [ "$_PY3_PROBE" != "ok" ]; then',
            '_PY3_PROBE="ok"\n  if false; then',
        )
        assert mutated != text, "the probe-removal mutation did not change anything"

        old_vulnerable_caller = (
            '    ROLE_SKILL="$(_role_skill "$agent_name" 2>/dev/null </dev/null || true)"\n'
            '    if [ -n "$ROLE_SKILL" ] && [ ! -f "$GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md" ]; then\n'
            "      echo -e \"${RED}  [x] Refusing: ${agent_name} needs the '${ROLE_SKILL}' skill, not installed at $GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md${NC}\" >&2\n"
            '      echo -e "${RED}      Run install_skills.sh first, then re-run install_agents.sh.${NC}" >&2\n'
            "      MISSING_ROLE_SKILL=true\n"
            "      continue\n"
            "    fi\n"
        )
        fixed_caller_start = '    if ROLE_SKILL="$(_role_skill "$agent_name")"; then'
        fixed_caller_end = (
            '    if [ ! -f "$GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md" ]; then\n'
            "      echo -e \"${RED}  [x] Refusing: ${agent_name} needs the '${ROLE_SKILL}' skill, not installed at $GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md${NC}\" >&2\n"
            '      echo -e "${RED}      Run install_skills.sh first, then re-run install_agents.sh.${NC}" >&2\n'
            "      MISSING_ROLE_SKILL=true\n"
            "      continue\n"
            "    fi\n"
        )
        start_idx = mutated.index(fixed_caller_start)
        end_idx = mutated.index(fixed_caller_end) + len(fixed_caller_end)
        assert start_idx < end_idx, "could not locate the fixed caller block to revert"
        mutated = mutated[:start_idx] + old_vulnerable_caller + mutated[end_idx:]
        assert mutated != text, "the caller-revert mutation did not change anything"
        script.write_text(mutated, encoding="utf-8")

        result = _run_sh(script, home, prepend_path=bin_dir)
        assert result.returncode == 0, (
            "reintroducing the old swallow-to-empty shape should reproduce "
            f"the fail-open bug (exit 0)\n{result.stdout}\n{result.stderr}"
        )
        assert (home / ".claude" / "agents" / "manager.md").is_file(), (
            "with the swallow reintroduced, manager.md should install "
            "despite a python3 stub that cannot answer the role-skill "
            "check at all -- the exact bug this PR fixes"
        )


class TestBothInstallersRefuseAManifestMissingASkillKey:
    """DG-402, coordinator review, HIGH (round 2). A manifest edit that
    drops one role's `skill` key is the realistic mistake the old `-`
    sentinel let straight through: both installers must refuse that one
    adapter even though its skill *is* installed -- the defect is the
    manifest, not a missing skill directory."""

    @staticmethod
    def _drop_skill_key(sandbox: Path, role: str) -> None:
        import json

        sources_json = sandbox / "agents" / "_sources.json"
        data = json.loads(sources_json.read_text(encoding="utf-8"))
        del data[role]["skill"]
        sources_json.write_text(json.dumps(data), encoding="utf-8")

    @pytest.mark.skipif(BASH is None, reason="no bash host on this machine")
    def test_sh_refuses_the_one_adapter_with_the_defective_entry(
        self, tmp_path: Path
    ) -> None:
        sandbox, home = _sandbox(tmp_path)
        for name in ("manager", "worker", "reviewer"):
            _seed_skill(home, name)
        self._drop_skill_key(sandbox, "worker")
        script = sandbox / "scripts" / "install" / "install_agents.sh"

        result = _run_sh(script, home)
        _assert_sh_ran_against(result, home)

        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"a manifest missing worker's 'skill' key must be refused\n{combined}"
        )
        assert not (home / ".claude" / "agents" / "worker.md").exists(), (
            f"worker.md must not install with a defective manifest entry\n{combined}"
        )

    @pytest.mark.skipif(POWERSHELL is None, reason="no PowerShell host on this machine")
    def test_ps1_refuses_the_one_adapter_with_the_defective_entry(
        self, tmp_path: Path
    ) -> None:
        sandbox, home = _sandbox(tmp_path)
        for name in ("manager", "worker", "reviewer"):
            _seed_skill(home, name)
        self._drop_skill_key(sandbox, "worker")
        script = sandbox / "scripts" / "install" / "install_agents.ps1"

        result = _run_ps(script, home)
        _assert_ps_canary(result, home)

        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"a manifest missing worker's 'skill' key must be refused\n{combined}"
        )
        assert not (home / ".claude" / "agents" / "worker.md").exists(), (
            f"worker.md must not install with a defective manifest entry\n{combined}"
        )
