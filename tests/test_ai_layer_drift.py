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


def _retired_list(repo: Path, names: list[str]) -> None:
    """Write `scripts/install/retired_skills.txt` under *repo* — the one list
    that decides what `--prune-apply` may remove and what doctor calls
    "retired" rather than "unrecognised" (DG-359 review finding #1)."""
    target = repo / doctor.RETIRED_SKILLS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(["# retired"] + names) + "\n", encoding="utf-8")


class TestComparingTheInstallToTheSource:
    def test_an_identical_install_is_clean(self, tmp_path):
        content = {"git-workflow": "rules\n", "post-mortem": "record\n"}
        repo = _repo(tmp_path / "src", content)
        install = _install(tmp_path / "dst", content)

        result = doctor.compare_ai_layer(repo, install)

        assert result == {"missing": [], "drifted": [], "extra": []}

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

    def test_an_extra_installed_skill_is_not_drift_but_is_named(self, tmp_path):
        """Something installed that this repo does not produce is not
        "different content for a skill we ship" — it is its own category.
        `compare_ai_layer` must still name it (DG-359): the blind spot was a
        check that only ever asked "are ours all there", so an extra directory
        slipped past both `missing` and `drifted` and the overall result read
        clean."""
        repo = _repo(tmp_path / "src", {"ours": "x\n"})
        install = _install(tmp_path / "dst", {"ours": "x\n", "bigquery-sql": "y\n"})

        result = doctor.compare_ai_layer(repo, install)

        assert result["missing"] == []
        assert result["drifted"] == []
        assert result["extra"] == ["bigquery-sql"]


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


