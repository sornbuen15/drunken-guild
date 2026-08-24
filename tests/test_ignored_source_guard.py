# mypy: ignore-errors
"""DG-259. A source file excluded by .gitignore must stop the commit.

`.gitignore` carries `*token*` as a credential-hygiene rule. It matched
tests/test_jira_token_economy.py, `git add -A` skipped it without a word, and
the commit, pre-commit and the local suite all passed -- the suite because the
file was still sitting on disk. A PR was opened claiming 21 new tests and
contained none of them, and nothing in the pipeline could have contradicted it.

The guard is deliberately about the class rather than the two patterns known
today. `*credential*` has the same property, and a project with a token-economy
ticket and a credential resolver will keep producing files that match.
"""

from pathlib import Path

from scripts import check_ignored_sources as guard


class TestWhatCountsAsASourceFile:
    def test_a_python_file_under_tests_counts(self) -> None:
        assert guard.is_source(Path("tests/test_jira_token_economy.py"))

    def test_a_python_file_under_src_counts(self) -> None:
        assert guard.is_source(Path("src/core/token_budget.py"))

    def test_a_shell_script_under_scripts_counts(self) -> None:
        assert guard.is_source(Path("scripts/rotate_token.sh"))

    def test_bytecode_does_not(self) -> None:
        """The check has to survive contact with a working tree. __pycache__ is
        ignored on purpose and there are hundreds of them; flagging those would
        make the guard noise on its first run and it would be switched off."""
        assert not guard.is_source(
            Path("scripts/__pycache__/jira_bridge.cpython-314.pyc")
        )

    def test_a_shared_skill_counts(self) -> None:
        """A skill is source, and nothing else in the tool chain would say so.

        ruff, mypy and pytest all stop at `src`, `tests` and `scripts`, so an
        ignore rule that swallowed a skill would be caught here or nowhere. The
        original form of this bit three times in one session, back when the
        tracked copy lived under an ignored `.agents/` -- existing skills kept
        working because gitignore does not affect files already in the index,
        so only a NEW one was invisible, and the docs pointing at it would have
        shipped referencing a file that was not in the repository."""
        assert guard.is_source(Path("skills/kanban/jira-tickets/SKILL.md"))
        assert guard.is_source(Path("agents/principal-engineer.md"))

    def test_antigravity_state_does_not(self) -> None:
        """`.agents/` proper is not ours and is ignored on purpose."""
        assert not guard.is_source(Path(".agents/discord_config.json"))
        assert not guard.is_source(Path(".agents/board/cards.json"))

    def test_a_file_outside_the_source_directories_does_not(self) -> None:
        """`.env` at the root is ignored and must stay ignored. The guard is
        about source that was meant to be committed, not about every exclusion."""
        assert not guard.is_source(Path(".env"))
        assert not guard.is_source(Path("htmlcov/index.html"))

    def test_a_coverage_artifact_under_a_source_directory_does_not(self) -> None:
        assert not guard.is_source(Path("tests/.pytest_cache/v/cache/lastfailed"))


class TestTheRepositoryRoot:
    """The fourth occurrence, and the first one CI caught rather than a person.

    `.gitignore` listed `Dockerfile` under "Docker simulation config (local
    test only, do not commit)". DG-228 turned it into a deliverable -- it is how
    the pinned install is verified -- and the stale rule kept it out of #114
    while that PR described it at length. `.dockerignore` went in; the
    Dockerfile did not.
    """

    def test_a_dockerfile_counts(self) -> None:
        assert guard.is_source(Path("Dockerfile"))

    def test_a_root_config_counts(self) -> None:
        assert guard.is_source(Path("pyproject.toml"))

    def test_declared_scratch_does_not(self) -> None:
        """`scratch_*.py` is ignored on purpose. Flagging it would make the
        guard noise on its first run, and a guard that cries wolf gets switched
        off -- which is this failure one level up."""
        assert not guard.is_source(Path("scratch_cleanup.py"))
        assert not guard.is_source(Path("requirements.lock.txt"))

    def test_ordinary_ignored_root_files_do_not(self) -> None:
        assert not guard.is_source(Path(".coverage"))
        assert not guard.is_source(Path("drunken_discord_raw.log"))

    def test_the_session_checkpoint_scratchpad_does_not(self) -> None:
        """SESSION_CHECKPOINT.md is a session scratchpad, not project record --
        the Boss confirmed it belongs to whoever's session wrote it, not to git
        (DG-293). Flagging it here would make the guard noise on every session,
        same failure as an unrecognized scratch file."""
        assert not guard.is_source(Path("SESSION_CHECKPOINT.md"))


class TestTheGuardItself:
    def test_it_reports_an_ignored_source_file(self) -> None:
        offenders = guard.offenders(
            [
                "scripts/__pycache__/x.cpython-314.pyc",
                "tests/test_token_economy.py",
                "src/core/__pycache__/y.pyc",
            ]
        )

        assert offenders == [Path("tests/test_token_economy.py")]

    def test_a_clean_tree_reports_nothing(self) -> None:
        assert guard.offenders(["src/core/__pycache__/y.pyc", "htmlcov/i.html"]) == []

    def test_the_message_names_the_file_and_why_it_matters(self) -> None:
        """ "Blocked" without a reason gets bypassed with --no-verify. The
        message has to say that the file will be missing from the commit while
        everything else reports success."""
        message = guard.explain([Path("tests/test_token_economy.py")])

        assert "tests/test_token_economy.py" in message
        assert "gitignore" in message.lower()


class TestItIsWiredIntoPreCommit:
    def test_the_hook_is_declared(self) -> None:
        """A guard nobody runs is a comment. DG-258's whole lesson is that the
        pipeline reported success throughout."""
        config = Path(__file__).resolve().parent.parent / ".pre-commit-config.yaml"

        assert "check_ignored_sources" in config.read_text(encoding="utf-8")
