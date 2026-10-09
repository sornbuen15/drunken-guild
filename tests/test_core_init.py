# mypy: ignore-errors
"""Setup must be scriptable, idempotent, and incapable of storing a token."""

import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from core import exclude, init, paths


@pytest.fixture(autouse=True)  # type: ignore[misc]
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "state"))
    monkeypatch.delenv(paths.ENV_REGISTRY, raising=False)
    return tmp_path


def run(*argv: str, monkeypatch=None) -> int:
    import sys

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", ["drunken-init", *argv])
        return init.main()


def registry_contents(tmp_path) -> dict:
    return json.loads(
        (tmp_path / "state" / "projects.json").read_text(encoding="utf-8")
    )


class TestBootstrap:
    def test_creates_the_state_directory_owner_only(self, tmp_path) -> None:
        assert run() == 0

        state = tmp_path / "state"
        assert state.is_dir()
        assert stat.S_IMODE(state.stat().st_mode) == paths.HOME_MODE

    def test_writes_an_empty_v2_registry(self, tmp_path) -> None:
        run()
        assert registry_contents(tmp_path) == {"version": 2, "projects": {}}

    def test_registers_a_project(self, tmp_path) -> None:
        project = tmp_path / "proj"
        project.mkdir()

        assert run("--project", "sample", "--path", str(project)) == 0
        assert registry_contents(tmp_path)["projects"]["sample"]["path"] == str(project)

    def test_path_is_optional_for_a_containerised_project(self, tmp_path) -> None:
        assert run("--project", "api-only") == 0
        assert registry_contents(tmp_path)["projects"]["api-only"] == {}

    def test_a_missing_path_is_rejected_with_the_reason(self, tmp_path, capsys) -> None:
        assert run("--project", "sample", "--path", str(tmp_path / "absent")) == 1
        assert "does not exist" in capsys.readouterr().out

    def test_an_invalid_project_id_is_rejected(self, tmp_path, capsys) -> None:
        assert run("--project", "../escape") == 1
        assert "Invalid project id" in capsys.readouterr().out


class TestNoSecretCanBeStored:
    """There is deliberately no flag that accepts a token."""

    def test_a_bare_token_is_refused(self, tmp_path, capsys) -> None:
        code = run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
        )

        assert code == 1
        assert "no scheme" in capsys.readouterr().out

    def test_the_refusal_does_not_echo_the_token(self, tmp_path, capsys) -> None:
        run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
        )
        assert "ATATT3xFfGF0-EXAMPLE" not in capsys.readouterr().out

    def test_nothing_is_written_when_the_credential_is_refused(self, tmp_path) -> None:
        run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN",
        )
        assert not (tmp_path / "state" / "projects.json").exists()

    def test_a_reference_is_accepted_and_stored_verbatim(self, tmp_path) -> None:
        assert (
            run(
                "--project",
                "sample",
                "--jira-url",
                "https://example.atlassian.net",
                "--jira-email",
                "someone@example.com",
                "--jira-project-key",
                "SMP",
                "--jira-credential",
                "env://SAMPLE_TOKEN",
            )
            == 0
        )

        jira = registry_contents(tmp_path)["projects"]["sample"]["jira"]
        assert jira["credential"] == "env://SAMPLE_TOKEN"

    def test_partial_jira_options_are_rejected_rather_than_half_written(
        self, tmp_path, capsys
    ) -> None:
        code = run("--project", "sample", "--jira-url", "https://example.atlassian.net")

        assert code == 1
        assert "Incomplete Jira options" in capsys.readouterr().out


class TestIdempotence:
    def test_rerunning_is_safe(self, tmp_path) -> None:
        project = tmp_path / "proj"
        project.mkdir()

        run("--project", "sample", "--path", str(project))
        run("--project", "sample", "--path", str(project))

        assert list(registry_contents(tmp_path)["projects"]) == ["sample"]

    def test_updating_one_field_leaves_the_others_alone(self, tmp_path) -> None:
        """A provisioning script that sets the path must not wipe Jira."""
        run(
            "--project",
            "sample",
            "--jira-url",
            "https://example.atlassian.net",
            "--jira-email",
            "someone@example.com",
            "--jira-project-key",
            "SMP",
            "--jira-credential",
            "env://SAMPLE_TOKEN",
        )
        project = tmp_path / "proj"
        project.mkdir()
        run("--project", "sample", "--path", str(project))

        entry = registry_contents(tmp_path)["projects"]["sample"]
        assert entry["path"] == str(project)
        assert entry["jira"]["project_key"] == "SMP"

    def test_a_second_project_joins_the_first(self, tmp_path) -> None:
        run("--project", "one")
        run("--project", "two")

        assert sorted(registry_contents(tmp_path)["projects"]) == ["one", "two"]


class TestV1Migration:
    def test_a_v1_registry_is_wrapped_only_when_the_operator_asks(
        self, tmp_path
    ) -> None:
        """Reading a v1 file never rewrites it; running drunken-init is the
        explicit request that does."""
        state = tmp_path / "state"
        state.mkdir(parents=True)
        (state / "projects.json").write_text(
            json.dumps({"legacy": {"path": "/abs/legacy"}}), encoding="utf-8"
        )

        assert run("--project", "fresh") == 0

        document = registry_contents(tmp_path)
        assert document["version"] == 2
        assert document["projects"]["legacy"]["path"] == "/abs/legacy"
        assert "fresh" in document["projects"]

    def test_a_malformed_registry_is_reported_not_overwritten(
        self, tmp_path, capsys
    ) -> None:
        state = tmp_path / "state"
        state.mkdir(parents=True)
        (state / "projects.json").write_text("[]", encoding="utf-8")

        assert run("--project", "fresh") == 1
        assert "not a JSON object" in capsys.readouterr().out


class TestOutput:
    def test_points_at_the_next_step(self, tmp_path, capsys) -> None:
        run("--project", "sample")
        assert "drunken-doctor" in capsys.readouterr().out

    def test_there_is_no_flag_that_takes_a_token(self) -> None:
        """The guarantee is structural: if no flag accepts a value, a value
        cannot be stored — or land in shell history."""
        options = {
            action.dest
            for action in init.build_parser()._actions  # noqa: SLF001
        }
        assert "jira_token" not in options
        assert "discord_token" not in options
        assert "jira_credential" in options


