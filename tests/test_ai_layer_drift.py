# mypy: ignore-errors
"""DG-262. What is installed must be what this repository says, and until now
nothing checked.

`SESSION_CHECKPOINT.md` stated that `~/.claude/` follows this repository. When
somebody finally compared them, `git-workflow` was installed at 120 lines
against 196 in the source, `project-hygiene` at 68 against 88, three skills were
not installed at all, and Antigravity's copy was two months old with 21 of 28
shared skills drifted. Claude and Antigravity were reading two different halves
of the git rules, and neither matched the source.

Every surface reported itself healthy, because no surface was asked.
"""

from pathlib import Path

from core import doctor


def _repo(tmp_path: Path, skills: dict[str, str]) -> Path:
    """A source tree holding *skills*, as {name: SKILL.md content}."""
    for name, body in skills.items():
        skill = tmp_path / "skills" / "category" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(body, encoding="utf-8")
    return tmp_path


def _install(tmp_path: Path, skills: dict[str, str]) -> Path:
    """An install root, flat, as the install scripts write it."""
    root = tmp_path / "installed"
    for name, body in skills.items():
        (root / name).mkdir(parents=True)
        (root / name / "SKILL.md").write_text(body, encoding="utf-8")
    root.mkdir(exist_ok=True)
    return root


class TestComparingTheInstallToTheSource:
    def test_an_identical_install_is_clean(self, tmp_path):
        content = {"git-workflow": "rules\n", "post-mortem": "record\n"}
        repo = _repo(tmp_path / "src", content)
        install = _install(tmp_path / "dst", content)

        result = doctor.compare_ai_layer(repo, install)

        assert result == {"missing": [], "drifted": []}

    def test_a_shorter_installed_copy_is_drift(self, tmp_path):
        """The exact shape of the real failure: same name, same place, less
        content. A count of directories matched the whole time."""
        repo = _repo(tmp_path / "src", {"git-workflow": "the full 196 lines\n"})
        install = _install(tmp_path / "dst", {"git-workflow": "half of them\n"})

        result = doctor.compare_ai_layer(repo, install)

        assert result["drifted"] == ["git-workflow"]
        assert result["missing"] == []

    def test_a_skill_that_never_got_installed_is_named(self, tmp_path):
        repo = _repo(
            tmp_path / "src", {"acronym-namer": "a\n", "confluence-sync": "b\n"}
        )
        install = _install(tmp_path / "dst", {"acronym-namer": "a\n"})

        result = doctor.compare_ai_layer(repo, install)

        assert result["missing"] == ["confluence-sync"]
        assert result["drifted"] == []

    def test_an_extra_installed_skill_is_not_drift(self, tmp_path):
        """Something installed that this repo does not produce is somebody
        else's — the install scripts already report those, and this check must
        not claim ownership of `~/.gemini/config/skills`, where ~30 Apache-2.0
        skills shipped by Google live beside ours."""
        repo = _repo(tmp_path / "src", {"ours": "x\n"})
        install = _install(tmp_path / "dst", {"ours": "x\n", "bigquery-sql": "y\n"})

        result = doctor.compare_ai_layer(repo, install)

        assert result == {"missing": [], "drifted": []}


class TestTheCheckReportsRatherThanFixes:
    def test_a_missing_install_root_is_a_skip_not_a_failure(self, tmp_path):
        """A container, CI or a fresh clone legitimately has no install, and a
        check that cries wolf there is one everybody learns to ignore."""
        repo = _repo(tmp_path / "src", {"ours": "x\n"})
        report = doctor.Report()

        doctor._check_ai_layer(report, root=repo)

        assert report.checks, "the check said nothing at all"
        assert not report.failed

    def test_drift_names_the_skills_and_the_remedy(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path / "src", {"git-workflow": "full\n"})
        install = _install(tmp_path / "dst", {"git-workflow": "short\n"})
        monkeypatch.setattr(
            doctor, "AI_LAYER_ROOTS", (("claude.skills", str(install)),)
        )

        report = doctor.Report()
        doctor._check_ai_layer(report, root=repo)

        entry = next(c for c in report.checks if c.name == "ai_layer.claude.skills")
        assert entry.status == "warn"
        assert "git-workflow" in entry.detail
        # The remedy is an install, which is the operator's to run, not ours.
        assert "install_skills.sh" in entry.detail


class TestTheDeploymentPathFollowsThePackageName:
    """`uv tool` names its directory after the distribution, so DG-264's rename
    from `drunken-team` to `drunken-guild` moved it.

    A constant pointing at the old path made this check answer about a
    deployment that is not the one a host launches — and answer `OK`, because
    the old directory still exists on this machine. A green line about the wrong
    directory is worse than no line.
    """

    def test_an_install_under_the_old_name_is_named_not_skipped(
        self, tmp_path, monkeypatch
    ):
        legacy = tmp_path / "drunken-team"
        legacy.mkdir()

        report = doctor.Report()
        doctor._check_deployment(
            report,
            env_root=tmp_path / "drunken-guild",
            legacy_roots=(str(legacy),),
        )

        entry = next(c for c in report.checks if c.name == "deployment.tool_env")
        assert entry.status == "warn"
        assert "previous package name" in entry.detail
        assert "uv tool install" in entry.detail

    def test_no_install_at_all_is_still_a_skip(self, tmp_path):
        """A container or a fresh clone has neither, and that is not a problem
        to report."""
        report = doctor.Report()
        doctor._check_deployment(
            report,
            env_root=tmp_path / "also-nope",
            legacy_roots=(str(tmp_path / "nope"),),
        )

        entry = next(c for c in report.checks if c.name == "deployment.tool_env")
        assert entry.status == "skip"