class TestExtraInstalledSkillsEndTheOkDG359:
    """DG-359. `install_skills.sh` copies in and prunes nothing, and this check
    answered only "are ours all there" — never "is anything else there too".
    Measured: 34 retired skill directories stayed installed after the 2.0.0
    re-scope, and `drunken-doctor` reported "all 11 skills match the source"
    in the same run, because an extra directory never entered the comparison
    at all.

    Seen failing first against the pre-DG-359 `_check_ai_layer`: a fixture
    install root holding a retired skill was reported `ok`, identically to one
    holding only the 11 shipped skills.
    """

    def test_a_retired_skill_still_installed_ends_the_ok(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        repo = _repo(src, {"ours": "x\n"})
        _retired_list(repo, ["kanban-io"])
        install = _install(tmp_path / "dst", {"ours": "x\n", "kanban-io": "old\n"})
        monkeypatch.setattr(
            doctor, "AI_LAYER_ROOTS", (("claude.skills", str(install)),)
        )

        report = doctor.Report()
        doctor._check_ai_layer(report, root=repo)

        entry = next(c for c in report.checks if c.name == "ai_layer.claude.skills")
        assert entry.status != "ok", (
            "a retired skill is still installed, and today's report must not "
            "read ok the way it did before DG-359"
        )
        assert "kanban-io" in entry.detail
        assert "retired, will be pruned" in entry.detail

    def test_an_extra_not_on_the_retired_list_is_unrecognised_not_retired(
        self, tmp_path, monkeypatch
    ):
        """Review finding #1: a check that calls any unshipped directory
        "retired" is exactly what let `--prune-apply` delete a hand-written,
        never-shipped skill. Something not on the tracked list must be named
        a different thing — `unrecognised` — so it is never on the list
        `--prune-apply` reads either."""
        src = tmp_path / "src"
        repo = _repo(src, {"ours": "x\n"})
        _retired_list(repo, ["kanban-io"])
        install = _install(
            tmp_path / "dst", {"ours": "x\n", "my-own-private-skill": "mine\n"}
        )
        monkeypatch.setattr(
            doctor, "AI_LAYER_ROOTS", (("claude.skills", str(install)),)
        )

        report = doctor.Report()
        doctor._check_ai_layer(report, root=repo)

        entry = next(c for c in report.checks if c.name == "ai_layer.claude.skills")
        assert entry.status != "ok"
        assert "my-own-private-skill" in entry.detail
        assert "unrecognised" in entry.detail
        assert "retired, will be pruned" not in entry.detail, (
            "a name absent from retired_skills.txt must never be labelled "
            "'retired, will be pruned' — that label is what a prune step trusts"
        )

    def test_a_skill_merely_moved_to_drunken_extras_is_named_separately(
        self, tmp_path, monkeypatch
    ):
        """`plugins/drunken-extras/skills/` holds first-party skills that moved
        out of `skills/` rather than being retired (DG-352/353). An install
        still carrying one of those is a different finding from one carrying
        something genuinely withdrawn, and the report must not conflate them."""
        src = tmp_path / "src"
        repo = _repo(src, {"ours": "x\n"})
        _retired_list(repo, ["kanban-io"])
        extras_dir = src / "plugins" / "drunken-extras" / "skills" / "acronym-namer"
        extras_dir.mkdir(parents=True)
        (extras_dir / "SKILL.md").write_text("extra\n", encoding="utf-8")

        install = _install(
            tmp_path / "dst",
            {"ours": "x\n", "acronym-namer": "extra\n", "kanban-io": "old\n"},
        )
        monkeypatch.setattr(
            doctor, "AI_LAYER_ROOTS", (("claude.skills", str(install)),)
        )

        report = doctor.Report()
        doctor._check_ai_layer(report, root=repo)

        entry = next(c for c in report.checks if c.name == "ai_layer.claude.skills")
        assert entry.status != "ok"
        assert "acronym-namer" in entry.detail
        assert "kanban-io" in entry.detail
        # Named under different labels, not folded into one undifferentiated list.
        assert "drunken-extras" in entry.detail
        assert "retired, will be pruned" in entry.detail

    def test_a_retired_name_that_is_also_a_drunken_extras_skill_is_never_prunable(
        self, tmp_path, monkeypatch
    ):
        """A name can be on `retired_skills.txt` and also be shipped today
        under `plugins/drunken-extras/skills/` — the guild's own list is not
        proof against drift either. `moved` must win: this must never be
        counted toward "retired" (prunable)."""
        src = tmp_path / "src"
        repo = _repo(src, {"ours": "x\n"})
        _retired_list(repo, ["acronym-namer"])
        extras_dir = src / "plugins" / "drunken-extras" / "skills" / "acronym-namer"
        extras_dir.mkdir(parents=True)
        (extras_dir / "SKILL.md").write_text("extra\n", encoding="utf-8")

        install = _install(
            tmp_path / "dst", {"ours": "x\n", "acronym-namer": "extra\n"}
        )
        monkeypatch.setattr(
            doctor, "AI_LAYER_ROOTS", (("claude.skills", str(install)),)
        )

        report = doctor.Report()
        doctor._check_ai_layer(report, root=repo)

        entry = next(c for c in report.checks if c.name == "ai_layer.claude.skills")
        assert "drunken-extras" in entry.detail
        assert "retired, will be pruned" not in entry.detail

    def test_a_name_listed_in_dot_external_is_not_reported(self, tmp_path, monkeypatch):
        """`skills/.external` is this repository's own statement that a name
        is deliberately third-party. Reporting it as an unexplained extra
        every run is exactly the noise a check earns being ignored for."""
        src = tmp_path / "src"
        repo = _repo(src, {"ours": "x\n"})
        (src / "skills" / ".external").write_text(
            "# comment\nbigquery-sql\n", encoding="utf-8"
        )

        install = _install(tmp_path / "dst", {"ours": "x\n", "bigquery-sql": "y\n"})
        monkeypatch.setattr(
            doctor, "AI_LAYER_ROOTS", (("claude.skills", str(install)),)
        )

        report = doctor.Report()
        doctor._check_ai_layer(report, root=repo)

        entry = next(c for c in report.checks if c.name == "ai_layer.claude.skills")
        assert entry.status == "ok"
        assert "bigquery-sql" not in entry.detail


class TestRetiredSkillNamesDG359:
    """DG-359 review finding #1. `scripts/install/retired_skills.txt` is the
    one list both install scripts' `--prune-apply` and this check read for
    what "retired" means — and it must never be able to name something the
    guild currently ships, or a prune step trusting it could delete that."""

    def test_comments_and_blank_lines_are_ignored(self, tmp_path):
        repo = tmp_path
        _retired_list(repo, ["kanban-io", "", "squad-workflow"])

        assert doctor.retired_skill_names(repo) == {"kanban-io", "squad-workflow"}

    def test_crlf_line_endings_parse_the_same_as_lf(self, tmp_path):
        target = tmp_path / doctor.RETIRED_SKILLS_FILE
        target.parent.mkdir(parents=True)
        target.write_bytes(b"# comment\r\nkanban-io\r\n\r\nsquad-workflow\r\n")

        assert doctor.retired_skill_names(tmp_path) == {"kanban-io", "squad-workflow"}

    def test_a_missing_file_is_an_empty_list_not_an_error(self, tmp_path):
        assert doctor.retired_skill_names(tmp_path) == set()

    def test_no_name_on_the_real_list_is_a_currently_shipped_skill(self):
        """The actual, committed list against the actual, committed
        `skills/` tree — not a fixture. If this ever fails, `--prune-apply`
        run today could delete a skill this repository ships."""
        real_root = Path(__file__).resolve().parent.parent
        retired = doctor.retired_skill_names(real_root)
        shipped = set(doctor.repo_skills(real_root))

        overlap = retired & shipped
        assert not overlap, (
            f"{sorted(overlap)} are on scripts/install/retired_skills.txt "
            "and are also skills this repository currently ships — a prune "
            "step reading that list could delete them"
        )


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


class TestRetiredSkillNamesDecodeSafetyDG475:
    """DG-475: ``retired_skill_names`` read ``retired_skills.txt`` with no
    ``try``/``except`` at all, so a list in another encoding raised an
    uncaught ``UnicodeDecodeError`` instead of the same "nothing to read"
    fallback a missing file already gets."""

    def test_a_utf16_list_does_not_raise(self, tmp_path):
        target = tmp_path / doctor.RETIRED_SKILLS_FILE
        target.parent.mkdir(parents=True)
        target.write_bytes("kanban-io\n".encode("utf-16"))

        assert doctor.retired_skill_names(tmp_path) == set()

    def test_a_latin1_list_does_not_raise(self, tmp_path):
        target = tmp_path / doctor.RETIRED_SKILLS_FILE
        target.parent.mkdir(parents=True)
        target.write_bytes(b"caf\xe9\n")

        assert doctor.retired_skill_names(tmp_path) == set()


class TestExternalSkillNamesDG475:
    """``external_skill_names`` reads ``skills/.external`` the same way
    ``retired_skill_names`` reads its own list, and had the same gap: no
    ``try``/``except`` around the read at all."""

    def test_names_are_read(self, tmp_path):
        target = tmp_path / "skills" / ".external"
        target.parent.mkdir(parents=True)
        target.write_text("# comment\nthird-party-skill\n", encoding="utf-8")

        assert doctor.external_skill_names(tmp_path) == {"third-party-skill"}

    def test_a_missing_file_is_an_empty_set_not_an_error(self, tmp_path):
        assert doctor.external_skill_names(tmp_path) == set()

    def test_a_utf16_file_does_not_raise(self, tmp_path):
        target = tmp_path / "skills" / ".external"
        target.parent.mkdir(parents=True)
        target.write_bytes("third-party-skill\n".encode("utf-16"))

        assert doctor.external_skill_names(tmp_path) == set()

    def test_a_latin1_file_does_not_raise(self, tmp_path):
        target = tmp_path / "skills" / ".external"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"caf\xe9\n")

        assert doctor.external_skill_names(tmp_path) == set()
