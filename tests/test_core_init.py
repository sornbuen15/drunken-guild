# mypy: ignore-errors
"""Setup must be scriptable, idempotent, and incapable of storing a token."""

import json
import os
import stat

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


class TestItGivesTheProjectAnInstructionFile:
    """DG-392 (REQ-007, REQ-015). Skills, the jira-mcp error and the docs all
    point a project's agents at its AGENTS.md, and nothing created one — so the
    map every skill reads never existed. With --path, init writes it, plus the
    one-line CLAUDE.md that makes Claude Code read it, and never overwrites."""

    def test_an_empty_checkout_gets_both_files(self, tmp_path) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()

        assert run("--project", "app", "--path", str(checkout)) == 0

        agents = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "## Documents" in agents, "project-docs reads the map from here"
        assert "`app`" in agents, "the registry id the Jira tools need"
        assert (checkout / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"

    def test_an_existing_agents_md_is_left_byte_identical(self, tmp_path) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        mine = b"# ours\r\nhand-written, keep me\n"
        (checkout / "AGENTS.md").write_bytes(mine)

        assert run("--project", "app", "--path", str(checkout)) == 0

        assert (checkout / "AGENTS.md").read_bytes() == mine

    def test_it_says_it_kept_the_existing_file(self, tmp_path, capsys) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        (checkout / "AGENTS.md").write_text("# ours\n", encoding="utf-8")

        run("--project", "app", "--path", str(checkout))

        out = capsys.readouterr().out
        assert "AGENTS.md" in out and "kept" in out

    def test_an_existing_claude_md_is_kept_and_a_missing_import_is_named(
        self, tmp_path, capsys
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        (checkout / "CLAUDE.md").write_text("# old rules\n", encoding="utf-8")

        run("--project", "app", "--path", str(checkout))

        assert (checkout / "CLAUDE.md").read_text(encoding="utf-8") == "# old rules\n"
        assert "@AGENTS.md" in capsys.readouterr().out

    def test_rerunning_changes_nothing(self, tmp_path) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        run("--project", "app", "--path", str(checkout))
        first = (checkout / "AGENTS.md").read_bytes()

        run("--project", "app", "--path", str(checkout), "--description", "x")

        assert (checkout / "AGENTS.md").read_bytes() == first

    def test_without_a_path_no_file_is_written_anywhere(self, tmp_path) -> None:
        run("--project", "remote-only")

        assert not list(tmp_path.rglob("AGENTS.md"))

    def test_a_fresh_agents_md_opens_with_the_guild_block(self, tmp_path) -> None:
        """DG-407. The template ships the same pointer table as the root
        AGENTS.md, so a freshly initialised project is routed the same way."""
        checkout = tmp_path / "app"
        checkout.mkdir()

        assert run("--project", "app", "--path", str(checkout)) == 0

        agents = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "<!-- guild-block:start -->" in agents
        assert "<!-- guild-block:end -->" in agents
        assert "/build" in agents
        assert "jira-tickets" in agents


class TestGuildBlockFlag:
    """DG-408. `--guild-block` is opt-in and only touches an EXISTING
    AGENTS.md; without it behaviour is exactly as today (see
    test_an_existing_agents_md_is_left_byte_identical above)."""

    def test_an_existing_file_without_a_block_gets_one_and_keeps_every_byte(
        self, tmp_path
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        original = "# ours\r\nhand-written, keep me\n"
        (checkout / "AGENTS.md").write_bytes(original.encode("utf-8"))

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 0

        merged = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "<!-- guild-block:start -->" in merged
        assert "<!-- guild-block:end -->" in merged
        assert "hand-written, keep me" in merged
        for line in original.splitlines():
            assert line in merged

    def test_rerunning_with_the_flag_is_byte_identical(self, tmp_path) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        (checkout / "AGENTS.md").write_text(
            "# ours\nhand-written, keep me\n", encoding="utf-8"
        )

        run("--project", "app", "--path", str(checkout), "--guild-block")
        first = (checkout / "AGENTS.md").read_bytes()

        run("--project", "app", "--path", str(checkout), "--guild-block")

        assert (checkout / "AGENTS.md").read_bytes() == first

    def test_an_older_block_has_only_the_block_replaced(self, tmp_path) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        before = "# ours\n\nbefore the block\n"
        old_block = (
            "<!-- guild-block:start -->\nSTALE CONTENT\n<!-- guild-block:end -->\n"
        )
        after = "\nafter the block\n"
        (checkout / "AGENTS.md").write_text(
            before + old_block + after, encoding="utf-8"
        )

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 0

        merged = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert "STALE CONTENT" not in merged
        assert "/build" in merged, "the current block replaced the stale one"
        assert merged.startswith(before)
        assert merged.endswith(after)


class TestGuildBlockSafety:
    """DG-408 review follow-up (BLOCK verdict on PR 116). merge_guild_block
    must refuse rather than guess or splice on anything it cannot safely
    reason about, and report a fresh file distinctly from an unchanged one."""

    def test_a_symlinked_agents_md_is_refused_and_the_target_is_untouched(
        self, tmp_path, capsys
    ) -> None:
        outside = tmp_path / "outside.md"
        outside.write_text(
            "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n", encoding="utf-8"
        )
        checkout = tmp_path / "app"
        checkout.mkdir()
        link = checkout / "AGENTS.md"
        os.symlink(outside, link)

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 1

        out = capsys.readouterr().out
        assert "symlink" in out.lower()
        assert (
            outside.read_text(encoding="utf-8")
            == "OUTSIDE CONTENT, NOT PART OF THE PROJECT\n"
        )

    def test_a_start_marker_with_no_matching_end_is_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        broken = "# ours\n<!-- guild-block:start -->\nno end marker here\n"
        (checkout / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 1

        out = capsys.readouterr().out
        assert "guild-block:start" in out
        assert "line 2" in out
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == broken

    def test_an_end_marker_before_its_start_is_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        broken = "# ours\n<!-- guild-block:end -->\nstuff\n<!-- guild-block:start -->\n"
        (checkout / "AGENTS.md").write_text(broken, encoding="utf-8")

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 1

        out = capsys.readouterr().out
        assert "guild-block" in out
        assert (checkout / "AGENTS.md").read_text(encoding="utf-8") == broken

    def test_two_start_markers_are_refused_file_untouched(
        self, tmp_path, capsys
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
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

    def test_a_bom_file_keeps_the_bom_at_byte_0_and_inserts_after_the_heading(
        self, tmp_path
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()
        content = "﻿# ours\nhand-written, keep me\n"
        (checkout / "AGENTS.md").write_bytes(content.encode("utf-8"))

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 0

        raw = (checkout / "AGENTS.md").read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "the BOM must stay at byte 0"
        merged = raw.decode("utf-8")
        assert "<!-- guild-block:start -->" in merged
        assert "hand-written, keep me" in merged
        assert merged.index("# ours") < merged.index("<!-- guild-block:start -->")

    def test_first_time_init_with_guild_block_is_reported_as_created_not_unchanged(
        self, tmp_path, capsys
    ) -> None:
        checkout = tmp_path / "app"
        checkout.mkdir()

        assert run("--project", "app", "--path", str(checkout), "--guild-block") == 0

        out = capsys.readouterr().out
        assert "created with the block" in out
        assert "unchanged" not in out


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
        # Not AGENTS.md/CLAUDE.md: `--path` alone already makes
        # scaffold.instruction_files() write those from the packaged
        # template in the same call (unchanged by this ticket — DG-442
        # retires that), so a config-repo copy of .claude/settings.json
        # proves the wiring without the two colliding over the same file.
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
        # Pre-existing, so scaffold.instruction_files() "keeps" it rather
        # than writing a fresh one — isolating the config-repo failure's
        # own "nothing written" guarantee from that unrelated write.
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
        # instruction_files() already wrote a placeholder AGENTS.md from the
        # packaged template on the line above — overwrite it explicitly so
        # this test is about --config-repo finding the registered path on a
        # later call, not about the untracked-file-skip default (covered in
        # tests/test_layer_copy.py).
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

    def test_path_and_config_repo_together_colliding_on_agents_md_is_non_zero_with_a_warning(
        self, tmp_path, capsys
    ) -> None:
        """MEDIUM-HIGH review finding: --path alone makes
        scaffold.instruction_files() write a default AGENTS.md first
        (unchanged by this ticket, DG-442's job); the config-repo copy that
        follows in the same call then sees it as existing and, finding it
        different from the config repo's own copy, must not exit 0 with
        only a buried info line — it must say so loudly and fail the run."""
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

        assert code == 1
        err = capsys.readouterr().err
        assert str(checkout / "AGENTS.md") in err
        assert "differs from the config repo" in err
        assert "--overwrite-ai-layer" in err
        # The scaffold-written default is still on disk, untouched by the
        # config repo's own copy — refused, not silently clobbered either
        # way.
        agents = (checkout / "AGENTS.md").read_text(encoding="utf-8")
        assert agents != "from the config repo\n"

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
