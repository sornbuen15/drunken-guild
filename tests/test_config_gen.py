# mypy: ignore-errors
"""DT-228. The configs are generated, and the generated ones honour the lock.

Every file this module emits was hand-written at least once, and every
hand-written one drifted. ALPHA's ``.mcp.json`` was still passing ``--workspace``
two releases after the flag was deleted. The installed tool environment carries
``mcp`` 1.29.0 against a lock pinning 1.28.1, because ``uv tool install`` does
not read ``uv.lock`` -- both satisfy ``<2``, and nothing reported the
difference until ``drunken-doctor`` grew a check for it (DT-252).
"""

import json
from pathlib import Path

from core import config_gen


class TestTheRetiredServerStaysRetired:
    def test_board_mcp_is_not_in_the_server_list(self) -> None:
        """DT-250 retired the local board because a second coordination surface
        can disagree with Jira -- the failure that cost DT-248 and DT-249 whole
        sessions. Onboarding was declaring it into every new project anyway.
        """
        assert not any("board" in name for name in config_gen.MCP_SERVERS)

    def test_neither_shape_emits_it(self) -> None:
        """Asserted on the output, not the constant. A test that compares the
        config against MCP_SERVERS agrees with whatever the constant says,
        which is exactly how this survived."""
        assert "board" not in json.dumps(config_gen.mcp_config("alpha"))
        assert "board" not in json.dumps(config_gen.host_config("alpha"))


class TestARepoConfigAndAHostConfigDifferOnPurpose:
    def test_the_repo_config_names_commands_and_never_paths(self) -> None:
        """It is committed and shared. An absolute path here is one machine's
        layout in everyone else's history."""
        serialised = json.dumps(config_gen.mcp_config("alpha"))

        assert "/Users/" not in serialised and "/home/" not in serialised
        assert "--directory" not in serialised and "PYTHONPATH" not in serialised

    def test_the_host_config_resolves_to_an_absolute_command(
        self, tmp_path, monkeypatch
    ) -> None:
        """A GUI app launched from /Applications inherits a minimal PATH that
        does not include ~/.local/bin, so a bare name works in a terminal and
        fails silently inside the IDE."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in config_gen.MCP_SERVERS:
            (bin_dir / name).write_text("#!/bin/sh\n")
        monkeypatch.setenv("UV_TOOL_BIN_DIR", str(bin_dir))

        entry = config_gen.host_config("alpha")["mcpServers"]["drunken-jira-mcp"]

        assert entry["command"] == str(bin_dir / "drunken-jira-mcp")

    def test_every_server_is_scoped_to_the_project(self) -> None:
        for entry in config_gen.mcp_config("alpha")["mcpServers"].values():
            assert entry["args"] == ["--project", "alpha"], (
                "An unscoped server acts on whichever project it defaulted to."
            )


class TestTheInstallCommandHonoursTheLock:
    def test_it_names_with_requirements_when_there_is_a_file(self) -> None:
        command = config_gen.install_command(Path("/tmp/requirements.lock.txt"))

        assert "--with-requirements" in command

    def test_without_one_it_says_so_rather_than_pretending(self) -> None:
        """Silence here would be the failure repeating: an install that looks
        pinned and is not is worse than one that admits it is not."""
        command = config_gen.install_command(None)

        assert "--with-requirements" not in command
        assert "ignores uv.lock" in command

    def test_pins_are_counted_as_packages_not_lines(self) -> None:
        """The export carries a hash block per package, so 43 packages is 1,337
        lines. Reporting lines would overstate it thirtyfold -- a number nobody
        would check and everybody would quote."""
        exported = (
            "mcp==1.28.1 \\\n    --hash=sha256:aaa \\\n    --hash=sha256:bbb\n"
            "httpx==0.28.1 \\\n    --hash=sha256:ccc\n"
        )

        assert config_gen.count_pins(exported) == 2

    def test_a_missing_uv_degrades_rather_than_raising(
        self, tmp_path, monkeypatch
    ) -> None:
        """An environment without uv can still generate its MCP configs."""
        monkeypatch.setenv("PATH", str(tmp_path))

        assert config_gen.export_requirements(tmp_path) is None

    def test_the_real_export_pins_the_locked_mcp_version(self) -> None:
        """The whole point of the ticket, checked against the real lock rather
        than a fixture: the deployment drifted to mcp 1.29.0 while uv.lock
        pinned 1.28.1, and this is what closes that gap."""
        exported = config_gen.export_requirements(
            Path(__file__).resolve().parent.parent
        )
        if exported is None:
            import pytest

            pytest.skip("uv is not available here; CI covers the export elsewhere")

        locked = [line for line in exported.splitlines() if line.startswith("mcp==")]
        assert locked, "the export named no mcp pin at all"


class TestMergingLeavesTheHostsOwnServersAlone:
    def test_an_unrecognised_server_survives(self, tmp_path) -> None:
        """Antigravity declares servers of its own. Overwriting the file to add
        ours would take those with it."""
        host = tmp_path / "mcp_config.json"
        host.write_text(
            json.dumps({"mcpServers": {"kanban-board": {"command": "node"}}})
        )

        config_gen.merge_into_host_config(host, "alpha")

        servers = json.loads(host.read_text())["mcpServers"]
        assert servers["kanban-board"] == {"command": "node"}
        assert set(config_gen.MCP_SERVERS) <= set(servers)

    def test_merging_twice_reports_no_change(self, tmp_path) -> None:
        host = tmp_path / "mcp_config.json"
        config_gen.merge_into_host_config(host, "alpha")

        assert config_gen.merge_into_host_config(host, "alpha") == []


class TestTheInstallOutputDoesNotLookLikeAnInstall:
    """It writes a file and prints a command; it installs nothing.

    The first version printed the filename and the command with no verb between
    them. That reads as a report of work completed, it was taken as one, and a
    deployment stayed three tickets behind -- including an unfixed security
    finding -- while every surface looked fine. Cost a full round-trip on
    2026-08-19.
    """

    def test_it_says_not_installed(self, tmp_path, monkeypatch, capsys) -> None:
        monkeypatch.setattr(
            config_gen, "export_requirements", lambda root: "mcp==1.28.1\n"
        )

        config_gen._emit_install(str(tmp_path / "req.txt"))

        out = capsys.readouterr().out
        assert "NOT INSTALLED" in out, (
            "Output that only names a file and a command reads as a report of "
            "work done. It has to say which of the two it did."
        )
        assert "uv tool install" in out, "It still has to hand over the command."


class TestTheImageInstallsWhatTheLockNames:
    """The Dockerfile is the checkable form of the claim, so the flag that
    makes it true is asserted here rather than trusted.

    Verified by building it during DT-228: with --with-requirements the image
    reports mcp 1.28.1, which is what uv.lock pins; without it, the same
    Dockerfile on the same base produces 1.29.0 -- exactly the drift the host
    deployment had. One line is the whole difference.
    """

    def test_the_install_is_pinned(self) -> None:
        dockerfile = (Path(__file__).resolve().parent.parent / "Dockerfile").read_text()

        assert "--with-requirements" in dockerfile, (
            "A bare `uv tool install .` resolves afresh inside the declared "
            "ranges, which is how the deployment drifted to mcp 1.29.0 while "
            "uv.lock pinned 1.28.1."
        )

    def test_secrets_are_not_copied_into_a_layer(self) -> None:
        """A token baked into a layer survives every later deletion."""
        ignored = (Path(__file__).resolve().parent.parent / ".dockerignore").read_text()

        assert ".env" in ignored and ".agents" in ignored