def _stub_this_repository(monkeypatch, checkout) -> None:
    """DG-442 review: the "is this repository" signal is read from a
    *target*'s own ``pyproject.toml`` (``[project] name = "drunken-guild"``),
    never from ``__file__`` — the installed CLI's ``__file__`` sits inside a
    virtualenv with no such thing to read, so a `__file__`-based signal would
    make *every* real run (the only kind that matters) treat *every* project
    as "not this repository" by accident. The dedicated signal tests below
    (`TestThisRepositorySignal`) exercise the real reader directly, against a
    real `pyproject.toml` on disk, with nothing stubbed. This helper exists
    only for the handful of unrelated tests (guild-block idempotency,
    byte-identical reruns) that need the *self* branch taken without writing
    a whole `pyproject.toml` fixture each time."""
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "drunken-guild"\n', encoding="utf-8"
    )


class TestThisRepositorySignal:
    """DG-442 review (CHANGES NEEDED on the Phase 1 plan): the signal must be
    read from the *target* git root's own ``pyproject.toml``, never from
    ``__file__`` — ``core.doctor.source_tree_root()`` returns ``None`` once
    installed (``uv tool install`` resolves inside a virtualenv with no
    ``skills/`` to find), which would make every real, installed run treat
    this repository itself as "a project under the guild". ``pyproject.toml``
    is preferred over a new marker file because it is already tracked,
    already the canonical "what package is this" file, and already read the
    same way (`[project]` section, line-scanned, no TOML dependency) by
    ``core.doctor.declared_version()`` for the sibling question "what version
    does this source tree declare" — reusing the shape rather than inventing
    a second one.

    None of these three stub the running binary: each points `--path` at a
    real, disposable checkout on disk and lets the real reader run.
    """

    def test_a_checkout_whose_pyproject_declares_the_guild_keeps_tracked_instruction_files(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_text(
            '[project]\nname = "drunken-guild"\n', encoding="utf-8"
        )

        assert run("--project", "app", "--path", str(checkout)) == 0

        agents = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "`app`" in agents
        assert (checkout / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"

    def test_a_checkout_without_the_signal_is_treated_as_a_project_under_the_guild(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert not (checkout / "AGENTS.md").exists()
        assert not (checkout / "CLAUDE.md").exists()
        assert "--config-repo" in capsys.readouterr().out

    def test_a_pyproject_with_a_different_name_is_not_treated_as_this_repo(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_text(
            '[project]\nname = "some-other-package"\n', encoding="utf-8"
        )

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert not (checkout / "AGENTS.md").exists()
        assert "--config-repo" in capsys.readouterr().out

    def test_a_leading_utf8_bom_does_not_defeat_the_signal(self, tmp_path) -> None:
        """Round 2 review item 4: a leading BOM used to be read as a
        literal character by the "utf-8" codec, which meant the very first
        line (`﻿[project]`) never equalled `"[project]"` and the
        signal silently read as "not this repository"."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_bytes(
            b"\xef\xbb\xbf" + '[project]\nname = "drunken-guild"\n'.encode("utf-8")
        )

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert (checkout / "AGENTS.md").exists()

    def test_a_trailing_comment_on_the_name_line_does_not_defeat_the_signal(
        self, tmp_path
    ) -> None:
        """Round 2 review item 4: a bare `strip('"')` only trims the two
        ends, so `name = "drunken-guild"  # the one and only` left the
        trailing comment fused onto the value and it never equalled
        "drunken-guild"."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_text(
            '[project]\nname = "drunken-guild"  # the one and only\n',
            encoding="utf-8",
        )

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert (checkout / "AGENTS.md").exists()

    def test_a_bom_with_a_different_name_is_still_not_treated_as_this_repo(
        self, tmp_path, capsys
    ) -> None:
        """Tolerating the BOM must not loosen the exact-name match — every
        existing false-positive guard stays in force."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_bytes(
            b"\xef\xbb\xbf"
            + '[project]\nname = "some-other-package"  # not us\n'.encode("utf-8")
        )

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert not (checkout / "AGENTS.md").exists()
        assert "--config-repo" in capsys.readouterr().out

    def test_a_real_checkout_of_this_repository_reports_kept_not_skipped(
        self, capsys
    ) -> None:
        """Integration-level proof against the real thing, not a fixture.
        Never passes --guild-block or --config-repo: both are no-ops here
        (AGENTS.md/CLAUDE.md already exist and are only ever "kept"), so this
        cannot mutate the real repository's own tracked files."""
        repo_root = Path(__file__).resolve().parent.parent

        assert (
            run("--project", "this-repo-readonly-probe-2", "--path", str(repo_root))
            == 0
        )

        out = capsys.readouterr().out
        assert "AGENTS.md" in out and "kept" in out
        assert "--config-repo" not in out


class TestNonUtf8Pyproject:
    """DG-456: ``_target_is_this_repository`` used to catch only
    ``OSError`` around ``pyproject.toml``'s ``read_text()``, so a
    ``pyproject.toml`` that is not UTF-8 (at all, or under the
    ``utf-8-sig`` codec this reader opens with) raised an uncaught
    ``UnicodeDecodeError`` straight out of ``drunken-init`` — a raw
    traceback instead of a normal run. The safe direction (CLAUDE.md: never
    writes tracked files on an ambiguous signal) is to treat an undecodable
    ``pyproject.toml`` exactly like a missing or OSError-raising one: "not
    this repository", nothing alarming reported.
    """

    def test_a_utf16_pyproject_does_not_raise_and_is_not_treated_as_this_repo(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_bytes(
            '[project]\nname = "drunken-guild"\n'.encode("utf-16")
        )

        assert init._target_is_this_repository(checkout) is False  # noqa: SLF001

    def test_latin1_bytes_do_not_raise_and_are_not_treated_as_this_repo(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        # 0xe9 alone is a continuation byte with no valid UTF-8 lead byte
        # before it — guaranteed to fail UTF-8 decoding, not merely to
        # decode into something unexpected.
        (checkout / "pyproject.toml").write_bytes(b'[project]\nname = "caf\xe9"\n')

        assert init._target_is_this_repository(checkout) is False  # noqa: SLF001

    def test_main_still_completes_normally_with_a_non_utf8_pyproject(
        self, tmp_path, capsys
    ) -> None:
        """The acceptance line's own shape: a full ``main()`` run (not just
        the helper), no traceback, exit 0, treated like any other project
        under the guild."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_bytes(
            '[project]\nname = "drunken-guild"\n'.encode("utf-16")
        )

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert not (checkout / "AGENTS.md").exists()
        assert not (checkout / "CLAUDE.md").exists()
        assert "--config-repo" in capsys.readouterr().out

    def test_an_empty_pyproject_is_not_an_error(self, tmp_path) -> None:
        """Regression guard: an empty file decodes fine under
        ``utf-8-sig`` and simply never matches ``[project]`` — this must
        keep working exactly as today."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_bytes(b"")

        assert init._target_is_this_repository(checkout) is False  # noqa: SLF001

    def test_invalid_toml_in_valid_utf8_is_not_an_error(self, tmp_path) -> None:
        """Regression guard: ``_target_is_this_repository`` is a
        line-scanner, not a TOML parser (see its own docstring) — garbage
        that is not valid TOML at all, but is valid UTF-8, must keep
        reading as "not this repository" rather than raising, exactly as
        it did before this ticket."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").write_text(
            "[[[ not valid toml at all ===\nname = \n", encoding="utf-8"
        )

        assert init._target_is_this_repository(checkout) is False  # noqa: SLF001

    def test_pyproject_as_a_directory_is_not_an_error(self, tmp_path) -> None:
        """Regression guard: ``IsADirectoryError`` is already an
        ``OSError`` subclass and was already caught before this ticket."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "pyproject.toml").mkdir()

        assert init._target_is_this_repository(checkout) is False  # noqa: SLF001


class TestItGivesTheProjectAnInstructionFile:
    """DG-392 (REQ-007, REQ-015), updated by DG-442: a project under the
    guild no longer gets a tracked AGENTS.md/CLAUDE.md written into its own
    checkout at all — the adapter is generated into the config repo's
    working copy and reaches the checkout only through the already-merged
    --config-repo copy-in (DG-441), untracked. This repository's own
    checkout (see TestThisRepositorySignal) is the one exception, where
    today's direct-write behaviour is unchanged."""

    def test_a_project_under_the_guild_generates_into_the_config_repo_then_copies_it_in_untracked(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
            )
            == 0
        )

        generated = (project_folder / "AGENTS.md").read_text(encoding="utf-8")
        assert "## Documents" in generated
        assert "`app`" in generated
        assert (project_folder / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"

        copied = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert copied == generated
        assert (checkout / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"

        tracked = _run_git("ls-files", cwd=checkout).stdout.splitlines()
        assert "AGENTS.md" not in tracked
        assert "CLAUDE.md" not in tracked

    def test_a_project_under_the_guild_gets_no_tracked_instruction_file_without_config_repo(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert not (checkout / "AGENTS.md").exists()
        assert not (checkout / "CLAUDE.md").exists()
        out = capsys.readouterr().out
        assert "AGENTS.md" in out and "--config-repo" in out

    def test_a_hand_edited_config_repo_copy_is_kept_not_overwritten_on_rerun(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)

        args = (
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )
        assert run(*args) == 0

        hand_edited = (project_folder / "AGENTS.md").read_text(
            encoding="utf-8"
        ) + "\nHAND-EDITED AFTER GENERATION\n"
        (project_folder / "AGENTS.md").write_text(hand_edited, encoding="utf-8")

        # The second run's own copy-in now sees the checkout's copy (from
        # the first run) differ from the just-hand-edited config-repo copy
        # and refuses to overwrite it without --overwrite-ai-layer — that is
        # DG-441's own, pre-existing, correct drift guard, nothing to do
        # with generation. What this test is actually about is that
        # *generation itself* never touched the hand-edited file at all.
        run(*args)

        assert (project_folder / "AGENTS.md").read_text(encoding="utf-8") == hand_edited

    def test_generation_requires_an_existing_config_repo_project_folder(
        self, tmp_path
    ) -> None:
        """DG-442 review: generation never creates a config-repo project
        folder on its own — a missing folder stays exactly DG-441's own
        refusal (`ConfigRepoProjectNotFoundError`), not something generation
        silently papers over by onboarding it unasked."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        config_repo.mkdir()

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not (config_repo / "app").exists()
        assert not (checkout / "AGENTS.md").exists()

    def test_generation_targets_exactly_config_repo_slash_project_id_not_a_similarly_named_folder(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        (config_repo / "app").mkdir(parents=True)
        decoy = config_repo / "app-decoy"
        decoy.mkdir()

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
            )
            == 0
        )

        assert (config_repo / "app" / "AGENTS.md").exists()
        assert not (decoy / "AGENTS.md").exists()
        assert list(decoy.iterdir()) == []

    def test_without_a_path_no_file_is_written_anywhere(self, tmp_path) -> None:
        run("--project", "remote-only")

        assert not list(tmp_path.rglob("AGENTS.md"))

    def test_a_fresh_agents_md_opens_with_the_guild_block(self, tmp_path) -> None:
        """DG-407. The template ships the same pointer table as the root
        AGENTS.md, so a freshly initialised project is routed the same way —
        now proven against the config-repo copy, since DG-442 is what the
        generated file actually lands in for a project under the guild."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
            )
            == 0
        )

        agents = (project_folder / "AGENTS.md").read_text(encoding="utf-8")
        assert "<!-- guild-block:start -->" in agents
        assert "<!-- guild-block:end -->" in agents
        assert "/build" in agents
        assert "jira-tickets" in agents


class TestThisRepositorysInstructionFilesAreUnchanged:
    """The one exception DG-442 carves out: this repository's own checkout
    keeps today's direct-write behaviour exactly, proven here with the
    `pyproject.toml` signal stubbed in (see `_stub_this_repository`) rather
    than the real repository's own tracked files, so these tests can freely
    write and overwrite without any risk to the actual checkout."""

    def test_an_existing_agents_md_is_left_byte_identical(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        mine = b"# ours\r\nhand-written, keep me\n"
        (checkout / "AGENTS.md").write_bytes(mine)

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert (checkout / "AGENTS.md").read_bytes() == mine

    def test_it_says_it_kept_the_existing_file(self, tmp_path, capsys) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        (checkout / "AGENTS.md").write_text("# ours\n", encoding="utf-8")

        run("--project", "app", "--path", str(checkout))

        out = capsys.readouterr().out
        assert "AGENTS.md" in out and "kept" in out

    def test_an_existing_claude_md_is_kept_and_a_missing_import_is_named(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        (checkout / "CLAUDE.md").write_text("# old rules\n", encoding="utf-8")

        run("--project", "app", "--path", str(checkout))

        assert (checkout / "CLAUDE.md").read_text(encoding="utf-8") == "# old rules\n"
        assert "@AGENTS.md" in capsys.readouterr().out

    def test_rerunning_changes_nothing(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        run("--project", "app", "--path", str(checkout))
        first = (checkout / "AGENTS.md").read_bytes()

        run("--project", "app", "--path", str(checkout), "--description", "x")

        assert (checkout / "AGENTS.md").read_bytes() == first

    def test_guild_block_still_merges_into_the_tracked_file_directly(
        self, tmp_path
    ) -> None:
        """DG-442 review: the one case where --guild-block keeps today's
        shape — merging straight into the checkout's own AGENTS.md, no
        --config-repo involved at all."""
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        (checkout / "AGENTS.md").write_text(
            "# ours\nhand-written, keep me\n", encoding="utf-8"
        )

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 0

        merged = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "<!-- guild-block:start -->" in merged
        assert "hand-written, keep me" in merged


class TestGuildBlockFlagForAProjectUnderTheGuild:
    """DG-408, updated by DG-442: for a project under the guild,
    --guild-block now merges into the *config repo's copy*
    (config_repo/<project>/AGENTS.md), never the checkout directly, and
    requires --config-repo together with it."""

    def test_without_config_repo_is_rejected_checkout_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 1

        out = capsys.readouterr().out
        assert "requires --config-repo" in out, (
            "no --config-repo at all is a different problem from --config-repo "
            "given but the folder missing — this message must name the flag "
            "as simply absent, not point at any particular path"
        )
        assert not (checkout / "AGENTS.md").exists()

    def test_with_config_repo_but_missing_project_folder_names_the_path(
        self, tmp_path, capsys
    ) -> None:
        """Round 2 review item 3: --config-repo was in fact given — the
        real problem is that the config repo has no folder for this project
        yet. The message must say *that*, not repeat the "requires
        --config-repo" wording from the sibling test above, which would
        send an operator re-checking a flag that was never the issue."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        config_repo.mkdir()

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
            "--guild-block",
        )

        assert code == 1
        out = capsys.readouterr().out
        assert "requires --config-repo" not in out
        assert "app" in out
        assert str(config_repo / "app") in out
        assert not (checkout / "AGENTS.md").exists()
        assert not (config_repo / "app").exists()

    def test_an_existing_config_repo_copy_without_a_block_gets_one_and_keeps_every_byte(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        original = "# ours\r\nhand-written, keep me\n"
        (project_folder / "AGENTS.md").write_bytes(original.encode("utf-8"))

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 0
        )

        merged = (project_folder / "AGENTS.md").read_text(encoding="utf-8")
        assert "<!-- guild-block:start -->" in merged
        assert "hand-written, keep me" in merged
        # ...and the merged copy (not the stale checkout file) is what got
        # copied in, untracked.
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == merged
        tracked = _run_git("ls-files", cwd=checkout).stdout.splitlines()
        assert "AGENTS.md" not in tracked

    def test_rerunning_with_the_flag_is_byte_identical(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "# ours\nhand-written, keep me\n", encoding="utf-8"
        )
        args = (
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
            "--guild-block",
        )

        run(*args)
        first = (project_folder / "AGENTS.md").read_bytes()

        run(*args)

        assert (project_folder / "AGENTS.md").read_bytes() == first

    def test_an_older_block_has_only_the_block_replaced(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        before = "# ours\n\nbefore the block\n"
        old_block = (
            "<!-- guild-block:start -->\nSTALE CONTENT\n<!-- guild-block:end -->\n"
        )
        after = "\nafter the block\n"
        (project_folder / "AGENTS.md").write_text(
            before + old_block + after, encoding="utf-8"
        )

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 0
        )

        merged = (project_folder / "AGENTS.md").read_text(encoding="utf-8")
        assert "STALE CONTENT" not in merged
        assert "/build" in merged, "the current block replaced the stale one"
        assert merged.startswith(before)
        assert merged.endswith(after)

    def test_first_time_with_guild_block_is_reported_as_created_not_unchanged(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 0
        )

        out = capsys.readouterr().out
        assert "created with the block" in out
        assert "unchanged" not in out


class TestGuildBlockSafety:
    """DG-408 review follow-up (BLOCK verdict on PR 116), retargeted by
    DG-442 at the config-repo copy for a project under the guild.
    merge_guild_block must refuse rather than guess or splice on anything it
    cannot safely reason about — proving that safety carries over to the
    new call site, not just the project-root one it was written for."""

    def test_a_symlinked_config_repo_agents_md_is_refused_and_the_target_is_untouched(
        self, tmp_path, capsys
    ) -> None:
        outside = tmp_path / "outside.md"
        outside.write_text(
            "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n", encoding="utf-8"
        )
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        link = project_folder / "AGENTS.md"
        os.symlink(outside, link)

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 1
        )

        out = capsys.readouterr().out
        assert "symlink" in out.lower()
        assert (
            outside.read_text(encoding="utf-8")
            == "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n"
        )

    def test_a_start_marker_with_no_matching_end_is_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        broken = "# ours\n<!-- guild-block:start -->\nno end marker here\n"
        (project_folder / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 1
        )

        out = capsys.readouterr().out
        assert "guild-block:start" in out
        assert "line 2" in out
        assert (project_folder / "AGENTS.md").read_text(encoding="utf-8") == broken

    def test_an_end_marker_before_its_start_is_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        """DG-408, restored by round 2 review item 2 (had been dropped
        without a reason when this class was retargeted at the config-repo
        copy): an END marker appearing before any open START is just as
        malformed as an unclosed START, even with matching counts."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        broken = "# ours\n<!-- guild-block:end -->\nstuff\n<!-- guild-block:start -->\n"
        (project_folder / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 1
        )

        out = capsys.readouterr().out
        assert "guild-block" in out
        assert (project_folder / "AGENTS.md").read_text(encoding="utf-8") == broken

    def test_two_start_markers_are_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        """DG-408, restored by round 2 review item 2: two *complete* pairs
        are still malformed — a second START while one is already open —
        even though start/end counts match."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        broken = (
            "# ours\n"
            "<!-- guild-block:start -->\nA\n<!-- guild-block:end -->\n"
            "<!-- guild-block:start -->\nB\n<!-- guild-block:end -->\n"
        )
        (project_folder / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 1
        )

        out = capsys.readouterr().out
        assert "guild-block:start" in out
        assert (project_folder / "AGENTS.md").read_text(encoding="utf-8") == broken

    def test_a_bom_file_keeps_the_bom_at_byte_0_and_inserts_after_the_heading(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        content = "﻿# ours\nhand-written, keep me\n"
        (project_folder / "AGENTS.md").write_bytes(content.encode("utf-8"))

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--guild-block",
            )
            == 0
        )

        raw = (project_folder / "AGENTS.md").read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "the BOM must stay at byte 0"
        merged = raw.decode("utf-8")
        assert "<!-- guild-block:start -->" in merged
        assert "hand-written, keep me" in merged
        assert merged.index("# ours") < merged.index("<!-- guild-block:start -->")


class TestGuildBlockSafetyForThisRepository:
    """DG-408, restored by round 2 review item 2: the same malformed-marker
    safety, for the *other* target DG-442 kept — this repository's own
    checkout, merged into directly, never through the config repo. These
    use the `_stub_this_repository` fixture (a disposable pyproject.toml),
    never the real repository's own tracked files."""

    def test_an_end_marker_before_its_start_is_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        broken = "# ours\n<!-- guild-block:end -->\nstuff\n<!-- guild-block:start -->\n"
        (checkout / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 1

        out = capsys.readouterr().out
        assert "guild-block" in out
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == broken

    def test_two_start_markers_are_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        _stub_this_repository(None, checkout)
        broken = (
            "# ours\n"
            "<!-- guild-block:start -->\nA\n<!-- guild-block:end -->\n"
            "<!-- guild-block:start -->\nB\n<!-- guild-block:end -->\n"
        )
        (checkout / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 1

        out = capsys.readouterr().out
        assert "guild-block:start" in out
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == broken


def _run_git(*cmd_args, cwd):
    import subprocess

    result = subprocess.run(
        ["git", *cmd_args], cwd=cwd, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (
        f"git {' '.join(cmd_args)} failed in {cwd}: {result.stderr}"
    )
    return result


def _init_git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _run_git("init", "-q", cwd=path)
    _run_git("config", "user.email", "test@example.com", cwd=path)
    _run_git("config", "user.name", "Test", cwd=path)
    (path / "README.md").write_text("scratch\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=path)
    _run_git("commit", "-q", "-m", "initial", cwd=path)
    return path


class TestConfigRepoCopyIn:
    """DG-441 (REQ-019/020). ``--config-repo`` wires
    ``core.layer_copy.copy_ai_layer_in`` into drunken-init."""

    def test_copies_the_project_folder_and_leaves_git_status_clean(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        # .claude/settings.json rather than AGENTS.md/CLAUDE.md: those two
        # are also generated into project_folder by this same call now
        # (DG-442), so a third, unrelated file proves the copy-in wiring on
        # its own without entangling it with the generation assertions that
        # TestItGivesTheProjectAnInstructionFile already covers.
        claude_dir = project_folder / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text(
            '{"from": "config repo"}\n', encoding="utf-8"
        )

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
            )
            == 0
        )

        settings = (checkout / ".claude" / "settings.json").read_text(encoding="utf-8")
        assert settings == '{"from": "config repo"}\n'
        status = _run_git("status", "--porcelain", cwd=checkout)
        assert status.stdout.strip() == ""

    def test_missing_project_folder_in_the_config_repo_is_refused(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        # Pre-existing, hand-written, and never touched by this call at all
        # (DG-442: generation only ever writes into the config repo, never
        # the checkout directly) — isolating the config-repo failure's own
        # "nothing written" guarantee from that unrelated file.
        (checkout / "AGENTS.md").write_text("PRE-EXISTING\n", encoding="utf-8")
        config_repo = tmp_path / "config-repo"
        config_repo.mkdir()

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert "app" in capsys.readouterr().out
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == (
            "PRE-EXISTING\n"
        )

    def test_config_repo_without_a_project_is_refused(self, tmp_path, capsys) -> None:
        config_repo = tmp_path / "config-repo"
        config_repo.mkdir()

        code = run("--config-repo", str(config_repo))

        assert code == 1
        assert "requires --project" in capsys.readouterr().out

    def test_works_on_a_second_run_against_an_already_registered_path(
        self, tmp_path
    ) -> None:
        """Idempotent, like every other flag: --path need not be repeated."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        assert run("--project", "app", "--path", str(checkout)) == 0
        # The first run passed no --config-repo, so (DG-442) nothing was
        # written anywhere; --overwrite-ai-layer below is still needed only
        # because a later run could otherwise find an identical, already
        # up to date file and report "unchanged" rather than exercising the
        # copy itself — not because of any write the first run made.
        assert (
            run(
                "--project",
                "app",
                "--config-repo",
                str(config_repo),
                "--overwrite-ai-layer",
            )
            == 0
        )

        agents = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert agents == "from the config repo\n"

    def test_path_and_config_repo_together_never_collide_on_agents_md_any_more(
        self, tmp_path
    ) -> None:
        """MEDIUM-HIGH review finding (DG-441 PR 116) that this used to
        reproduce no longer applies after DG-442: `--path` alone no longer
        makes anything write a default AGENTS.md into the checkout, so there
        is only ever one place (the config repo's own copy) for a hand-placed
        file and this call's own generation to disagree about — and
        generation never overwrites an existing file either. A hand-placed
        config-repo AGENTS.md and `--path` together must now succeed and
        copy that exact file in, not refuse."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 0
        assert (project_folder / "AGENTS.md").read_text(encoding="utf-8") == (
            "from the config repo\n"
        )
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == (
            "from the config repo\n"
        )

    def test_an_identical_existing_file_is_unchanged_and_exits_zero(
        self, tmp_path
    ) -> None:
        """The other half of the same guarantee: once the file on disk
        actually matches the config repo, re-running must stay green — an
        idempotent re-run is not "drift"."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text(
            "from the config repo\n", encoding="utf-8"
        )

        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--config-repo",
                str(config_repo),
                "--overwrite-ai-layer",
            )
            == 0
        )

        # Re-run without --overwrite-ai-layer: the file now on disk already
        # matches the config repo exactly, so this is "unchanged", not
        # drift.
        assert run("--project", "app", "--config-repo", str(config_repo)) == 0

    def test_a_project_registered_at_a_subfolder_copies_there_and_excludes_at_the_real_git_root(
        self, tmp_path
    ) -> None:
        """Review finding #5: the registry's `git_root` offset (see
        core.context.ProjectContext.git_root_path) is a plain relative
        join, never resolved or direction-restricted — ".." ascends to a
        real top level that is an *ancestor* of the registered --path,
        which is exactly DG-441 comment (a)'s shape (a project registered
        at a subfolder of a larger repository, a monorepo package)."""
        repo = _init_git_repo(tmp_path / "monorepo")
        project_path = repo / "packages" / "sample"
        project_path.mkdir(parents=True)

        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "sample"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("instructions\n", encoding="utf-8")

        assert (
            run(
                "--project",
                "sample",
                "--path",
                str(project_path),
                "--git-root",
                "../..",
                "--config-repo",
                str(config_repo),
                "--overwrite-ai-layer",
            )
            == 0
        )

        # The agent reads AGENTS.md from the registered project path — the
        # subfolder itself — never from the repository's outer root.
        assert (project_path / "AGENTS.md").read_text(
            encoding="utf-8"
        ) == "instructions\n"
        # ...but info/exclude is the real repository's own, reached by
        # ascending via the ".." offset, not something invented under the
        # subfolder or left unwritten.
        exclude_text = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        assert exclude.MARKER_START in exclude_text

        status = _run_git("status", "--porcelain", cwd=repo)
        assert status.stdout.strip() == "", (
            f"git status is not clean after the copy: {status.stdout!r}"
        )


class TestTrackedInstructionFileRefusal:
    """DG-442: a project under the guild whose own git already tracks
    AGENTS.md/CLAUDE.md is refused outright, before any write — the
    migration itself is an open PRD question, not handled by drunken-init.
    The check reuses `core.layer_copy`'s own hardened, GIT_*-stripped
    tracked-check (imported, not re-implemented) rather than
    `core.doctor.tracked_ai_layer_paths`, which is unstripped and already
    named in DG-440's own docstring as the wrong shape for exactly this."""

    def test_refused_even_without_config_repo(self, tmp_path, capsys) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir(parents=True)
        _run_git("init", "-q", cwd=checkout)
        _run_git("config", "user.email", "test@example.com", cwd=checkout)
        _run_git("config", "user.name", "Test", cwd=checkout)
        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)

        code = run("--project", "app", "--path", str(checkout))

        out = capsys.readouterr().out
        assert code == 1
        assert "AGENTS.md" in out
        assert "already tracks" in out or "already tracked" in out.lower()

    def test_refused_with_config_repo_before_generating_anything(
        self, tmp_path, capsys
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not (project_folder / "AGENTS.md").exists(), (
            "the config repo must stay untouched: the refusal happens before "
            "any generation, not after a failed copy-in"
        )

    def test_not_fooled_by_a_leaked_git_index_file(
        self, tmp_path, capsys, monkeypatch
    ) -> None:
        """DG-440's own documented incident shape: a leaked GIT_INDEX_FILE
        pointing at an empty, unrelated index must not make the tracked
        file read as 'not tracked'."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)
        empty_index = tmp_path / "empty.index"
        monkeypatch.setenv("GIT_INDEX_FILE", str(empty_index))

        code = run("--project", "app", "--path", str(checkout))

        assert code == 1

    def test_staged_but_uncommitted_is_still_refused(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "AGENTS.md").write_text("staged, not committed\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)

        code = run("--project", "app", "--path", str(checkout))

        assert code == 1

    def test_unborn_head_is_not_refused(self, tmp_path) -> None:
        """A fresh `git init` with no commit at all must read as "nothing
        tracked yet", not crash and not wrongly refuse."""
        checkout = tmp_path / "app"
        checkout.mkdir(parents=True)
        _run_git("init", "-q", cwd=checkout)
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 0
        assert (project_folder / "AGENTS.md").exists()

    def test_tracked_at_a_git_root_offset_is_still_refused(self, tmp_path) -> None:
        """DG-442 review: the check must use the path relative to the real
        git root, not relative to the registered --path, or an offset
        registration silently escapes the refusal."""
        monorepo = _init_git_repo(tmp_path / "monorepo")
        project_path = monorepo / "packages" / "sample"
        project_path.mkdir(parents=True)
        (project_path / "AGENTS.md").write_text(
            "tracked at the offset\n", encoding="utf-8"
        )
        _run_git("add", "packages/sample/AGENTS.md", cwd=monorepo)
        _run_git("commit", "-q", "-m", "tracked at offset", cwd=monorepo)

        code = run(
            "--project",
            "sample",
            "--path",
            str(project_path),
            "--git-root",
            "../..",
        )

        assert code == 1

    def test_tracked_claude_md_at_a_git_root_offset_is_still_refused(
        self, tmp_path
    ) -> None:
        """Round 2 review item 5: the same offset coverage as the AGENTS.md
        case above, for CLAUDE.md — the second of the two files this check
        must catch, not just the first."""
        monorepo = _init_git_repo(tmp_path / "monorepo")
        project_path = monorepo / "packages" / "sample"
        project_path.mkdir(parents=True)
        (project_path / "CLAUDE.md").write_bytes(b"@AGENTS.md\n")
        _run_git("add", "packages/sample/CLAUDE.md", cwd=monorepo)
        _run_git("commit", "-q", "-m", "tracked claude.md at offset", cwd=monorepo)

        code = run(
            "--project",
            "sample",
            "--path",
            str(project_path),
            "--git-root",
            "../..",
        )

        assert code == 1

    def test_the_registry_gains_no_entry_on_a_refused_first_run(self, tmp_path) -> None:
        """Round 2 review item 1: a reviewer reproduced the registry being
        written *before* the refusal ran, so a refused run still gained a
        registry entry. Nothing — registry included — may be written when
        the run is refused."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)
        registry_path = tmp_path / "state" / "projects.json"
        assert not registry_path.exists()

        code = run("--project", "app", "--path", str(checkout))

        assert code == 1
        assert not registry_path.exists(), (
            "a refused run must leave no registry file at all behind — "
            "this is the first run, so 'no entry' means 'no file'"
        )

    def test_the_registry_is_byte_unchanged_on_a_later_refused_run(
        self, tmp_path
    ) -> None:
        """The other half of the same guarantee: an *already*-registered
        project whose checkout later starts tracking AGENTS.md must not
        have its registry entry touched (e.g. a `--description` update
        silently landing) by a run that goes on to refuse."""
        checkout = _init_git_repo(tmp_path / "app")
        assert run("--project", "app", "--path", str(checkout)) == 0
        registry_path = tmp_path / "state" / "projects.json"
        before = registry_path.read_bytes()

        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)

        code = run("--project", "app", "--path", str(checkout), "--description", "new")

        assert code == 1
        assert registry_path.read_bytes() == before


class TestJiraBlockFromConfigRepo:
    """DG-443: the Jira block can come from the config repo's own
    `jira.json`, instead of `--jira-*` flags — credential as a reference
    only, and no identity (`email`) in the config repo at all."""

    def test_jira_block_is_read_from_the_config_repo_fragment(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "jira.json").write_text(
            json.dumps(
                {
                    "url": "https://example.atlassian.net",
                    "project_key": "ALPHA",
                    "credential": "env://JIRA_TOKEN_ALPHA",
                }
            ),
            encoding="utf-8",
        )

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 0
        jira = registry_contents(tmp_path)["projects"]["app"]["jira"]
        assert jira == {
            "url": "https://example.atlassian.net",
            "project_key": "ALPHA",
            "credential": "env://JIRA_TOKEN_ALPHA",
        }

    def test_an_email_key_in_the_jira_fragment_is_refused(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "jira.json").write_text(
            json.dumps(
                {
                    "url": "https://example.atlassian.net",
                    "project_key": "ALPHA",
                    "credential": "env://JIRA_TOKEN_ALPHA",
                    "email": "person@realcorp.test",
                }
            ),
            encoding="utf-8",
        )
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()

    def test_a_literal_token_in_the_jira_fragment_credential_is_refused_before_any_write(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        bare_token = "ATATT" + "x" * 24
        (project_folder / "jira.json").write_text(
            json.dumps(
                {
                    "url": "https://example.atlassian.net",
                    "project_key": "ALPHA",
                    "credential": bare_token,
                }
            ),
            encoding="utf-8",
        )
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()

    def test_a_token_shaped_url_field_in_the_jira_fragment_is_refused(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        stray_secret = "ghp_" + "a" * 36
        (project_folder / "jira.json").write_text(
            json.dumps(
                {
                    "url": f"https://example.atlassian.net/{stray_secret}",
                    "project_key": "ALPHA",
                    "credential": "env://JIRA_TOKEN_ALPHA",
                }
            ),
            encoding="utf-8",
        )
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()

    def test_a_missing_jira_fragment_is_not_an_error(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("clean\n", encoding="utf-8")

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 0
        assert "jira" not in registry_contents(tmp_path)["projects"]["app"]

    def test_a_malformed_jira_fragment_is_reported_not_silently_ignored(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "jira.json").write_text("{not valid json", encoding="utf-8")
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()

    def test_an_earlier_cli_written_jira_block_survives_a_config_repo_run_with_no_fragment(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        assert (
            run(
                "--project",
                "app",
                "--path",
                str(checkout),
                "--jira-url",
                "https://example.atlassian.net",
                "--jira-email",
                "person@realcorp.test",
                "--jira-project-key",
                "ALPHA",
                "--jira-credential",
                "env://JIRA_TOKEN_ALPHA",
            )
            == 0
        )
        before = registry_contents(tmp_path)["projects"]["app"]["jira"]

        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        (project_folder / "AGENTS.md").write_text("clean\n", encoding="utf-8")

        code = run(
            "--project",
            "app",
            "--config-repo",
            str(config_repo),
            "--overwrite-ai-layer",
        )

        assert code == 0
        assert registry_contents(tmp_path)["projects"]["app"]["jira"] == before


class TestContentScanRefusalBeforeAnyWriteEndToEnd:
    """DG-443 review (comment 11482, decision 4): a config-repo content
    refusal on a *new* project must leave the registry absent, not just
    the project checkout untouched — the registry write happens strictly
    after every validation, not before it."""

    def test_a_content_scan_refusal_on_a_new_project_leaves_the_registry_absent(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        secret = "ghp_" + "a" * 36
        (project_folder / "AGENTS.md").write_text(secret, encoding="utf-8")
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()
        assert not (checkout / "AGENTS.md").exists()


def _write_sleepy_git(bin_dir: Path, sleep_seconds: float) -> None:
    """A git stand-in that sleeps for *sleep_seconds* then exits 0, for
    proving a real ``subprocess`` timeout fires rather than a mocked
    return value. Bounded: this never sleeps forever, so a test exercising
    it is bounded by *sleep_seconds* even if the timeout under test fails
    to apply at all.

    Duplicated from ``tests/test_exclude.py``'s identical helper rather
    than imported across test modules — see that copy's docstring for why
    Windows needs a copy of the current interpreter plus a
    ``sitecustomize.py`` rather than a ``.bat``/``.cmd`` file: a bare name
    with no extension only gets ``.exe`` auto-appended by Windows'
    ``CreateProcess``, so a batch file here would be invisible to the
    lookup and silently fall through to the real ``git.exe`` elsewhere on
    ``PATH``.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        git_path = bin_dir / "git.exe"
        shutil.copy2(sys.executable, git_path)
        (bin_dir / "sitecustomize.py").write_text(
            f"import time, os\ntime.sleep({sleep_seconds})\nos._exit(0)\n",
            encoding="utf-8",
        )
    else:
        git_path = bin_dir / "git"
        git_path.write_text(
            f"#!/bin/sh\nsleep {sleep_seconds}\nexit 0\n", encoding="utf-8"
        )
        git_path.chmod(0o755)


def _prepend_sleepy_git_to_path(monkeypatch: pytest.MonkeyPatch, bin_dir: Path) -> None:
    """``monkeypatch.setenv`` specifically, not a one-off ``env=`` dict
    built for a single subprocess call: Windows' ``CreateProcess``
    resolves which executable a bare name like ``"git"`` finds using the
    *calling* process's own environment, not whatever is later passed as
    ``env=`` — ``monkeypatch.setenv`` mutates this process's real
    ``os.environ``, which is what that lookup actually reads."""
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    if sys.platform == "win32":
        monkeypatch.setenv(
            "PYTHONPATH", f"{bin_dir}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"
        )


class TestTrackedInstructionFileRefusalUnderAHungGit:
    """DG-454 review (CRITICAL): a prior version of this change let a git
    timeout raise the *same* exception :func:`core.init._tracked_instruction_files`
    already caught to mean "not a git repository at all, so nothing can be
    tracked" — ``exclude.NotAGitRepositoryError``. A reviewer reproduced
    it: under a hung git, that catch returned ``[]`` ("nothing tracked")
    for a checkout whose AGENTS.md *was*, in fact, already tracked, so
    ``_refuse_if_already_tracked`` never refused at all.

    A timeout must now raise the separate ``exclude.GitTimedOutError``
    instead (see ``tests/test_exclude.py::TestRunGitTimeout``), which this
    module's narrow ``except exclude.NotAGitRepositoryError`` does not
    catch — it propagates, through ``main()``'s own ``except DrunkenError``,
    as a refusal. No edit to ``core/init.py`` itself was needed for this:
    the fix is entirely in which exception a timeout raises."""

    def test_tracked_instruction_files_raises_rather_than_answering_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)

        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_sleepy_git_to_path(monkeypatch, bin_dir)

        with pytest.raises(exclude.GitCommandError):
            init._tracked_instruction_files(checkout, checkout)  # noqa: SLF001

    def test_main_refuses_and_writes_nothing_under_a_hung_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """Acceptance (c): the full ``main()`` flow, not just the helper
        function — refuses, prints an error, and the registry is never
        written at all (the same "no file at all on a first run"
        guarantee as :class:`TestTheRegistryIsNeverWrittenOnARefusedRun`
        above, now under a timeout instead of an ordinary tracked file)."""
        checkout = _init_git_repo(tmp_path / "app")
        (checkout / "AGENTS.md").write_text("real, tracked content\n", encoding="utf-8")
        _run_git("add", "AGENTS.md", cwd=checkout)
        _run_git("commit", "-q", "-m", "tracked", cwd=checkout)

        monkeypatch.setattr(exclude, "DEFAULT_GIT_TIMEOUT_SECONDS", 0.2)
        bin_dir = tmp_path / "fakebin"
        _write_sleepy_git(bin_dir, sleep_seconds=2)
        _prepend_sleepy_git_to_path(monkeypatch, bin_dir)

        code = run("--project", "app", "--path", str(checkout))

        assert code == 1
        registry_path = tmp_path / "state" / "projects.json"
        assert not registry_path.exists(), (
            "a hung git must refuse before the registry is ever written, "
            "exactly like any other refused run — never silently proceed "
            "as though nothing were tracked"
        )


class TestContentScanGapsFoundInReviewAreRefusedThroughRealInit:
    """DG-443 review round 2 (CRITICAL 1-3): the reviewer reproduced each
    end to end through ``python -m core.init`` — ``scan_text`` returned
    ``[]`` for a JSON-quoted secret, a PEM private key, and a fine-grained
    GitHub PAT. Each is exercised here the same way: through the real
    ``drunken-init --config-repo`` flow, registry absent on refusal."""

    def test_a_json_quoted_secret_in_settings_json_is_refused(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        claude_dir = project_folder / ".claude"
        claude_dir.mkdir(parents=True)
        secret_value = "v3rys3cr3tValueThatIsLong"
        (claude_dir / "settings.json").write_text(
            json.dumps({"password": secret_value}), encoding="utf-8"
        )
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()
        assert not (checkout / ".claude" / "settings.json").exists()

    def test_a_pem_private_key_in_agents_md_is_refused(self, tmp_path) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        dashes = "-" * 5
        pem_line = f"{dashes}BEGIN RSA PRIVATE KEY{dashes}"
        (project_folder / "AGENTS.md").write_text(f"{pem_line}\n", encoding="utf-8")
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()
        assert not (checkout / "AGENTS.md").exists()

    def test_a_github_fine_grained_pat_in_conventions_md_is_refused(
        self, tmp_path
    ) -> None:
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        project_folder.mkdir(parents=True)
        pat = "github_pat_" + "A" * 22 + "_" + "B" * 59
        (project_folder / "CONVENTIONS.md").write_text(f"{pat}\n", encoding="utf-8")
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()
        assert not (checkout / "CONVENTIONS.md").exists()

    def test_a_curl_short_option_cluster_in_settings_json_is_refused(
        self, tmp_path
    ) -> None:
        """DG-443 review round 4: `-su` (a short-option cluster ending in
        `u`, not the bare `-u` round 3 already covered) in a hook command
        inside `.claude/settings.json`, exercised through the real
        `drunken-init --config-repo` flow, exactly as the reviewer
        reproduced the gap."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        claude_dir = project_folder / ".claude"
        claude_dir.mkdir(parents=True)
        secret_value = "v3rys3cr3tValueThatIsLong"
        hook_command = (
            "curl" + " " + "-su" + " " + "alice:" + secret_value + " " + "https://x"
        )
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {"hooks": [{"type": "command", "command": hook_command}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()
        assert not (checkout / ".claude" / "settings.json").exists()

    def test_a_powershell_static_constructor_in_settings_json_is_refused(
        self, tmp_path
    ) -> None:
        """DG-443 review round 5: `[PSCredential]::new("user","pass")`
        (the static constructor, missed by round 4's `PSCredential\\s*\\(`
        pattern, which only matched the `New-Object ... PSCredential(`
        form) inside a PowerShell `-Command` hook in
        `.claude/settings.json`, through the real `drunken-init
        --config-repo` flow, exactly as the reviewer reproduced the gap."""
        checkout = _init_git_repo(tmp_path / "app")
        config_repo = tmp_path / "config-repo"
        project_folder = config_repo / "app"
        claude_dir = project_folder / ".claude"
        claude_dir.mkdir(parents=True)
        secret_value = "v3rys3cr3tValueThatIsLong"
        hook_command = (
            "powershell -Command "
            + "["
            + "PSCredential"
            + "]::new("
            + '"alice", "'
            + secret_value
            + '")'
        )
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {"hooks": [{"type": "command", "command": hook_command}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        registry_path = tmp_path / "state" / "projects.json"

        code = run(
            "--project",
            "app",
            "--path",
            str(checkout),
            "--config-repo",
            str(config_repo),
        )

        assert code == 1
        assert not registry_path.exists()
        assert not (checkout / ".claude" / "settings.json").exists()
